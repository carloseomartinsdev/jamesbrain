"""Slim presenter input. Reuses the jamesCore/PKE envelope; no parallel knowledge DTO."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationSnippet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    text: str


class StructuredResult(BaseModel):
    """Capability-agnostic structured result. PKE is the first producer."""

    model_config = ConfigDict(extra="forbid")

    status: str
    operation: str | None = None
    kind: str | None = None
    value: str | None = None
    values: list[str] = Field(default_factory=list)
    relation_answer: bool | str | None = None
    matched_entities: list[str] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)
    reason: str | None = None
    error_code: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    dimension: str | None = None
    unit: str | None = None
    entity: dict[str, Any] | None = None
    claims: dict[str, Any] | None = None


class PresenterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_message: str
    result: StructuredResult
    conversation_context: list[ConversationSnippet] = Field(default_factory=list)
    language_hint: str | None = None
    technical_question: bool = False


def language_hint(text: str) -> str:
    raw = text or ""
    if re.search(r"[¿¡ñ]|cómo |cuál |llám|se llama|\bllama\b", raw, re.I):
        return "es"
    if re.search(
        r"\b(what|what's|whats|how|where|when|why|is my|are my|do i|does my|my cat|my car)\b",
        raw,
        re.I,
    ):
        return "en"
    return "pt"


def is_technical_question(text: str) -> bool:
    folded = (text or "").casefold()
    markers = (
        "pke",
        "o que está registrado",
        "o que esta registrado",
        "banco de dados",
        "knowledge graph",
        "entidade",
        "canonical",
        "como você armazen",
        "como voce armazen",
        "materializa",
    )
    return any(marker in folded for marker in markers)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        data = dump()
        if isinstance(data, dict):
            return data
    return {}


def _str_values(items: list[Any]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item is None:
            continue
        text = str(item).strip()
        out.append(text)
    return out


def _item_values(items: list[Any]) -> list[str]:
    """Collect item values without truthiness. `0` and `false` stay."""
    out: list[str] = []
    skip = {"yes", "no", "unknown", "true", "false", "relação", "relacao", "atributo"}
    for item in items:
        if not isinstance(item, dict):
            continue
        if "value" not in item:
            continue
        value = item.get("value")
        if value is None:
            continue
        text = str(value).strip()
        if text.casefold() not in skip:
            out.append(text)
    return out


def _item_unit(items: list[Any]) -> str | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        unit = item.get("unit")
        if unit is None:
            continue
        text = str(unit).strip()
        if text:
            return text
    return None


def _matched_names(data: dict[str, Any]) -> list[str]:
    names: list[str] = []
    raw = data.get("matched_entities")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict):
                label = item.get("canonical_name") or item.get("name") or item.get("label")
                if label:
                    names.append(str(label).strip())
    return names


def _relation_answer(data: dict[str, Any]) -> bool | str | None:
    raw = data.get("relation_answer")
    if raw is True:
        return True
    if raw is False:
        return False
    if isinstance(raw, str):
        folded = raw.strip().casefold()
        if folded in {"yes", "true"}:
            return True
        if folded in {"no", "false"}:
            return False
        if folded:
            return folded
    items = data.get("items")
    if isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict):
        raw_item = items[0].get("value")
        value = "" if raw_item is None else str(raw_item).strip().casefold()
        if value == "yes":
            return True
        if value == "no":
            return False
        if value == "unknown":
            return "unknown"
    return None


def _explicit_text(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return "true" if raw else "false"
    return str(raw)


def _entity_payload(data: dict[str, Any]) -> dict[str, Any] | None:
    raw = data.get("entity") or data.get("subject")
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    if raw.get("entity_id"):
        out["entity_id"] = str(raw["entity_id"]).strip()
    name = raw.get("name") or raw.get("canonical_name") or raw.get("label")
    if name is not None and str(name).strip() != "":
        out["name"] = str(name).strip()
    return out or None


def _primary_value(
    *,
    kind: str | None,
    payload_value: Any,
    values: list[str],
    names: list[str],
    relation: bool | str | None,
) -> str | None:
    explicit = _explicit_text(payload_value)
    if kind == "measurement":
        if explicit is not None:
            return explicit
        if values:
            return values[0]
        if names:
            return names[0]
        return None
    if explicit is not None and kind not in {"relation", "absence"}:
        return explicit
    if names and kind != "measurement":
        return names[0]
    if values:
        return values[0]
    if relation is True:
        return "yes"
    if relation is False:
        return "no"
    if isinstance(relation, str):
        return relation
    return None


def _has_knowledge_payload(
    payload: dict[str, Any],
    values: list[str],
    relation: bool | str | None,
) -> bool:
    if relation is True or relation is False:
        return True
    if values:
        return True
    if payload.get("value") is not None:
        return True
    kind = str(payload.get("kind") or "")
    if payload.get("unit") is not None or payload.get("dimension"):
        return kind in {"measurement", "attribute", "state", "intrinsic_property"}
    items = payload.get("items")
    return isinstance(items, list) and any(
        isinstance(item, dict) and item.get("value") is not None for item in items
    )


def from_capability_envelope(
    user_message: str,
    *,
    type_: str | None = None,
    outcome: str | None = None,
    operation: Any = None,
    data: Any = None,
    clarification: Any = None,
    error: Any = None,
    conversation_context: list[ConversationSnippet] | None = None,
) -> PresenterInput:
    op = _as_dict(operation)
    payload = _as_dict(data)
    clar = _as_dict(clarification)
    err = _as_dict(error)
    op_kind = str(op.get("kind") or "") or None
    op_outcome = str(op.get("outcome") or "")
    kind = str(payload.get("kind") or "") or None
    status = str(payload.get("status") or "").strip() or None
    relation = _relation_answer(payload)
    names = _matched_names(payload)
    entity = _entity_payload(payload)
    if entity and entity.get("name") and entity["name"] not in names:
        names = [entity["name"], *names]
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    values = _item_values(items)
    if payload.get("value") is not None:
        explicit_value = _explicit_text(payload.get("value"))
        if explicit_value is not None and explicit_value not in values:
            if kind == "measurement":
                values = [explicit_value, *values]
            elif not values:
                values = [explicit_value]
    unit = payload.get("unit")
    if unit is None:
        unit = _item_unit(items)
    elif unit is not None:
        unit = str(unit).strip() or None
    dimension = payload.get("dimension")
    if dimension is not None:
        dimension = str(dimension).strip() or None
    candidates = _str_values(payload.get("candidates") or [])
    if not candidates:
        options = clar.get("options") if isinstance(clar.get("options"), list) else []
        for option in options:
            if isinstance(option, dict) and option.get("label"):
                candidates.append(str(option["label"]).strip())
            else:
                label = getattr(option, "label", None)
                if label:
                    candidates.append(str(label).strip())

    if not status:
        if outcome == "technical_error" or type_ == "error" or err:
            status = "error"
        elif type_ == "unsupported" or op_outcome == "unsupported":
            status = "unsupported"
        elif type_ == "clarification" or op_outcome == "needs_clarification":
            status = "needs_clarification"
        elif op_outcome in {"committed", "partial", "deferred"}:
            status = op_outcome
        elif type_ == "acknowledgement":
            status = op_outcome or "committed"
        elif relation is False:
            status = "answered"
        elif type_ == "answer" and not payload and op_outcome == "answered":
            status = "no_results"
        else:
            status = "answered"

    if status == "answered" and not payload and type_ == "answer":
        status = "no_results"

    if status == "no_results" and _has_knowledge_payload(payload, values, relation):
        status = "answered"
        if kind == "absence":
            kind = str(payload.get("kind") or "measurement")
            if kind == "absence":
                kind = "measurement" if dimension or unit else "attribute"

    reason = payload.get("reason")
    if isinstance(reason, str) and "insufficient" in reason.casefold():
        status = "insufficient"
    error_code = None
    if err.get("code"):
        error_code = str(err["code"])
    elif payload.get("code"):
        error_code = str(payload["code"])

    claims = payload.get("claims") if isinstance(payload.get("claims"), dict) else None

    result = StructuredResult(
        status=status,
        operation=op_kind,
        kind=kind,
        value=_primary_value(
            kind=kind,
            payload_value=payload.get("value"),
            values=values,
            names=names,
            relation=relation,
        ),
        values=values,
        relation_answer=relation,
        matched_entities=names,
        candidates=candidates,
        reason=str(reason) if reason else None,
        error_code=error_code,
        items=[item for item in items if isinstance(item, dict)],
        dimension=dimension,
        unit=str(unit) if unit is not None else None,
        entity=entity,
        claims=claims,
    )
    return PresenterInput(
        user_message=user_message,
        result=result,
        conversation_context=conversation_context or [],
        language_hint=language_hint(user_message),
        technical_question=is_technical_question(user_message),
    )


def llm_payload(inp: PresenterInput) -> dict[str, Any]:
    result = inp.result
    body: dict[str, Any] = {
        "user_message": inp.user_message,
        "language_hint": inp.language_hint,
        "technical_question": inp.technical_question,
        "structured_result": {
            "status": result.status,
            "operation": result.operation,
            "kind": result.kind,
            "value": result.value,
            "values": result.values,
            "relation_answer": result.relation_answer,
            "matched_entities": result.matched_entities,
            "candidates": result.candidates,
            "reason": result.reason,
            "error_code": result.error_code,
            "items": result.items,
            "dimension": result.dimension,
            "unit": result.unit,
            "entity": result.entity,
            "claims": result.claims,
        },
    }
    if inp.conversation_context:
        body["conversation_context"] = [
            {"role": turn.role, "text": turn.text} for turn in inp.conversation_context[-4:]
        ]
    return body
