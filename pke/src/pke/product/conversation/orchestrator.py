"""Conversation Orchestrator — fronteira de aplicação, não autoridade semântica.

CONVERSATION_LIFECYCLE_AUTHORITY / MESSAGE_LIFECYCLE_AUTHORITY /
PENDING_CLARIFICATION_AUTHORITY / PRODUCT_OPERATION_AUTHORITY /
PRODUCT_IDEMPOTENCY_AUTHORITY / ENGINE_INVOCATION_AUTHORITY
= ConversationOrchestrator (+ ProductStore for persistence).

EngineGateway remains an adapter only.
Cross-store: Product DB ≠ Knowledge DB — no shared ACID transaction.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pke.application.clarification_recovery import (
    ClarificationRecoveryService,
    RecoveryStatus,
)
from pke.application.pending_operation import (
    PendingOperationStatus,
    PendingSemanticOperation,
)
from pke.domain.value_objects import UserContext
from pke.persist.sqlite.read_store import SqliteKnowledgeReadStore
from pke.product.api.v1.dtos import (
    ApiClarification,
    ApiClarificationAnswerRequest,
    ApiClarificationMode,
    ApiClarificationOption,
    ApiConversation,
    ApiConversationSummary,
    ApiMessage,
    ApiMessageRequest,
    ApiMessageResponse,
    ApiMessageRole,
    ApiMessageStatus,
    ApiOperation,
    ApiOperationKind,
    ApiOperationOutcome,
    ApiResponseType,
)
from pke.product.auth import AuthUser
from pke.product.conversation.engine_gateway import EngineGateway, EngineTurn
from pke.product.conversation.idempotency import (
    message_fingerprint,
    clarification_fingerprint,
)
from pke.product.conversation.presenter import present_turn
from pke.product.conversation.recovery import (
    OperationRequiresReconciliation,
    ProductRecoveryService,
    RecoveryAction,
)
from pke.product.conversation.store import ProductStore
from pke.product.ids import message_id, request_id as new_request_id

_LOG = logging.getLogger("pke.product")


class ConversationNotFound(Exception):
    pass


class ClarificationNotFound(Exception):
    pass


class ClarificationConflict(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


class IdempotencyInProgress(Exception):
    pass


class ProductStoreUnavailable(Exception):
    pass


class ConversationOrchestrator:
    def __init__(
        self,
        store: ProductStore,
        gateway: EngineGateway,
        knowledge: SqliteKnowledgeReadStore,
        *,
        timezone: str = "America/Fortaleza",
        debug_ui: bool = False,
        clarification_recovery: ClarificationRecoveryService | None = None,
        product_recovery: ProductRecoveryService | None = None,
    ) -> None:
        self._store = store
        self._gateway = gateway
        self._knowledge = knowledge
        self._timezone = timezone
        self._debug_ui = debug_ui
        self._recovery = clarification_recovery
        self._product_recovery = product_recovery or ProductRecoveryService(store)

    def list_conversations(self, user: AuthUser) -> list[ApiConversationSummary]:
        out: list[ApiConversationSummary] = []
        for row in self._store.list_conversations(user.id):
            out.append(
                ApiConversationSummary(
                    id=row.id,
                    title=row.title,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    last_message_preview=self._store.last_message_preview(user.id, row.id),
                    status="active",
                )
            )
        return out

    def create_conversation(self, user: AuthUser, title: str | None = None) -> ApiConversation:
        row = self._store.create_conversation(user.id, title or "Nova conversa")
        return ApiConversation(
            id=row.id,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
            messages=[],
            pending_clarification=None,
            status="active",
        )

    def get_conversation(self, user: AuthUser, conversation_id: str) -> ApiConversation:
        row = self._store.get_conversation(user.id, conversation_id)
        if row is None:
            raise ConversationNotFound()
        messages = self._store.list_messages(user.id, conversation_id)
        pending = self._store.get_pending_clarification(user.id, conversation_id)
        pending_dto = None
        if pending is not None:
            pending_dto = ApiClarification(
                id=pending.id,
                mode=ApiClarificationMode(pending.mode),
                options=[ApiClarificationOption(**opt) for opt in pending.options],
            )
        return ApiConversation(
            id=row.id,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
            last_message_preview=self._store.last_message_preview(user.id, row.id),
            status="active",
            messages=messages,
            pending_clarification=pending_dto,
        )

    def list_messages(self, user: AuthUser, conversation_id: str) -> list[ApiMessage]:
        if self._store.get_conversation(user.id, conversation_id) is None:
            raise ConversationNotFound()
        return self._store.list_messages(user.id, conversation_id)

    def send_message(self, user: AuthUser, request: ApiMessageRequest) -> ApiMessageResponse:
        fp = message_fingerprint(text=request.text, conversation_id=request.conversation_id)
        claimed = False
        completed = False
        if request.client_request_id:
            try:
                self._product_recovery.ensure_product_store()
            except Exception as exc:
                raise ProductStoreUnavailable() from exc
            outcome = self._product_recovery.begin_or_replay(
                user.id,
                request.client_request_id,
                request_fingerprint=fp,
                conversation_id=request.conversation_id,
            )
            if outcome.action is RecoveryAction.REPLAY_PRODUCT_RESULT and outcome.response:
                return outcome.response
            if outcome.action is RecoveryAction.CONFLICT:
                raise IdempotencyConflict()
            if outcome.action is RecoveryAction.IN_FLIGHT:
                raise IdempotencyInProgress()
            claimed = True

        try:
            if not request.client_request_id:
                try:
                    self._store.ping()
                except Exception as exc:
                    raise ProductStoreUnavailable() from exc
            conversation = self._require_or_create(user, request.conversation_id)
            if conversation.title == "Nova conversa":
                self._store.touch_conversation(
                    user.id, conversation.id, _title_from_text(request.text)
                )
            user_msg = self._store.add_message(
                user_id=user.id,
                conversation_id_value=conversation.id,
                role=ApiMessageRole.USER.value,
                type_="text",
                text=request.text,
                status=ApiMessageStatus.COMPLETED.value,
                client_request_id=request.client_request_id,
            )
            response, turn = self._run_engine(
                user,
                conversation.id,
                request.text,
                client_request_id=request.client_request_id,
            )
            response = response.model_copy(update={"user_message_id": user_msg.id})
            # Idempotency completed immediately after Engine outcome (before optional
            # assistant-row persistence). Product DB ≠ Knowledge DB — no shared ACID.
            if request.client_request_id:
                self._store.complete_idempotent(
                    user.id,
                    request.client_request_id,
                    response.model_dump(mode="json"),
                    request_fingerprint=fp,
                    conversation_id=conversation.id,
                )
                completed = True
            self._persist_assistant(user, conversation.id, request.text, response, turn=turn)
            return response
        except OperationRequiresReconciliation:
            raise
        except ProductStoreUnavailable:
            raise
        except Exception:
            if claimed and not completed and request.client_request_id:
                self._store.fail_idempotent(user.id, request.client_request_id)
            raise

    def answer_clarification(
        self,
        user: AuthUser,
        clarification_id: str,
        request: ApiClarificationAnswerRequest,
    ) -> ApiMessageResponse:
        """Canonical bounded recovery — never concatenates original+answer into Interpreter."""
        fp = clarification_fingerprint(
            clarification_id=clarification_id,
            text=request.text,
            option_id=request.option_id,
        )
        claimed = False
        completed = False
        if request.client_request_id:
            try:
                self._product_recovery.ensure_product_store()
            except Exception as exc:
                raise ProductStoreUnavailable() from exc
            outcome = self._product_recovery.begin_or_replay(
                user.id,
                request.client_request_id,
                request_fingerprint=fp,
                conversation_id=None,
            )
            if outcome.action is RecoveryAction.REPLAY_PRODUCT_RESULT and outcome.response:
                return outcome.response
            if outcome.action is RecoveryAction.CONFLICT:
                raise IdempotencyConflict()
            if outcome.action is RecoveryAction.IN_FLIGHT:
                raise IdempotencyInProgress()
            claimed = True

        try:
            pending_row = self._store.get_clarification(user.id, clarification_id)
            if pending_row is None:
                raise ClarificationNotFound()
            if self._store.get_conversation(user.id, pending_row.conversation_id) is None:
                raise ClarificationNotFound()
            # One active answer: only pending may enter ClarificationRecoveryService.
            if pending_row.status != "pending":
                raise ClarificationConflict()

            answer_text = (request.text or "").strip()
            if request.option_id:
                label = next(
                    (
                        opt["label"]
                        for opt in pending_row.options
                        if opt["id"] == request.option_id
                    ),
                    request.option_id,
                )
                answer_text = label if not answer_text else answer_text
            if not answer_text:
                raise ValueError("clarification answer vazio")

            user_msg = self._store.add_message(
                user_id=user.id,
                conversation_id_value=pending_row.conversation_id,
                role=ApiMessageRole.USER.value,
                type_="text",
                text=answer_text,
                status=ApiMessageStatus.COMPLETED.value,
                client_request_id=request.client_request_id,
            )

            response = self._bounded_answer(
                user, pending_row, answer_text, client_request_id=request.client_request_id
            )
            response = response.model_copy(update={"user_message_id": user_msg.id})
            if request.client_request_id:
                self._store.complete_idempotent(
                    user.id,
                    request.client_request_id,
                    response.model_dump(mode="json"),
                    request_fingerprint=fp,
                    conversation_id=pending_row.conversation_id,
                )
                completed = True
            self._persist_assistant(
                user, pending_row.conversation_id, answer_text, response, turn=None
            )
            return response
        except OperationRequiresReconciliation:
            raise
        except ProductStoreUnavailable:
            raise
        except Exception:
            if claimed and not completed and request.client_request_id:
                self._store.fail_idempotent(user.id, request.client_request_id)
            raise

    def _bounded_answer(
        self,
        user: AuthUser,
        pending_row,
        answer_text: str,
        *,
        client_request_id: str | None,
    ) -> ApiMessageResponse:
        req_id = new_request_id()
        if self._recovery is None or not pending_row.pending_operation_json:
            self._store.mark_clarification_answered(user.id, pending_row.id)
            return ApiMessageResponse(
                conversation_id=pending_row.conversation_id,
                message_id=message_id(),
                type=ApiResponseType.UNSUPPORTED,
                status=ApiMessageStatus.COMPLETED,
                text="Ainda não consigo completar isso com segurança a partir dessa resposta.",
                operation=ApiOperation(
                    kind=ApiOperationKind.CLARIFICATION,
                    outcome=ApiOperationOutcome.UNSUPPORTED,
                ),
                client_request_id=client_request_id,
                request_id=req_id,
            )

        pending = PendingSemanticOperation.model_validate_json(pending_row.pending_operation_json)
        if pending_row.status == "resolved":
            pending = pending.model_copy(update={"status": PendingOperationStatus.RESOLVED})

        session = self._store.load_engine_session(user.id, pending_row.conversation_id)
        ctx = UserContext(user_id=user.id, timezone=self._timezone)
        result = self._recovery.recover(pending, answer_text, ctx, session)

        if result.status is RecoveryStatus.IDEMPOTENT_REPLAY:
            return ApiMessageResponse(
                conversation_id=pending_row.conversation_id,
                message_id=message_id(),
                type=ApiResponseType.ACKNOWLEDGEMENT,
                status=ApiMessageStatus.COMPLETED,
                text="Certo. Já registrei essa informação.",
                operation=ApiOperation(
                    kind=ApiOperationKind.KNOWLEDGE_WRITE,
                    outcome=ApiOperationOutcome.COMMITTED,
                ),
                client_request_id=client_request_id,
                request_id=req_id,
            )

        if result.status is RecoveryStatus.RESOLVED_COMMITTED:
            self._store.mark_clarification_resolved(
                user.id,
                pending_row.id,
                pending_operation_json=(
                    result.pending.model_dump_json() if result.pending else None
                ),
            )
            self._store.save_engine_session(user.id, pending_row.conversation_id, session)
            return ApiMessageResponse(
                conversation_id=pending_row.conversation_id,
                message_id=message_id(),
                type=ApiResponseType.ACKNOWLEDGEMENT,
                status=ApiMessageStatus.COMPLETED,
                text="Certo. Registrei essa informação.",
                operation=ApiOperation(
                    kind=ApiOperationKind.KNOWLEDGE_WRITE,
                    outcome=ApiOperationOutcome.COMMITTED,
                ),
                client_request_id=client_request_id,
                request_id=req_id,
            )

        self._store.mark_clarification_answered(user.id, pending_row.id)
        outcome = ApiOperationOutcome.UNSUPPORTED
        text = "Ainda não consegui completar com essa resposta."
        if result.status is RecoveryStatus.UNSUPPORTED_SLOT:
            text = "Esse tipo de esclarecimento ainda não é suportado com segurança."
        elif result.status is RecoveryStatus.REMAINS_UNRESOLVED:
            text = "Ainda não identifiquei o que falta. Pode responder de outro jeito?"
            outcome = ApiOperationOutcome.NEEDS_CLARIFICATION
        elif result.status is RecoveryStatus.CLOSED:
            text = "Esse esclarecimento já foi encerrado."

        return ApiMessageResponse(
            conversation_id=pending_row.conversation_id,
            message_id=message_id(),
            type=(
                ApiResponseType.UNSUPPORTED
                if outcome is ApiOperationOutcome.UNSUPPORTED
                else ApiResponseType.CLARIFICATION
            ),
            status=(
                ApiMessageStatus.COMPLETED
                if outcome is not ApiOperationOutcome.NEEDS_CLARIFICATION
                else ApiMessageStatus.CLARIFICATION_REQUIRED
            ),
            text=text,
            operation=ApiOperation(kind=ApiOperationKind.CLARIFICATION, outcome=outcome),
            client_request_id=client_request_id,
            request_id=req_id,
        )

    def _require_or_create(self, user: AuthUser, conversation_id: str | None):
        if conversation_id:
            row = self._store.get_conversation(user.id, conversation_id)
            if row is None:
                raise ConversationNotFound()
            return row
        return self._store.create_conversation(user.id)

    def _run_engine(
        self,
        user: AuthUser,
        conversation_id: str,
        text: str,
        *,
        client_request_id: str | None,
    ) -> tuple[ApiMessageResponse, EngineTurn]:
        req_id = new_request_id()
        started = time.perf_counter()
        session = self._store.load_engine_session(user.id, conversation_id)
        session = session.model_copy(
            update={"recent_utterances": self._prior_user_utterances(user.id, conversation_id, text)}
        )
        ctx = UserContext(user_id=user.id, timezone=self._timezone)
        turn = self._gateway.process(
            text,
            ctx,
            session,
            client_request_id=client_request_id,
            pke_request_id=req_id,
        )
        self._store.save_engine_session(user.id, conversation_id, session)
        duration_ms = int((time.perf_counter() - started) * 1000)
        debug = None
        if self._debug_ui:
            debug = {
                "request_id": req_id,
                "latency_ms": duration_ms,
                "result_class": _result_class(turn),
            }
        response = present_turn(
            turn,
            conversation_id=conversation_id,
            client_request_id=client_request_id,
            request_id=req_id,
            entity_label=self._entity_label,
            user_id=user.id,
            debug=debug,
        )
        _LOG.info(
            "turn request_id=%s client_request_id=%s conversation_id=%s user_id=%s "
            "duration_ms=%s result_type=%s status=%s",
            req_id,
            client_request_id,
            conversation_id,
            user.id,
            duration_ms,
            response.type.value,
            response.status.value,
        )
        return response, turn

    def _persist_assistant(
        self,
        user: AuthUser,
        conversation_id: str,
        original_text: str,
        response: ApiMessageResponse,
        *,
        turn: EngineTurn | None,
    ) -> None:
        payload: dict[str, Any] = {}
        pending_json = None
        if (
            turn is not None
            and turn.ingest is not None
            and turn.ingest.pending_operation is not None
        ):
            pending_json = turn.ingest.pending_operation.model_dump_json()
        if response.clarification is not None:
            payload["clarification"] = response.clarification.model_dump(mode="json")
            self._store.add_clarification(
                user_id=user.id,
                conversation_id_value=conversation_id,
                message_id_value=response.message_id,
                mode=response.clarification.mode.value,
                options=[opt.model_dump(mode="json") for opt in response.clarification.options],
                original_text=original_text,
                clarification_id_value=response.clarification.id,
                pending_operation_json=pending_json,
            )
        if response.error is not None:
            payload["error"] = response.error.model_dump(mode="json")
        if response.data is not None:
            payload["data"] = response.data
        if response.operation is not None:
            payload["operation"] = response.operation.model_dump(mode="json")
        self._store.add_message(
            user_id=user.id,
            conversation_id_value=conversation_id,
            role=ApiMessageRole.ASSISTANT.value,
            type_=response.type.value,
            text=response.text,
            status=response.status.value,
            payload=payload or None,
            client_request_id=response.client_request_id,
            message_id_value=response.message_id,
        )
        self._store.touch_conversation(user.id, conversation_id)

    def _prior_user_utterances(
        self, user_id: str, conversation_id: str, current_text: str
    ) -> list[str]:
        messages = self._store.list_messages(user_id, conversation_id)
        texts = [
            (m.text or "").strip()
            for m in messages
            if (getattr(m.role, "value", m.role) == ApiMessageRole.USER.value)
            and (m.text or "").strip()
        ]
        current = current_text.strip()
        if texts and texts[-1] == current:
            texts = texts[:-1]
        return texts[-8:]

    def _entity_label(self, user_id: str, entity_id: str) -> str | None:
        graph = self._knowledge.load_user_graph(user_id)
        entity = graph.entities.get(entity_id)
        return entity.canonical_name if entity is not None else None


def _title_from_text(text: str) -> str:
    compact = " ".join(text.strip().split())
    if len(compact) <= 48:
        return compact or "Nova conversa"
    return compact[:45].rstrip() + "…"


def _result_class(turn) -> str:
    if turn.provider_failure is not None:
        return "provider_failure"
    if turn.interpretation_error is not None:
        return "unsupported_interpretation"
    if turn.ask is not None:
        return f"ask:{turn.ask.status.value}"
    if turn.ingest is not None:
        return f"ingest:{turn.ingest.status.value}"
    return "empty"
