"""Traduz resultado do Engine para o contrato público. Copy de UI vive aqui, não no Core."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
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
from pke.product.conversation.engine_gateway import EngineTurn, is_retryable_provider_failure
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
        text = "Certo. Atualizei esse registro." if correction else "Certo. Registrei essa informação."
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.ACKNOWLEDGEMENT,
            status=ApiMessageStatus.COMPLETED,
            text=text,
            operation=ApiOperation(kind=kind, outcome=ApiOperationOutcome.COMMITTED),
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
            text="Não consegui interpretar isso com segurança suficiente para registrar.",
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
            text=ask_clarification_text(result.clarification),
            clarification=clarification,
            operation=ApiOperation(
                kind=ApiOperationKind.CLARIFICATION,
                outcome=ApiOperationOutcome.NEEDS_CLARIFICATION,
            ),
            client_request_id=client_request_id,
            request_id=request_id,
            debug=debug,
        )
    if result.status is AskStatus.ANSWERED:
        text, data = render_query(result.query_result)
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
        return ApiMessageResponse(
            conversation_id=conversation_id,
            message_id=message_id(),
            type=ApiResponseType.ANSWER,
            status=ApiMessageStatus.COMPLETED,
            text="Não encontrei um registro sobre isso.",
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
        operation=ApiOperation(
            kind=ApiOperationKind.KNOWLEDGE_QUERY, outcome=ApiOperationOutcome.UNSUPPORTED
        ),
        client_request_id=client_request_id,
        request_id=request_id,
        debug=debug,
    )


def render_query(query_result: QueryResult | None) -> tuple[str, dict[str, Any] | None]:
    if query_result is None:
        return "Não encontrei um registro sobre isso.", None
    if query_result.relation_answer is not None:
        mapping = {"yes": "Sim.", "no": "Não.", "unknown": "Não tenho certeza o suficiente para afirmar."}
        return mapping.get(query_result.relation_answer, "Sim."), {
            "kind": "fact_summary",
            "items": [{"label": "relação", "value": query_result.relation_answer}],
        }
    if query_result.current_relations:
        labels = [
            item.object_label
            for item in query_result.current_relations
            if item.object_label
        ]
        if not labels:
            text = f"Encontrei {len(query_result.current_relations)} registro(s)."
        elif len(labels) == 1:
            text = f"Encontrei {labels[0]}."
        else:
            text = "Encontrei " + ", ".join(labels[:-1]) + " e " + labels[-1] + "."
        return text, {
            "kind": "fact_summary",
            "items": [{"label": "relação", "value": name} for name in labels]
            or [{"label": "registros", "value": str(len(query_result.current_relations))}],
        }
    if query_result.attribute_proposition_answer is not None:
        mapping = {
            "yes": "Sim.",
            "no": "Não.",
            "unknown": "Não encontrei um valor definitivo.",
            "ambiguous": "Encontrei mais de um valor possível.",
            "temporally_unknown": "Encontrei um registro, mas o momento não está definido.",
        }
        return mapping.get(query_result.attribute_proposition_answer, "Sim."), {
            "kind": "fact_summary",
            "items": [{"label": "atributo", "value": query_result.attribute_proposition_answer}],
        }
    if query_result.attribute_values:
        items = []
        for item in query_result.attribute_values:
            label = item.text_value or (
                str(item.numeric_value) if item.numeric_value is not None else None
            )
            if item.year_value is not None:
                label = str(item.year_value)
            dim_label = item.dimension_key or query_result.attribute_dimension_key or "valor"
            items.append({"label": dim_label, "value": label})
        if len(items) == 1:
            text = "Encontrei " + (items[0]["value"] or "um registro") + "."
        else:
            parts = [
                f"{row['label']} {row['value']}"
                for row in items
                if row.get("value")
            ]
            text = "Encontrei " + ", ".join(parts) + "." if parts else f"Encontrei {len(items)} valores."
        return text, {"kind": "fact_summary", "items": items}
    if query_result.measurement_values:
        items = [
            {
                "label": query_result.measurement_dimension_key or "medição",
                "value": _fmt_number(item.numeric_value),
                "unit": item.unit or item.currency_code,
            }
            for item in query_result.measurement_values
        ]
        if len(items) == 1:
            unit = f" {items[0]['unit']}" if items[0]["unit"] else ""
            text = f"Encontrei {items[0]['value']}{unit}."
        else:
            text = f"Encontrei {len(items)} medições."
        return text, {"kind": "measurement_list", "items": items}
    if query_result.measurement_proposition_answer is not None:
        mapping = {
            "yes": "Sim.",
            "unknown": "Não encontrei essa medição.",
            "ambiguous": "Encontrei mais de uma medição possível.",
            "temporally_unknown": "Encontrei uma medição, mas o momento não está definido.",
        }
        return mapping.get(query_result.measurement_proposition_answer, "Sim."), {
            "kind": "measurement_list",
            "items": [],
        }
    if query_result.current_state_value:
        return f"O estado atual é {query_result.current_state_value}.", {
            "kind": "fact_summary",
            "items": [{"label": "estado", "value": query_result.current_state_value}],
        }
    if query_result.aggregate is not None and query_result.aggregate.value is not None:
        value = query_result.aggregate.value
        currency = query_result.aggregate.currency
        if currency:
            text = f"Encontrei um total de {_fmt_money(value, currency)}."
        else:
            text = f"Encontrei um total de {_fmt_number(value)}."
        return text, {
            "kind": "fact_summary",
            "items": [{"label": "total", "value": str(value), "currency": currency}],
        }
    if query_result.items:
        return f"Encontrei {query_result.matched_count} registro(s).", {
            "kind": "fact_summary",
            "items": [{"label": "registros", "value": str(query_result.matched_count)}],
        }
    return "Não encontrei um registro sobre isso.", None


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


def ask_clarification_text(clarification: AskClarification | None) -> str:
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
        operation=ApiOperation(kind=ApiOperationKind.NONE, outcome=ApiOperationOutcome.FAILED),
        client_request_id=client_request_id,
        request_id=request_id,
        debug=debug,
    )


def _fmt_number(value: Decimal | int | float | str) -> str:
    amount = Decimal(str(value))
    if amount == amount.to_integral():
        return f"{int(amount)}"
    text = format(amount, "f").rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _fmt_money(value: Decimal | int | float | str, currency: str) -> str:
    amount = Decimal(str(value))
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if currency.upper() == "BRL":
        return f"R$ {formatted}"
    return f"{formatted} {currency}"
