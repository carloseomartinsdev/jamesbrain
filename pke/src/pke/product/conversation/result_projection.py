"""Project Engine/Ask results onto the public structured-result contract.

Ask/Engine status is the knowledge authority. This module must never translate
`answered` into `no_results` because a scalar is falsy (0, false, "").
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from pke.application.ask_results import AskResult, AskStatus
from pke.query.results import QueryResult

EntityLabelFn = Callable[[str, str], str | None]

_KNOWN_MEASUREMENT = {
    "known_single",
    "known_multiple",
    "ambiguous",
    "temporally_unknown",
}
_KNOWN_ATTRIBUTE = {
    "known_single",
    "known_multiple",
    "ambiguous",
    "temporally_unknown",
}
_DIM_PT = {
    "weight": "peso",
    "mass": "peso",
    "height": "altura",
    "temperature": "temperatura",
    "length": "comprimento",
}


def project_ask(
    ask: AskResult,
    *,
    entity_label: EntityLabelFn | None = None,
    user_id: str = "",
) -> tuple[str, dict[str, Any]]:
    entity = _subject_entity(ask, entity_label, user_id)
    if ask.status is AskStatus.NO_RESULTS:
        return _absence(ask.query_result, entity)
    if ask.status is not AskStatus.ANSWERED:
        return "Ainda não consigo responder isso com segurança.", {
            "status": ask.status.value,
            "kind": "query",
        }
    text, data = project_query_result(
        ask.query_result,
        entity_label=entity_label,
        user_id=user_id,
        entity=entity,
    )
    if data.get("status") == "no_results":
        data = _answered_without_absence(ask.query_result, entity)
        text = _text_from_data(data)
    return text, data


def project_query_result(
    query_result: QueryResult | None,
    *,
    entity_label: EntityLabelFn | None = None,
    user_id: str = "",
    entity: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    if query_result is None:
        return "Ainda não sei isso.", {"status": "no_results", "kind": "absence"}
    if entity is None:
        entity = _entity_from_relations(query_result, entity_label, user_id)

    if query_result.relation_answer is not None:
        return _project_relation_answer(query_result, entity_label, user_id, entity)
    if query_result.current_relations:
        return _project_relation_list(query_result, entity_label, user_id, entity)
    if query_result.attribute_proposition_answer is not None:
        return _project_attribute_proposition(query_result)
    if query_result.attribute_values:
        return _project_attribute_values(query_result, entity)
    if query_result.measurement_values or (
        query_result.measurement_status in _KNOWN_MEASUREMENT
        and query_result.measurement_proposition_answer is None
    ):
        return _project_measurement(query_result, entity)
    if query_result.measurement_proposition_answer is not None:
        return _project_measurement_proposition(query_result)
    if query_result.current_state_value is not None:
        return _project_state(query_result, entity)
    if query_result.aggregate is not None and query_result.aggregate.value is not None:
        return _project_aggregate(query_result)
    if query_result.items:
        return f"Encontrei {query_result.matched_count} registro(s).", {
            "status": "answered",
            "kind": "list",
            "items": [{"label": "registros", "value": str(query_result.matched_count)}],
        }
    if query_result.attribute_status in _KNOWN_ATTRIBUTE:
        data = {
            "status": "answered",
            "kind": "attribute",
            "dimension": query_result.attribute_dimension_key,
            "entity": entity,
            "items": [],
        }
        return _text_from_data(data), {k: v for k, v in data.items() if v is not None}
    if query_result.measurement_status in _KNOWN_MEASUREMENT:
        return _project_measurement(query_result, entity)
    return "Ainda não sei isso.", {"status": "no_results", "kind": "absence"}


def compact_projection(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "projected_status": data.get("status"),
        "projected_kind": data.get("kind"),
    }
    if data.get("value") is not None:
        out["value"] = data["value"]
    if data.get("unit"):
        out["unit"] = data["unit"]
    if data.get("dimension"):
        out["dimension"] = data["dimension"]
    if data.get("relation_answer") is not None:
        out["relation_answer"] = data["relation_answer"]
    if data.get("claims") is not None:
        out["claims"] = data["claims"]
    return out


def fmt_number(value: Decimal | int | float | str) -> str:
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


def _absence(
    query_result: QueryResult | None, entity: dict[str, str] | None
) -> tuple[str, dict[str, Any]]:
    data: dict[str, Any] = {"status": "no_results", "kind": "absence", "value": None}
    dimension = None
    if query_result is not None:
        dimension = (
            query_result.measurement_dimension_key
            or query_result.attribute_dimension_key
            or query_result.state_dimension_key
        )
    if dimension:
        data["dimension"] = dimension
    if entity:
        data["entity"] = entity
    return _unknown_text(entity, dimension), data


def _answered_without_absence(
    query_result: QueryResult | None, entity: dict[str, str] | None
) -> dict[str, Any]:
    kind = "knowledge_query"
    dimension = None
    if query_result is not None:
        if query_result.measurement_dimension_key or query_result.measurement_status:
            kind = "measurement"
            dimension = query_result.measurement_dimension_key
        elif query_result.attribute_dimension_key or query_result.attribute_status:
            kind = "attribute"
            dimension = query_result.attribute_dimension_key
        elif query_result.relation_answer is not None or query_result.current_relations:
            kind = "relation"
        elif query_result.current_state_value is not None or query_result.state_dimension_key:
            kind = "state"
            dimension = query_result.state_dimension_key
    data: dict[str, Any] = {"status": "answered", "kind": kind}
    if dimension:
        data["dimension"] = dimension
    if entity:
        data["entity"] = entity
    return data


def _project_relation_answer(
    query_result: QueryResult,
    entity_label: EntityLabelFn | None,
    user_id: str,
    entity: dict[str, str] | None,
) -> tuple[str, dict[str, Any]]:
    mapping = {
        "yes": "Sim.",
        "no": "Pelo que sei, não.",
        "unknown": "Não tenho certeza o suficiente para afirmar.",
    }
    names = _matched_relation_names(query_result, entity_label, user_id)
    status = "answered"
    if query_result.relation_answer == "unknown":
        status = "unknown"
    data: dict[str, Any] = {
        "status": status,
        "kind": "relation",
        "relation_answer": query_result.relation_answer,
        "matched_entities": [{"canonical_name": name} for name in names],
        "items": [{"label": "relação", "value": query_result.relation_answer}],
    }
    if entity:
        data["entity"] = entity
    return mapping.get(query_result.relation_answer or "", "Sim."), data


def _project_relation_list(
    query_result: QueryResult,
    entity_label: EntityLabelFn | None,
    user_id: str,
    entity: dict[str, str] | None,
) -> tuple[str, dict[str, Any]]:
    labels = _matched_relation_names(query_result, entity_label, user_id)
    if not labels:
        text = f"Encontrei {len(query_result.current_relations)} registro(s)."
    elif len(labels) == 1:
        text = f"Encontrei {labels[0]}."
    else:
        text = "Encontrei " + ", ".join(labels[:-1]) + " e " + labels[-1] + "."
    data: dict[str, Any] = {
        "status": "answered",
        "kind": "relation",
        "matched_entities": [{"canonical_name": name} for name in labels],
        "items": [{"label": "relação", "value": name} for name in labels]
        or [{"label": "registros", "value": str(len(query_result.current_relations))}],
    }
    if entity:
        data["entity"] = entity
    return text, data


def _project_attribute_proposition(query_result: QueryResult) -> tuple[str, dict[str, Any]]:
    mapping = {
        "yes": "Sim.",
        "no": "Pelo que sei, não.",
        "unknown": "Não encontrei um valor definitivo.",
        "ambiguous": "Encontrei mais de um valor possível.",
        "temporally_unknown": "Encontrei um registro, mas o momento não está definido.",
    }
    prop = query_result.attribute_proposition_answer
    status = "answered"
    if prop in {"unknown", "temporally_unknown"}:
        status = "unknown"
    if prop == "ambiguous":
        status = "needs_clarification"
    return mapping.get(prop or "", "Sim."), {
        "status": status,
        "kind": "attribute_proposition",
        "relation_answer": prop,
        "dimension": query_result.attribute_dimension_key,
        "items": [{"label": "atributo", "value": prop}],
    }


def _project_attribute_values(
    query_result: QueryResult, entity: dict[str, str] | None
) -> tuple[str, dict[str, Any]]:
    items = []
    for item in query_result.attribute_values:
        label: str | None = None
        if item.text_value is not None and item.text_value != "":
            label = item.text_value
        elif item.numeric_value is not None:
            label = fmt_number(item.numeric_value)
        elif item.year_value is not None:
            label = str(item.year_value)
        dim_label = item.dimension_key or query_result.attribute_dimension_key or "valor"
        row: dict[str, Any] = {"label": dim_label, "value": label}
        if item.unit:
            row["unit"] = item.unit
        items.append(row)
    dim = query_result.attribute_dimension_key or (items[0]["label"] if items else None)
    value = items[0]["value"] if len(items) == 1 else None
    data: dict[str, Any] = {
        "status": "answered",
        "kind": "attribute",
        "dimension": dim,
        "value": value,
        "items": items,
    }
    if entity:
        data["entity"] = entity
        if entity.get("name"):
            data.setdefault("matched_entities", [{"canonical_name": entity["name"]}])
    text = _attribute_text(items, entity)
    return text, {k: v for k, v in data.items() if v is not None}


def _project_measurement(
    query_result: QueryResult, entity: dict[str, str] | None
) -> tuple[str, dict[str, Any]]:
    items = [
        {
            "label": query_result.measurement_dimension_key or "medição",
            "value": fmt_number(item.numeric_value),
            "unit": item.unit or item.currency_code,
        }
        for item in query_result.measurement_values
        if item.numeric_value is not None
    ]
    dimension = query_result.measurement_dimension_key
    value = items[0]["value"] if len(items) == 1 else None
    unit = items[0]["unit"] if len(items) == 1 else None
    data: dict[str, Any] = {
        "status": "answered",
        "kind": "measurement",
        "dimension": dimension,
        "value": value,
        "unit": unit,
        "items": items,
        "entity": entity,
    }
    return _measurement_text(items, entity, dimension), {
        k: v for k, v in data.items() if v is not None
    }


def _project_measurement_proposition(query_result: QueryResult) -> tuple[str, dict[str, Any]]:
    mapping = {
        "yes": "Sim.",
        "unknown": "Ainda não sei isso.",
        "ambiguous": "Encontrei mais de uma medição possível.",
        "temporally_unknown": "Encontrei uma medição, mas o momento não está definido.",
    }
    prop = query_result.measurement_proposition_answer
    status = "answered" if prop == "yes" else "unknown"
    if prop == "ambiguous":
        status = "needs_clarification"
    return mapping.get(prop or "", "Sim."), {
        "status": status,
        "kind": "measurement_proposition",
        "relation_answer": prop,
        "dimension": query_result.measurement_dimension_key,
        "items": [],
    }


def _project_state(
    query_result: QueryResult, entity: dict[str, str] | None
) -> tuple[str, dict[str, Any]]:
    value = query_result.current_state_value
    data: dict[str, Any] = {
        "status": "answered",
        "kind": "state",
        "dimension": query_result.state_dimension_key,
        "value": value,
        "items": [{"label": "estado", "value": value}],
    }
    if entity:
        data["entity"] = entity
    return f"O estado atual é {value}.", {k: v for k, v in data.items() if v is not None}


def _project_aggregate(query_result: QueryResult) -> tuple[str, dict[str, Any]]:
    value = query_result.aggregate.value
    currency = query_result.aggregate.currency
    if currency:
        text = f"Encontrei um total de {_fmt_money(value, currency)}."
    else:
        text = f"Encontrei um total de {fmt_number(value)}."
    return text, {
        "status": "answered",
        "kind": "aggregate",
        "value": str(value),
        "items": [{"label": "total", "value": str(value), "currency": currency}],
    }


def _measurement_text(
    items: list[dict[str, Any]], entity: dict[str, str] | None, dimension: str | None
) -> str:
    if not items:
        return "Ainda não consigo afirmar o valor com segurança."
    if len(items) > 1:
        parts = []
        for row in items:
            unit = f" {row['unit']}" if row.get("unit") else ""
            parts.append(f"{row['value']}{unit}".strip())
        return "Encontrei " + ", ".join(parts) + "."
    value = items[0]["value"]
    unit = items[0].get("unit")
    unit_s = f" {unit}" if unit else ""
    name = (entity or {}).get("name")
    dim = (dimension or items[0].get("label") or "").casefold()
    if name and dim in {"weight", "mass", "peso", "massa"}:
        return f"A {name} pesa {value}{unit_s}.".replace("  ", " ")
    if name and dim in {"temperature", "temperatura"}:
        return f"A {name} está a {value}{unit_s}.".replace("  ", " ")
    if name:
        return f"{name}: {value}{unit_s}.".replace("  ", " ")
    return f"{value}{unit_s}.".strip()


def _attribute_text(items: list[dict[str, Any]], entity: dict[str, str] | None) -> str:
    name = (entity or {}).get("name")
    if len(items) == 1:
        value = items[0].get("value")
        if value is None:
            return "Ainda não consigo afirmar o valor com segurança."
        if name and str(value).casefold() != name.casefold():
            return f"{name}: {value}."
        return f"{value}."
    parts = [f"{row['label']} {row['value']}" for row in items if row.get("value") is not None]
    if parts:
        return "Encontrei " + ", ".join(parts) + "."
    return f"Encontrei {len(items)} valores."


def _unknown_text(entity: dict[str, str] | None, dimension: str | None) -> str:
    name = (entity or {}).get("name")
    dim = _DIM_PT.get((dimension or "").casefold(), None)
    if name and dim:
        return f"Ainda não sei a {dim} da {name}."
    if name:
        return f"Ainda não sei isso sobre {name}."
    return "Ainda não sei isso."


def _text_from_data(data: dict[str, Any]) -> str:
    kind = data.get("kind")
    entity = data.get("entity") if isinstance(data.get("entity"), dict) else None
    if data.get("status") == "no_results":
        return _unknown_text(entity, data.get("dimension"))
    if kind == "measurement":
        items = data.get("items") if isinstance(data.get("items"), list) else []
        if not items and data.get("value") is not None:
            items = [
                {
                    "label": data.get("dimension") or "medição",
                    "value": data.get("value"),
                    "unit": data.get("unit"),
                }
            ]
        return _measurement_text(items, entity, data.get("dimension"))
    if kind == "relation":
        answer = data.get("relation_answer")
        if answer == "no" or answer is False:
            return "Pelo que sei, não."
        if answer == "yes" or answer is True:
            return "Sim."
    if data.get("value") is not None:
        return f"{data['value']}."
    return "Ainda não consigo afirmar o valor com segurança."


def _subject_entity(
    ask: AskResult,
    entity_label: EntityLabelFn | None,
    user_id: str,
) -> dict[str, str] | None:
    ids = list(ask.resolved_entity_ids)
    if not ids and ask.resolved_spec is not None:
        ids = list(ask.resolved_spec.entity_ids)
    if not ids:
        return None
    entity_id = ids[0]
    name = None
    if entity_label is not None and user_id:
        name = entity_label(user_id, entity_id)
    payload = {"entity_id": entity_id}
    if name:
        payload["name"] = name
    return payload


def _entity_from_relations(
    query_result: QueryResult,
    entity_label: EntityLabelFn | None,
    user_id: str,
) -> dict[str, str] | None:
    names = _matched_relation_names(query_result, entity_label, user_id)
    if len(names) == 1:
        return {"name": names[0]}
    return None


def _matched_relation_names(
    query_result: QueryResult,
    entity_label: EntityLabelFn | None,
    user_id: str,
) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in query_result.current_relations:
        label = item.object_label
        if not label and entity_label is not None and user_id:
            label = entity_label(user_id, item.object_entity_id)
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(label)
    return names
