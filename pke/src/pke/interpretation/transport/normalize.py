"""Normalização determinística pré-validação wire. Sem NL, sem DB, sem LLM."""

from __future__ import annotations

import copy
from typing import Any

# Aliases estruturais conhecidos (categoria A).
_CADENCE_ALIASES = {"by_month_day": "by_monthday"}

_REFERENCE_KIND_ALIASES = {
    "explicit": "named",
    "specific": "named",
    "type": "class",
    "generic": "class",
    "category": "class",
    "class_constraint": "class",
    "type_constraint": "class",
    "entity_type": "class",
    "entity_class": "class",
}

# Campos de texto opcional onde "" significa ausência semântica (categoria C).
_OPTIONAL_TEXT_KEYS = frozenset(
    {
        "original_text",
        "interpretation",
        "precision",
        "timezone",
        "time_of_day",
    }
)


def normalize_wire_shape(payload: dict[str, Any]) -> dict[str, Any]:
    """Aplica transformações permitidas antes de `WireEnvelope.model_validate`."""
    data = copy.deepcopy(payload)
    ir = data.get("ir")
    if not isinstance(ir, dict):
        return data
    if data.get("ir_kind") == "ingest":
        _normalize_ingest_ir(ir)
    elif data.get("ir_kind") == "query":
        _normalize_query_ir(ir)
    return data


def _normalize_ingest_ir(ir: dict[str, Any]) -> None:
    if isinstance(ir.get("event"), dict):
        _normalize_event(ir["event"])
    if isinstance(ir.get("obligation"), dict):
        obligation = ir["obligation"]
        if isinstance(obligation.get("cadence"), dict):
            obligation["cadence"] = _normalize_cadence(obligation["cadence"])
        if isinstance(obligation.get("due"), dict):
            obligation["due"] = _normalize_time_dict(obligation["due"])
        if isinstance(obligation.get("facts"), list):
            obligation["facts"] = [_normalize_fact(item) for item in obligation["facts"]]
    if isinstance(ir.get("correction"), dict):
        correction = ir["correction"]
        if isinstance(correction.get("facts"), list):
            correction["facts"] = [_normalize_fact(item) for item in correction["facts"]]
    if isinstance(ir.get("entities_mentioned"), list):
        ir["entities_mentioned"] = [
            _normalize_entity(item) for item in ir["entities_mentioned"] if isinstance(item, dict)
        ]


def _normalize_query_ir(ir: dict[str, Any]) -> None:
    query = ir.get("query")
    if not isinstance(query, dict):
        return
    if isinstance(query.get("time"), dict):
        query["time"] = _normalize_query_time_dict(query["time"])
    if isinstance(query.get("entities"), list):
        query["entities"] = [
            _normalize_entity(item) for item in query["entities"] if isinstance(item, dict)
        ]


def _normalize_event(event: dict[str, Any]) -> None:
    event["time"] = _normalize_time_dict(event.get("time"))
    if isinstance(event.get("participants"), list):
        event["participants"] = [
            _normalize_entity(item) for item in event["participants"] if isinstance(item, dict)
        ]
    if isinstance(event.get("facts"), list):
        event["facts"] = [_normalize_fact(item) for item in event["facts"] if isinstance(item, dict)]
    if isinstance(event.get("action"), str):
        event["action"] = event["action"].strip()
    if isinstance(event.get("type"), str):
        event["type"] = event["type"].strip()


def _normalize_time_dict(time: object) -> dict[str, Any]:
    if time is None:
        return {"original_text": ""}
    if not isinstance(time, dict):
        return {"original_text": ""}
    out = dict(time)
    for key in list(out.keys()):
        if key in _OPTIONAL_TEXT_KEYS:
            out[key] = _empty_to_default_text(out.get(key))
    if "original_text" not in out:
        out["original_text"] = ""
    if isinstance(out.get("weekday"), str):
        out["weekday"] = out["weekday"].strip().lower()
    if isinstance(out.get("relative_day"), str):
        out["relative_day"] = out["relative_day"].strip().lower()
    if isinstance(out.get("weekday_policy"), str):
        out["weekday_policy"] = out["weekday_policy"].strip().lower()
    return out


def _normalize_query_time_dict(time: dict[str, Any]) -> dict[str, Any]:
    out = dict(time)
    if "original_text" in out:
        value = out["original_text"]
        out["original_text"] = None if value == "" else value
    if isinstance(out.get("relative_period"), str):
        out["relative_period"] = out["relative_period"].strip().lower()
    return out


def _normalize_cadence(cadence: dict[str, Any]) -> dict[str, Any]:
    out = dict(cadence)
    for old, new in _CADENCE_ALIASES.items():
        if old in out and new not in out:
            out[new] = out.pop(old)
    return out


def _normalize_fact(fact: dict[str, Any]) -> dict[str, Any]:
    out = dict(fact)
    if out.get("money") is None and isinstance(out.get("value"), dict):
        value = out["value"]
        if "amount" in value:
            out["money"] = dict(value)
    if "money" in out and "value" in out:
        del out["value"]
    if isinstance(out.get("qualifier"), str):
        out["qualifier"] = out["qualifier"].strip().lower()
    if isinstance(out.get("epistemic_status"), str):
        out["epistemic_status"] = out["epistemic_status"].strip().lower()
    return out


def _normalize_entity(entity: dict[str, Any]) -> dict[str, Any]:
    out = dict(entity)
    if isinstance(out.get("entity_type"), str):
        out["entity_type"] = out["entity_type"].strip()
    if isinstance(out.get("role"), str):
        out["role"] = out["role"].strip()
    if isinstance(out.get("reference_kind"), str):
        rk = out["reference_kind"].strip().lower()
        out["reference_kind"] = _REFERENCE_KIND_ALIASES.get(rk, rk)
    return out


def _empty_to_default_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)
