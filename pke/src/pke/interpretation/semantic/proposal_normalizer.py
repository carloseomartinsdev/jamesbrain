"""Deterministic normalization of raw provider output → semantic proposal envelope."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pke.interpretation.semantic.llm_vocab import (
    coerce_lifecycle_cue,
    coerce_primitive_hint,
    coerce_utterance_kind,
    normalize_entity_dict,
    normalize_time_dict,
)
from pke.interpretation.transport.proposal_wire import WireSemanticProposal


class NormalizationCategory(StrEnum):
    VALID_ENVELOPE = "valid_envelope"
    MARKDOWN_FENCE = "markdown_fence"
    JSON_WITH_PREFIX_SUFFIX = "json_with_prefix_suffix"
    FLAT_PROPOSAL = "flat_proposal"
    ENUM_DRIFT = "enum_drift"
    FIELD_NAME_DRIFT = "field_name_drift"
    EMPTY_RESPONSE = "empty_response"
    NON_JSON_TEXT = "non_json_text"
    MULTIPLE_JSON_OBJECTS = "multiple_json_objects"
    MALFORMED_JSON = "malformed_json"
    CANONICAL_V2_OUTPUT = "canonical_v2_output"
    WRONG_IR_KIND = "wrong_ir_kind"
    OTHER = "other"


@dataclass(frozen=True)
class NormalizationFailure:
    category: NormalizationCategory
    message: str
    notes: tuple[str, ...] = ()


@dataclass
class NormalizationSuccess:
    payload: dict[str, Any]
    categories: list[NormalizationCategory] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw_recovered: bool = False


@dataclass
class NormalizationResult:
    ok: bool
    success: NormalizationSuccess | None = None
    failure: NormalizationFailure | None = None


_PROPOSAL_MARKERS = frozenset(
    {
        "primitive_hint",
        "change_semantics",
        "condition_semantics",
        "link_semantics",
        "stable_property_semantics",
        "classification_semantics",
        "relation_expression",
        "state_expression",
        "action_expression",
        "attribute_expression",
        "event_expression",
        "subject",
        "object",
        "temporal",
    }
)

_IR_KIND_VALUES = frozenset({"semantic_proposal", "semantic_query", "ingest", "query"})
_PROPOSAL_ALLOWED_KEYS = frozenset(WireSemanticProposal.model_fields)
_ENTITY_FIELD_ALIASES = {"expression": "text"}


def _strip_fences(text: str) -> tuple[str, bool]:
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip(), True
    return text, False


def _extract_single_json_object(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Extract exactly one top-level JSON object — no creative repair."""
    text = text.strip()
    if not text:
        return None, "empty"
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed, None
        return None, "not_object"
    except json.JSONDecodeError:
        pass

    starts = [i for i, ch in enumerate(text) if ch == "{"]
    if not starts:
        return None, "no_brace"
    # Only attempt wrapped extraction from the first top-level object opener.
    for start in (starts[0],):
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    fragment = text[start : idx + 1]
                    try:
                        obj = json.loads(fragment)
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict):
                        return obj, None
                    break
    return None, "malformed"


