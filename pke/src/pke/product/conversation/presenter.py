"""Traduz resultado do Engine para o contrato público. Copy de UI vive aqui, não no Core."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pke.application.ask_results import AskClarification, AskResult, AskStatus
from pke.application.results import CorrectionIngestOutcome, IngestResult, IngestStatus
from pke.product.api.v1.dtos import (
    ApiClarification,
    ApiClarificationMode,
    ApiClarificationOption,
    ApiErrorBody,
    ApiMessageResponse,
    ApiMessageStatus,
    ApiOperation,
    ApiOperationKind,
    ApiOperationOutcome,
    ApiResponseType,
)
from pke.product.conversation.engine_gateway import (
    EngineTurn,
    ask_trace_result,
    is_retryable_provider_failure,
)
from pke.product.conversation.result_projection import (
    compact_projection,
    project_ask,
    project_query_result,
)
from pke.product.ids import clarification_id, message_id
from pke.query.results import QueryResult

EntityLabelFn = Callable[[str, str], str | None]

_QUESTION_TEXT = {
    "clarify.entity.which_one": "Você está falando de qual item?",
    "clarify.entity.vehicle": "Você está falando de qual veículo?",
    "clarify.entity.automobile": "Você está falando de qual carro?",
    "clarify.time": "Em que momento isso aconteceu?",
    "clarify.time.range": "Em que período você quer consultar?",
    "clarify.attribute.mileage": "Qual era a quilometragem?",
    "clarify.attribute.amount": "Qual foi o valor?",
    "clarify.attribute.value": "Qual é o valor dessa propriedade?",
    "clarify.attribute.vehicle_value": "Qual é a marca ou o modelo do seu carro?",
    "clarify.attribute.dimension": "Qual propriedade você quer registrar?",
    "clarify.measurement.dimension": "Qual grandeza você quer medir?",
    "clarify.measurement.value": "Qual é o valor medido?",
    "clarify.state.value": "Qual é o estado?",
    "clarify.state.dimension": "Qual dimensão de estado?",
    "clarify.generic": "Pode detalhar um pouco mais?",
    "clarify.action.maintain": "Que tipo de manutenção foi?",
    "clarify.due": "Qual é o vencimento?",
    "clarify.recurrence": "Com que frequência isso se repete?",
    "clarify.correction.target": "O que você quer corrigir?",
    "clarify.correction.fact": "Qual é o valor correto?",
    "time.missing": "Em que momento isso aconteceu?",
}


def present_turn(
    turn: EngineTurn,
    *,
    conversation_id: str,
    client_request_id: str | None,
    request_id: str | None,
    entity_label: EntityLabelFn,
    user_id: str,
    debug: dict[str, Any] | None = None,
) -> ApiMessageResponse:
    if turn.provider_failure is not None and is_retryable_provider_failure(turn.provider_failure):
        return _error(
            conversation_id,
            "PROVIDER_UNAVAILABLE",
            "Não foi possível processar sua solicitação agora. Nada foi registrado.",
            client_request_id,
            request_id,
            debug,
        )
    if turn.interpretation_error is not None:
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.UNSUPPORTED,
            status=ApiMessageStatus.COMPLETED,
            text="Não consegui interpretar isso com segurança suficiente.",
            data={"status": "unsupported", "kind": "interpretation"},
            operation=ApiOperation(
                kind=ApiOperationKind.NONE, outcome=ApiOperationOutcome.UNSUPPORTED
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    if turn.ask is not None:
        return _present_ask(
            turn.ask,
            conversation_id=conversation_id,
            client_request_id=client_request_id,
            request_id=request_id,
            entity_label=entity_label,
            user_id=user_id,
            debug=debug,
        )
    if turn.ingest is not None:
        return _present_ingest(
            turn.ingest,
            conversation_id=conversation_id,
            client_request_id=client_request_id,
            request_id=request_id,
            entity_label=entity_label,
            user_id=user_id,
            debug=debug,
            turn_is_correction=turn.is_correction,
        )
    return _error(
        conversation_id,
        "INTERNAL",
        "Não consegui processar isso agora. Nada foi registrado.",
        client_request_id,
        request_id,
        debug,
    )


def _ingest_write_data(
    result: IngestResult,
    *,
    kind: str,
    correction: bool | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "status": result.status.value,
        "kind": kind,
        "claims": result.claims.model_dump(mode="json"),
    }
    if correction is not None:
        data["correction"] = correction
    _log_write_projection(result, data)
    return data


def _present_ingest(
    result: IngestResult,
    *,
    conversation_id: str,
    client_request_id: str | None,
    request_id: str | None,
    entity_label: EntityLabelFn,
    user_id: str,
    debug: dict[str, Any] | None,
    turn_is_correction: bool = False,
) -> ApiMessageResponse:
    if result.status is IngestStatus.COMMITTED:
        correction = (
            turn_is_correction
            or result.correction_outcome is CorrectionIngestOutcome.CORRECTION_APPLIED
            or bool(result.materialization and result.materialization.correction_ids)
        )
        kind = (
            ApiOperationKind.KNOWLEDGE_CORRECTION
            if correction
            else ApiOperationKind.KNOWLEDGE_WRITE
        )
        text = "Certo. Atualizei esse registro." if correction else "Entendi."
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.ACKNOWLEDGEMENT,
            status=ApiMessageStatus.COMPLETED,
            text=text,
            data=_ingest_write_data(result, kind="acknowledgement", correction=correction),
            operation=ApiOperation(kind=kind, outcome=ApiOperationOutcome.COMMITTED),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    if result.status is IngestStatus.PARTIAL:
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.ACKNOWLEDGEMENT,
            status=ApiMessageStatus.COMPLETED,
            text="Entendi parte disso, mas não consegui guardar tudo.",
            data=_ingest_write_data(result, kind="acknowledgement"),
            operation=ApiOperation(
                kind=ApiOperationKind.KNOWLEDGE_WRITE,
                outcome=ApiOperationOutcome.PARTIAL,
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    if result.status is IngestStatus.DEFERRED:
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.ACKNOWLEDGEMENT,
            status=ApiMessageStatus.COMPLETED,
            text="Entendi o que você quis dizer, mas ainda não consigo guardar essa informação corretamente.",
            data=_ingest_write_data(result, kind="acknowledgement"),
            operation=ApiOperation(
                kind=ApiOperationKind.KNOWLEDGE_WRITE,
                outcome=ApiOperationOutcome.DEFERRED,
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    if result.status is IngestStatus.NEEDS_CLARIFICATION:
        clarification = _clarification_from_ingest(result, entity_label, user_id)
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.CLARIFICATION,
            status=ApiMessageStatus.CLARIFICATION_REQUIRED,
            text=clarification_text(result, clarification),
            clarification=clarification,
            data=_clarification_data(clarification, result.clarification.question_key if result.clarification else None),
            operation=ApiOperation(
                kind=ApiOperationKind.CLARIFICATION,
                outcome=ApiOperationOutcome.NEEDS_CLARIFICATION,
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    if result.status is IngestStatus.UNSUPPORTED:
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.UNSUPPORTED,
            status=ApiMessageStatus.COMPLETED,
            text="Entendi o que você quis dizer, mas ainda não consigo guardar essa informação corretamente.",
            data=_ingest_write_data(result, kind="write"),
            operation=ApiOperation(
                kind=ApiOperationKind.KNOWLEDGE_WRITE,
                outcome=ApiOperationOutcome.UNSUPPORTED,
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    if result.correction_outcome in {
        CorrectionIngestOutcome.CORRECTION_UNSUPPORTED,
        CorrectionIngestOutcome.CORRECTION_REJECTED,
        CorrectionIngestOutcome.CORRECTION_REPLACEMENT_NON_MATERIALIZABLE,
    }:
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.UNSUPPORTED,
            status=ApiMessageStatus.COMPLETED,
            text="Ainda não consigo corrigir isso com segurança.",
            data={"status": "unsupported", "kind": "correction"},
            operation=ApiOperation(
                kind=ApiOperationKind.KNOWLEDGE_CORRECTION,
                outcome=ApiOperationOutcome.UNSUPPORTED,
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    if result.correction_outcome in {
        CorrectionIngestOutcome.CORRECTION_TARGET_AMBIGUOUS,
        CorrectionIngestOutcome.CORRECTION_TARGET_UNRESOLVED,
        CorrectionIngestOutcome.CORRECTION_REPLACEMENT_UNRESOLVED,
    }:
        clarification = ApiClarification(
            id=clarification_id(),
            mode=ApiClarificationMode.TEXT,
        )
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.CLARIFICATION,
            status=ApiMessageStatus.CLARIFICATION_REQUIRED,
            text="Não identifiquei o que você quer corrigir. Pode detalhar?",
            clarification=clarification,
            data=_clarification_data(clarification, "clarify.correction.target"),
            operation=ApiOperation(
                kind=ApiOperationKind.CLARIFICATION,
                outcome=ApiOperationOutcome.NEEDS_CLARIFICATION,
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    return ApiMessageResponse(
        conversation_id=conversation_id,
        message_id=message_id(),
        type=ApiResponseType.UNSUPPORTED,
        status=ApiMessageStatus.COMPLETED,
        text="Ainda não consigo registrar isso com segurança.",
        data={"status": "unsupported", "kind": "write"},
        operation=ApiOperation(
            kind=ApiOperationKind.KNOWLEDGE_WRITE, outcome=ApiOperationOutcome.UNSUPPORTED
        ),
        client_request_id=client_request_id,
        request_id=request_id,
        debug=debug,
    )


def _present_ask(
    result: AskResult,
    *,
    conversation_id: str,
    client_request_id: str | None,
    request_id: str | None,
    entity_label: EntityLabelFn,
    user_id: str,
    debug: dict[str, Any] | None,
) -> ApiMessageResponse:
    if result.status is AskStatus.NEEDS_CLARIFICATION:
        clarification = _clarification_from_ask(result.clarification, entity_label, user_id)
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.CLARIFICATION,
            status=ApiMessageStatus.CLARIFICATION_REQUIRED,
            text=ask_clarification_text(
                result.clarification,
                labels=[
                    entity_label(user_id, eid) or eid
                    for eid in (result.clarification.candidate_entity_ids if result.clarification else [])
                ],
            ),
            clarification=clarification,
            data=_clarification_data(
                clarification,
                result.clarification.clarification_key if result.clarification else None,
            ),
            operation=ApiOperation(
                kind=ApiOperationKind.CLARIFICATION,
                outcome=ApiOperationOutcome.NEEDS_CLARIFICATION,
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    if result.status is AskStatus.ANSWERED:
        text, data = project_ask(
            result, entity_label=entity_label, user_id=user_id
        )
        _log_response_projection(
            result,
            data,
            client_request_id=client_request_id,
            request_id=request_id,
        )
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.ANSWER,
            status=ApiMessageStatus.COMPLETED,
            text=text,
            data=data,
            operation=ApiOperation(
                kind=ApiOperationKind.KNOWLEDGE_QUERY, outcome=ApiOperationOutcome.ANSWERED
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    if result.status is AskStatus.NO_RESULTS:
        text, data = project_ask(
            result, entity_label=entity_label, user_id=user_id
        )
        _log_response_projection(
            result,
            data,
            client_request_id=client_request_id,
            request_id=request_id,
        )
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.ANSWER,
            status=ApiMessageStatus.COMPLETED,
            text=text,
            data=data,
            operation=ApiOperation(
                kind=ApiOperationKind.KNOWLEDGE_QUERY, outcome=ApiOperationOutcome.ANSWERED
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    if result.status is AskStatus.UNSUPPORTED:
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.UNSUPPORTED,
            status=ApiMessageStatus.COMPLETED,
            text="Ainda não consigo responder isso com segurança.",
            data={"status": "unsupported", "kind": "query"},
            operation=ApiOperation(
                kind=ApiOperationKind.KNOWLEDGE_QUERY,
                outcome=ApiOperationOutcome.UNSUPPORTED,
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    return ApiMessageResponse(
        conversation_id=conversation_id,
        message_id=message_id(),
        type=ApiResponseType.UNSUPPORTED,
        status=ApiMessageStatus.COMPLETED,
        text="Ainda não consigo responder isso com segurança.",
        data={"status": "unsupported", "kind": "query"},
        operation=ApiOperation(
            kind=ApiOperationKind.KNOWLEDGE_QUERY, outcome=ApiOperationOutcome.UNSUPPORTED
        ),
        client_request_id=client_request_id,
        request_id=request_id,
        debug=debug,
    )


def render_query(
    query_result: QueryResult | None,
    *,
    entity_label: EntityLabelFn | None = None,
    user_id: str = "",
) -> tuple[str, dict[str, Any] | None]:
    return project_query_result(
        query_result, entity_label=entity_label, user_id=user_id
    )


def _log_write_projection(result: IngestResult, data: dict[str, Any]) -> None:
    try:
        from pke.debug.request_log import append_stage
        from pke.debug.trace_context import current_trace

        ids = current_trace()
        file_id = ids.file_id()
        if not file_id:
            return
        append_stage(
            file_id,
            "response_projection",
            {
                "source_status": result.status.value,
                "source_kind": "ingest",
                **compact_projection(data),
            },
            client_request_id=ids.client_request_id,
            request_id=ids.pke_request_id,
            conversation_id=ids.conversation_id,
            user_message_id=ids.user_message_id,
            status=data.get("status"),
        )
    except Exception:
        return


def _log_response_projection(
    ask: AskResult,
    data: dict[str, Any],
    *,
    client_request_id: str | None,
    request_id: str | None,
) -> None:
    try:
        from pke.debug.request_log import append_stage
        from pke.debug.trace_context import current_trace

        ids = current_trace()
        source_kind, source = ask_trace_result(ask)
        body = {
            "source_status": ask.status.value,
            "source_kind": source_kind,
            **compact_projection(data),
        }
        if source.get("numeric_value") is not None:
            body["source_value"] = source["numeric_value"]
        elif source.get("value") is not None:
            body["source_value"] = source["value"]
        if source.get("unit"):
            body["source_unit"] = source["unit"]
        append_stage(
            client_request_id or request_id or ids.file_id(),
            "response_projection",
            body,
            client_request_id=client_request_id or ids.client_request_id,
            request_id=request_id or ids.pke_request_id,
            conversation_id=ids.conversation_id,
            user_message_id=ids.user_message_id,
            status=data.get("status"),
        )
    except Exception:
        return


def _clarification_data(clarification: ApiClarification | None, reason: str | None) -> dict[str, Any]:
    candidates: list[str] = []
    if clarification is not None:
        candidates = [opt.label for opt in clarification.options if opt.label]
    payload: dict[str, Any] = {
        "status": "needs_clarification",
        "kind": "clarification",
        "reason": reason or "generic",
        "candidates": candidates,
    }
    if reason and "insufficient" in reason:
        payload["status"] = "insufficient"
    return payload


def clarification_text(result: IngestResult, clarification: ApiClarification) -> str:
    if clarification.mode is ApiClarificationMode.CHOICE and len(clarification.options) >= 2:
        labels = " ou ".join(opt.label for opt in clarification.options)
        return f"Você está falando do {labels}?"
    if result.clarification is not None:
        mapped = _QUESTION_TEXT.get(result.clarification.question_key)
        if mapped:
            return mapped
    for issue in result.issues:
        mapped = _QUESTION_TEXT.get(issue.code)
        if mapped:
            return mapped
    return "Pode detalhar um pouco mais?"


def ask_clarification_text(
    clarification: AskClarification | None,
    *,
    labels: list[str] | None = None,
) -> str:
    names = [item for item in (labels or []) if item]
    if len(names) >= 2:
        joined = " ou ".join(names)
        return f"Você está falando do {joined}?"
    if clarification is None:
        return "Pode detalhar um pouco mais?"
    return _QUESTION_TEXT.get(clarification.clarification_key, "Pode detalhar um pouco mais?")


def _clarification_from_ingest(
    result: IngestResult,
    entity_label: EntityLabelFn,
    user_id: str,
) -> ApiClarification:
    del entity_label, user_id
    if result.clarification is not None:
        key = result.clarification.question_key
        if key.startswith("clarify.entity.") and key != "clarify.entity.which_one":
            return ApiClarification(id=clarification_id(), mode=ApiClarificationMode.TEXT)
        if key in {"clarify.time", "clarify.due", "clarify.recurrence", "clarify.attribute.mileage"}:
            return ApiClarification(id=clarification_id(), mode=ApiClarificationMode.TEXT)
    return ApiClarification(id=clarification_id(), mode=ApiClarificationMode.TEXT)


def _clarification_from_ask(
    clarification: AskClarification | None,
    entity_label: EntityLabelFn,
    user_id: str,
) -> ApiClarification:
    if clarification and clarification.candidate_entity_ids:
        options: list[ApiClarificationOption] = []
        for entity_id in clarification.candidate_entity_ids:
            label = entity_label(user_id, entity_id) or entity_id
            options.append(ApiClarificationOption(id=entity_id, label=label))
        if len(options) >= 2:
            return ApiClarification(
                id=clarification_id(),
                mode=ApiClarificationMode.CHOICE,
                options=options,
            )
    return ApiClarification(id=clarification_id(), mode=ApiClarificationMode.TEXT)


def _error(
    conversation_id: str,
    code: str,
    message: str,
    client_request_id: str | None,
    request_id: str | None,
    debug: dict[str, Any] | None,
) -> ApiMessageResponse:
    return ApiMessageResponse(
        conversation_id=conversation_id,
        message_id=message_id(),
        type=ApiResponseType.ERROR,
        status=ApiMessageStatus.FAILED,
        text=message,
        error=ApiErrorBody(code=code, message=message),
        data={"status": "error", "kind": "error", "code": code},
        operation=ApiOperation(kind=ApiOperationKind.NONE, outcome=ApiOperationOutcome.FAILED),
        client_request_id=client_request_id,
        request_id=request_id,
        debug=debug,
    )


