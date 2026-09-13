"""Gateway do Engine: uma interpretação por turno, depois IngestService ou AskService.

Não monta IngestIR/QueryIR. Não é autoridade semântica.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pke.application.ask import AskService
from pke.application.ask_results import AskResult
from pke.application.discourse import interpret_context_from_session
from pke.application.ingest import IngestService, ingest_result_from_interpretation_error
from pke.application.results import IngestResult
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation.discourse import allowed_entity_ids
from pke.interpretation.interpreter import (
    InterpretationError,
    Interpreter,
)
from pke.interpretation.models import IngestIntent, IngestIR, QueryIR
from pke.interpretation.retry import is_transient_provider_failure
from pke.interpretation.semantic.envelope_dispatch import ProviderRoute, dispatch_provider_payload
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.llm.errors import LlmError, LlmProviderError

_LOG = logging.getLogger("pke.product")


def _proposal_dump_from_interpreter(interpreter: TurnCachedInterpreter) -> dict | None:
    raw = getattr(interpreter, "last_raw_content", None)
    if raw is None and hasattr(interpreter, "_inner"):
        raw = getattr(interpreter._inner, "last_raw_content", None)
    if not raw:
        return None
    try:
        dispatched = dispatch_provider_payload(raw)
        if dispatched.route is ProviderRoute.INVALID or not dispatched.payload:
            return None
        if dispatched.route is ProviderRoute.V2_CANONICAL:
            return None
        ir = dispatched.payload.get("ir")
        if dispatched.payload.get("ir_kind") == "semantic_query":
            return None
        if ir is not None:
            from pke.interpretation.semantic.models import SemanticProposal

            return SemanticProposal.model_validate(ir).model_dump()
        env = WireSemanticEnvelope.model_validate(dispatched.payload)
        return env.parsed_proposal().model_dump()
    except Exception:
        return None


class TurnCachedInterpreter:
    """Evita segunda chamada ao interpreter no mesmo turno (ingest/ask)."""

    def __init__(self, inner: Interpreter) -> None:
        self._inner = inner
        self._cached_raw: str | None = None
        self._cached_result: object | None = None

    @property
    def last_raw_content(self) -> str | None:
        return getattr(self._inner, "last_raw_content", None)

    def interpret(self, raw: str, ctx: InterpretationContext) -> object:
        if self._cached_raw == raw and self._cached_result is not None:
            return self._cached_result
        result = self._inner.interpret(raw, ctx)
        self._cached_raw = raw
        self._cached_result = result
        return result

    def clear(self) -> None:
        self._cached_raw = None
        self._cached_result = None


@dataclass
class EngineTurn:
    ingest: IngestResult | None = None
    ask: AskResult | None = None
    interpretation_error: InterpretationError | None = None
    provider_failure: LlmError | None = None
    is_correction: bool = False


class EngineGateway:
    def __init__(
        self,
        interpreter: TurnCachedInterpreter,
        ingest: IngestService,
        ask: AskService,
    ) -> None:
        self._interpreter = interpreter
        self._ingest = ingest
        self._ask = ask

    def process(
        self,
        raw: str,
        user: UserContext,
        session: SessionContext,
        *,
        client_request_id: str | None = None,
        pke_request_id: str | None = None,
        conversation_id: str | None = None,
        user_message_id: str | None = None,
    ) -> EngineTurn:
        from pke.debug.semantic_trace import flush_entity_resolution_stage
        from pke.debug.trace_context import bind_trace, reset_trace

        self._interpreter.clear()
        token = bind_trace(
            client_request_id=client_request_id,
            pke_request_id=pke_request_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
        )
        ctx = interpret_context_from_session(
            session,
            user,
            client_request_id=client_request_id,
            pke_request_id=pke_request_id,
        )
        previous_focus = (
            list(session.discourse.active_focus.entity_ids)
            if session.discourse.active_focus is not None
            else []
        )
        _log_discourse_input(session, conversation_id)
        try:
            try:
                interpreted = self._interpreter.interpret(raw, ctx)
            except InterpretationError as exc:
                dump = _proposal_dump_from_interpreter(self._interpreter)
                incomplete = ingest_result_from_interpretation_error(
                    raw, exc, proposal_dump=dump
                )
                if incomplete is not None:
                    return EngineTurn(ingest=incomplete)
                cause = exc.__cause__
                provider = cause if isinstance(cause, LlmError) else None
                if provider is None and _is_provider_message(str(exc)):
                    provider = LlmProviderError(str(exc))
                if provider is not None:
                    _LOG.warning(
                        "engine provider_failure type=%s message=%s interpretation=%s",
                        type(provider).__name__,
                        str(provider)[:240],
                        str(exc)[:240],
                    )
                return EngineTurn(interpretation_error=exc, provider_failure=provider)
            if isinstance(interpreted, QueryIR):
                _log_discourse_resolution(interpreted)
                turn = EngineTurn(ask=self._ask.ask(raw, user, session))
                try:
                    flush_entity_resolution_stage()
                except Exception:
                    pass
                _log_discourse_update(session, previous_focus)
                _log_engine_turn(client_request_id, pke_request_id, turn)
                return turn
            is_correction = (
                isinstance(interpreted, IngestIR) and interpreted.intent is IngestIntent.CORRECT
            )
            _log_discourse_resolution(interpreted)
            turn = EngineTurn(
                ingest=self._ingest.ingest(raw, user, session),
                is_correction=is_correction,
            )
            try:
                flush_entity_resolution_stage()
            except Exception:
                pass
            _log_discourse_update(session, previous_focus)
            _log_engine_turn(client_request_id, pke_request_id, turn)
            return turn
        finally:
            reset_trace(token)


def is_retryable_provider_failure(exc: LlmError | None) -> bool:
    """Presenter: map exhausted *transient* provider failures to PROVIDER_UNAVAILABLE.

    Auth/config are not treated as temporary unavailability.
    This is UX classification — not a second retry loop.
    """
    return is_transient_provider_failure(exc)


def _known_entity_ids(interpreted: QueryIR | IngestIR) -> list[str]:
    ids: list[str] = []
    if isinstance(interpreted, QueryIR):
        mentions = interpreted.query.entities
    else:
        mentions = interpreted.entities_mentioned
    for mention in mentions:
        if mention.known_entity_id:
            ids.append(mention.known_entity_id)
    return ids


def _log_discourse_input(session: SessionContext, conversation_id: str | None) -> None:
    from pke.debug.semantic_trace import append_trace_stage

    focus = session.discourse.active_focus
    append_trace_stage(
        "discourse_input",
        {
            "conversation_id": conversation_id,
            "active_focus": focus.model_dump(mode="json") if focus else None,
            "recent_referents": [
                item.model_dump(mode="json") for item in session.discourse.recent_referents
            ],
            "allowed_entity_ids": allowed_entity_ids(session.discourse),
            "pending_intent": (
                {
                    "operation": session.discourse.pending_intent.operation,
                    "attribute_dimension_key": session.discourse.pending_intent.attribute_dimension_key,
                    "missing_role": session.discourse.pending_intent.missing_role,
                    "candidate_entity_ids": list(
                        session.discourse.pending_intent.candidate_entity_ids
                    ),
                }
                if session.discourse.pending_intent is not None
                else None
            ),
        },
    )


def _log_discourse_resolution(interpreted: QueryIR | IngestIR) -> None:
    from pke.debug.semantic_trace import append_trace_stage

    decision = interpreted.discourse_decision or "none"
    source = {
        "continue": "active_focus",
        "new_topic": "current_utterance",
        "ambiguous": "none",
        "none": "none",
    }.get(decision, "none")
    append_trace_stage(
        "discourse_resolution",
        {
            "decision": decision,
            "source": source,
            "resolved_entity_ids": _known_entity_ids(interpreted),
        },
    )


def _log_discourse_update(session: SessionContext, previous_focus: list[str]) -> None:
    from pke.debug.semantic_trace import append_trace_stage

    focus = session.discourse.active_focus
    new_focus = list(focus.entity_ids) if focus is not None else []
    append_trace_stage(
        "discourse_update",
        {
            "previous_focus": previous_focus,
            "new_focus": new_focus,
            "reason": session.discourse.last_update_reason,
            "active_focus": focus.model_dump(mode="json") if focus else None,
            "recent_referents": [
                item.model_dump(mode="json") for item in session.discourse.recent_referents
            ],
            "idle_turns": session.discourse.idle_turns,
        },
    )


def _is_provider_message(message: str) -> bool:
    return message.startswith("provider:")


def _log_engine_turn(
    client_request_id: str | None,
    pke_request_id: str | None,
    turn: EngineTurn,
) -> None:
    from pke.debug.request_log import append_stage
    from pke.debug.trace_context import current_trace

    body: dict = {}
    if turn.ask is not None:
        body = {
            "path": "ask",
            "status": turn.ask.status.value,
            "issues": [
                {"code": i.code, "message": i.message} for i in turn.ask.issues[:8]
            ],
            "resolved_entity_ids": list(turn.ask.resolved_entity_ids),
        }
        kind, compact = ask_trace_result(turn.ask)
        if kind is not None:
            body["answer_kind"] = kind
        if compact:
            body["result"] = compact
        value = compact.get("numeric_value") or compact.get("value")
        if value is not None:
            body["value"] = value
        if compact.get("dimension"):
            body["dimension"] = compact["dimension"]
        if turn.ask.clarification is not None:
            body["clarification_reason"] = turn.ask.clarification.reason
            if turn.ask.clarification.clarification_key:
                body["clarification_contract"] = turn.ask.clarification.clarification_key
    elif turn.ingest is not None:
        body = {
            "path": "ingest",
            "status": turn.ingest.status.value,
            "is_correction": turn.is_correction,
            "issues": [
                {"code": i.code, "message": i.message} for i in turn.ingest.issues[:8]
            ],
            "bound_entity_ids": list(turn.ingest.bound_entity_ids),
            "claims": turn.ingest.claims.model_dump(mode="json"),
        }
        if turn.ingest.correction_outcome is not None:
            body["correction_outcome"] = turn.ingest.correction_outcome.value
    elif turn.interpretation_error is not None:
        return
    ids = current_trace()
    append_stage(
        client_request_id or ids.file_id(),
        "engine",
        body,
        client_request_id=client_request_id or ids.client_request_id,
        pke_request_id=pke_request_id or ids.pke_request_id,
        conversation_id=ids.conversation_id,
        user_message_id=ids.user_message_id,
    )


def ask_trace_result(ask: AskResult) -> tuple[str | None, dict]:
    qr = ask.query_result
    if qr is None:
        if ask.status.value == "no_results":
            return "absence", {}
        return None, {}
    if qr.measurement_dimension_key or qr.measurement_values or qr.measurement_status:
        item = qr.measurement_values[0] if qr.measurement_values else None
        compact: dict = {
            "dimension": qr.measurement_dimension_key,
            "status": qr.measurement_status,
        }
        if item is not None and item.numeric_value is not None:
            compact["numeric_value"] = str(item.numeric_value)
        if item is not None and item.unit:
            compact["unit"] = item.unit
        elif item is not None and item.currency_code:
            compact["unit"] = item.currency_code
        kind = "absence" if ask.status.value == "no_results" else "measurement"
        return kind, {k: v for k, v in compact.items() if v is not None}
    if qr.attribute_dimension_key or qr.attribute_values or qr.attribute_status:
        item = qr.attribute_values[0] if qr.attribute_values else None
        compact = {"dimension": qr.attribute_dimension_key, "status": qr.attribute_status}
        if item is not None:
            if item.text_value is not None and item.text_value != "":
                compact["value"] = item.text_value
            elif item.numeric_value is not None:
                compact["value"] = str(item.numeric_value)
            elif item.year_value is not None:
                compact["value"] = str(item.year_value)
        dim = (qr.attribute_dimension_key or "").casefold()
        kind = "intrinsic_property" if dim in {"name", "canonical_name"} else "attribute"
        if ask.status.value == "no_results":
            kind = "absence"
        return kind, {k: v for k, v in compact.items() if v is not None}
    if qr.relation_answer is not None or qr.current_relations:
        compact = {}
        if qr.relation_answer is not None:
            compact["relation_answer"] = qr.relation_answer
        kind = "absence" if ask.status.value == "no_results" else "relation"
        return kind, compact
    if qr.current_state_value is not None or qr.state_dimension_key:
        compact = {"dimension": qr.state_dimension_key}
        if qr.current_state_value is not None:
            compact["value"] = qr.current_state_value
        kind = "absence" if ask.status.value == "no_results" else "state"
        return kind, {k: v for k, v in compact.items() if v is not None}
    if ask.status.value == "no_results":
        return "absence", {}
    return None, {}


