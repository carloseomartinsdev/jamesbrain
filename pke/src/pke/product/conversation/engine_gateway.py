"""Gateway do Engine: uma interpretação por turno, depois IngestService ou AskService.

Não monta IngestIR/QueryIR. Não é autoridade semântica.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pke.application.ask import AskService
from pke.application.ask_results import AskResult
from pke.application.ingest import IngestService, ingest_result_from_interpretation_error
from pke.application.results import IngestResult
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation.interpreter import (
    InterpretationContext,
    InterpretationError,
    Interpreter,
)
from pke.interpretation.models import IngestIR, IngestIntent, QueryIR
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
    ) -> EngineTurn:
        self._interpreter.clear()
        ctx = InterpretationContext(
            user=user,
            recent_event_ids=session.recent_event_ids,
            recent_utterances=list(session.recent_utterances),
            client_request_id=client_request_id,
            pke_request_id=pke_request_id,
        )
        try:
            interpreted = self._interpreter.interpret(raw, ctx)
        except InterpretationError as exc:
            dump = _proposal_dump_from_interpreter(self._interpreter)
            incomplete = ingest_result_from_interpretation_error(
                raw, exc, proposal_dump=dump
            )
            if incomplete is not None:
                turn = EngineTurn(ingest=incomplete)
                _log_engine_turn(client_request_id, pke_request_id, turn)
                return turn
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
            turn = EngineTurn(interpretation_error=exc, provider_failure=provider)
            _log_engine_turn(client_request_id, pke_request_id, turn)
            return turn
        if isinstance(interpreted, QueryIR):
            turn = EngineTurn(ask=self._ask.ask(raw, user, session))
            _log_engine_turn(client_request_id, pke_request_id, turn)
            return turn
        is_correction = (
            isinstance(interpreted, IngestIR) and interpreted.intent is IngestIntent.CORRECT
        )
        turn = EngineTurn(
            ingest=self._ingest.ingest(raw, user, session),
            is_correction=is_correction,
        )
        _log_engine_turn(client_request_id, pke_request_id, turn)
        return turn


def is_retryable_provider_failure(exc: LlmError | None) -> bool:
    """Presenter: map exhausted *transient* provider failures to PROVIDER_UNAVAILABLE.

    Auth/config are not treated as temporary unavailability.
    This is UX classification — not a second retry loop.
    """
    return is_transient_provider_failure(exc)


def _is_provider_message(message: str) -> bool:
    return message.startswith("provider:")


def _log_engine_turn(
    client_request_id: str | None,
    pke_request_id: str | None,
    turn: EngineTurn,
) -> None:
    from pke.debug.request_log import append_stage

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
        if turn.ask.clarification is not None:
            body["clarification_reason"] = turn.ask.clarification.reason
    elif turn.ingest is not None:
        body = {
            "path": "ingest",
            "status": turn.ingest.status.value,
            "is_correction": turn.is_correction,
            "issues": [
                {"code": i.code, "message": i.message} for i in turn.ingest.issues[:8]
            ],
            "bound_entity_ids": list(turn.ingest.bound_entity_ids),
        }
        if turn.ingest.correction_outcome is not None:
            body["correction_outcome"] = turn.ingest.correction_outcome.value
        if turn.ingest.materialization is not None:
            mat = turn.ingest.materialization
            body["materialization"] = {
                "entities_created": len(mat.created_entity_ids),
                "entities_reused": len(mat.reused_entity_ids),
                "attributes": len(mat.attribute_ids),
                "relations": len(mat.relation_ids),
                "events": len(mat.event_ids),
                "states": len(mat.state_ids),
                "measurements": len(mat.measurement_ids),
            }
    elif turn.interpretation_error is not None:
        body = {
            "path": "interpret",
            "error": str(turn.interpretation_error),
            "provider_failure": (
                str(turn.provider_failure) if turn.provider_failure is not None else None
            ),
        }
    append_stage(
        client_request_id,
        "engine",
        body,
        pke_request_id=pke_request_id,
    )