def _lower_enum(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _normalize_entity(entity: object) -> object:
    if not isinstance(entity, dict):
        return entity
    out = dict(entity)
    for old_key, new_key in _ENTITY_FIELD_ALIASES.items():
        if new_key not in out and old_key in out:
            out[new_key] = out.pop(old_key)
    return normalize_entity_dict(out)


def _normalize_proposal_body(body: dict[str, Any], notes: list[str], categories: list[NormalizationCategory]) -> dict[str, Any]:
    out = dict(body)
    if "primitive_hint" not in out and "primitive" in out:
        out["primitive_hint"] = _lower_enum(out.pop("primitive"))
        categories.append(NormalizationCategory.FIELD_NAME_DRIFT)
        notes.append("primitive → primitive_hint")
    if "primitive_hint" in out:
        original = out["primitive_hint"]
        coerced = coerce_primitive_hint(original)
        if coerced != _lower_enum(original):
            categories.append(NormalizationCategory.ENUM_DRIFT)
            notes.append(f"primitive_hint {original!r} → {coerced}")
        out["primitive_hint"] = coerced
    if "utterance_kind" in out:
        original_u = out["utterance_kind"]
        coerced_u = coerce_utterance_kind(original_u)
        if coerced_u != _lower_enum(original_u):
            categories.append(NormalizationCategory.ENUM_DRIFT)
            notes.append(f"utterance_kind {original_u!r} → {coerced_u}")
        out["utterance_kind"] = coerced_u
    if "lifecycle_cue" in out:
        cue = coerce_lifecycle_cue(out["lifecycle_cue"])
        if cue is None:
            out.pop("lifecycle_cue", None)
        else:
            out["lifecycle_cue"] = cue
    for key in ("subject", "object", "context"):
        if key in out:
            out[key] = _normalize_entity(out[key])
    if isinstance(out.get("participants"), list):
        out["participants"] = [_normalize_entity(e) for e in out["participants"]]
    if isinstance(out.get("entities_mentioned"), list):
        out["entities_mentioned"] = [_normalize_entity(e) for e in out["entities_mentioned"]]
    if isinstance(out.get("temporal"), dict):
        out["temporal"] = normalize_time_dict(out["temporal"])
    unknown = [key for key in list(out) if key not in _PROPOSAL_ALLOWED_KEYS]
    if unknown:
        for key in unknown:
            out.pop(key, None)
        categories.append(NormalizationCategory.FIELD_NAME_DRIFT)
        notes.append("dropped unknown proposal fields: " + ",".join(sorted(unknown)))
    return out


def _looks_like_flat_proposal(obj: dict[str, Any]) -> bool:
    if "ir_kind" in obj:
        return False
    return bool(_PROPOSAL_MARKERS & obj.keys())


def _looks_like_v2_canonical(obj: dict[str, Any]) -> bool:
    kind = obj.get("ir_kind")
    if kind not in {"ingest", "query"}:
        return False
    ir = obj.get("ir")
    if not isinstance(ir, dict):
        return False
    if kind == "ingest":
        return "intent" in ir and any(k in ir for k in ("event", "state", "relation", "obligation"))
    return "query" in ir or ir.get("intent") == "query"


def normalize_raw_provider_output(content: str) -> NormalizationResult:
    """Provider-independent deterministic normalization."""
    if content is None or not str(content).strip():
        return NormalizationResult(
            ok=False,
            failure=NormalizationFailure(NormalizationCategory.EMPTY_RESPONSE, "empty provider output"),
        )

    text = str(content).strip()
    categories: list[NormalizationCategory] = []
    notes: list[str] = []
    raw_recovered = False

    stripped, fenced = _strip_fences(text)
    if fenced:
        categories.append(NormalizationCategory.MARKDOWN_FENCE)
        notes.append("extracted JSON from markdown fence")
        raw_recovered = True
        text = stripped

    obj, err = _extract_single_json_object(text)
    if obj is None:
        if err == "multiple":
            return NormalizationResult(
                ok=False,
                failure=NormalizationFailure(
                    NormalizationCategory.MULTIPLE_JSON_OBJECTS,
                    "multiple JSON objects — ambiguous",
                ),
            )
        if err == "empty":
            cat = NormalizationCategory.EMPTY_RESPONSE
        elif err == "no_brace":
            cat = NormalizationCategory.NON_JSON_TEXT
        else:
            cat = NormalizationCategory.MALFORMED_JSON
        return NormalizationResult(ok=False, failure=NormalizationFailure(cat, f"json extract failed: {err}"))

    if text != content.strip() and NormalizationCategory.JSON_WITH_PREFIX_SUFFIX not in categories:
        if not fenced:
            categories.append(NormalizationCategory.JSON_WITH_PREFIX_SUFFIX)
            notes.append("extracted JSON object from wrapped text")
            raw_recovered = True

    payload = dict(obj)

    if _looks_like_v2_canonical(payload):
        categories.append(NormalizationCategory.CANONICAL_V2_OUTPUT)
        return NormalizationResult(
            ok=True,
            success=NormalizationSuccess(
                payload=payload,
                categories=categories,
                notes=notes,
                raw_recovered=raw_recovered,
            ),
        )

    if _looks_like_flat_proposal(payload):
        raw_input = payload.get("raw_input", "")
        body = _normalize_proposal_body(payload, notes, categories)
        payload = {"ir_kind": "semantic_proposal", "ir": body}
        if raw_input and "raw_input" not in body:
            payload["ir"]["raw_input"] = raw_input
        categories.append(NormalizationCategory.FLAT_PROPOSAL)
        notes.append("wrapped flat proposal as semantic_proposal envelope")
        raw_recovered = True

    if "ir_kind" in payload:
        payload["ir_kind"] = _lower_enum(payload["ir_kind"])
        if payload["ir_kind"] not in _IR_KIND_VALUES:
            return NormalizationResult(
                ok=False,
                failure=NormalizationFailure(
                    NormalizationCategory.WRONG_IR_KIND,
                    f"unsupported ir_kind: {payload['ir_kind']}",
                ),
            )
        categories.append(NormalizationCategory.ENUM_DRIFT)

    if payload.get("ir_kind") in {"semantic_proposal", "semantic_query"} and isinstance(payload.get("ir"), dict):
        payload["ir"] = _normalize_proposal_body(payload["ir"], notes, categories)

    if payload.get("ir_kind") in {"semantic_proposal", "semantic_query"}:
        categories.append(NormalizationCategory.VALID_ENVELOPE)

    return NormalizationResult(
        ok=True,
        success=NormalizationSuccess(
            payload=payload,
            categories=categories,
            notes=notes,
            raw_recovered=raw_recovered,
        ),
    )
