"""LLM-facing vocabulary → PKE closed slots.

The provider fills a semantic ficha with a wider everyday lexicon
(possessive, present, automobile, …). Transport must accept those values
and translate them — not reject the payload as schema_invalid.
"""

from __future__ import annotations

from typing import Any

KIND_HINTS = frozenset(
    {
        "person",
        "organization",
        "place",
        "thing",
        "appliance",
        "vehicle",
        "document",
        "medication",
        "unknown",
    }
)
KIND_HINT_ALIASES = {
    "automobile": "vehicle",
    "car": "vehicle",
    "org": "organization",
    "company": "organization",
    "people": "person",
    "human": "person",
    "location": "place",
    "object": "thing",
    "item": "thing",
}

REFERENCE_KINDS = frozenset({"named", "contextual", "possessive"})
REFERENCE_KIND_ALIASES = {
    "owned": "possessive",
    "my": "possessive",
    "mine": "possessive",
    "genitive": "possessive",
    "explicit": "named",
    "specific": "named",
    "proper": "named",
    "proper_name": "named",
    "pronoun": "contextual",
    "anaphor": "contextual",
    "anaphora": "contextual",
    "self": "contextual",
    "deictic": "contextual",
}

OCCURRENCE_ASPECTS = frozenset({"happened", "ongoing", "planned", "habitual"})
OCCURRENCE_ALIASES = {
    "present": "ongoing",
    "now": "ongoing",
    "current": "ongoing",
    "present_tense": "ongoing",
    "past": "happened",
    "future": "planned",
}

UTTERANCE_KINDS = frozenset({"assert", "describe", "change", "query", "correct", "none"})
UTTERANCE_ALIASES = {
    "question": "query",
    "ask": "query",
    "interrogative": "query",
    "statement": "assert",
}

PRIMITIVE_HINTS = frozenset(
    {"event", "state", "relation", "attribute", "type", "measurement", "unknown"}
)

RELATIVE_DAYS = frozenset({"today", "yesterday", "tomorrow"})
RELATIVE_DAY_ALIASES = {
    "hoje": "today",
    "ontem": "yesterday",
    "amanha": "tomorrow",
    "amanhã": "tomorrow",
}

LIFECYCLE_CUES = frozenset({"start", "end", "ongoing", "deny", "none"})
LIFECYCLE_ALIASES = {
    "begin": "start",
    "stop": "end",
    "continue": "ongoing",
    "no": "deny",
}


def _lower(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text or None


def coerce_closed(
    value: object,
    allowed: frozenset[str],
    aliases: dict[str, str],
    *,
    default: str | None = None,
) -> str | None:
    text = _lower(value)
    if text is None:
        return default
    if text in allowed:
        return text
    mapped = aliases.get(text)
    if mapped is not None:
        return mapped
    return default


def coerce_kind_hint(value: object) -> str | None:
    return coerce_closed(value, KIND_HINTS, KIND_HINT_ALIASES, default=None)


def coerce_reference_kind(value: object) -> str:
    text = _lower(value)
    if text is None:
        return "named"
    if text in REFERENCE_KINDS:
        return text
    mapped = REFERENCE_KIND_ALIASES.get(text)
    if mapped is not None:
        return mapped
    return "contextual"


def coerce_occurrence_aspect(value: object) -> str | None:
    return coerce_closed(value, OCCURRENCE_ASPECTS, OCCURRENCE_ALIASES, default=None)


def coerce_utterance_kind(value: object) -> str:
    return coerce_closed(value, UTTERANCE_KINDS, UTTERANCE_ALIASES, default="assert") or "assert"


def coerce_primitive_hint(value: object) -> str:
    return coerce_closed(value, PRIMITIVE_HINTS, {}, default="unknown") or "unknown"


def coerce_relative_day(value: object) -> str | None:
    return coerce_closed(value, RELATIVE_DAYS, RELATIVE_DAY_ALIASES, default=None)


def coerce_lifecycle_cue(value: object) -> str | None:
    return coerce_closed(value, LIFECYCLE_CUES, LIFECYCLE_ALIASES, default=None)


def normalize_entity_dict(entity: dict[str, Any]) -> dict[str, Any]:
    out = dict(entity)
    if "text" not in out and "expression" in out:
        out["text"] = out.pop("expression")
    if "kind_hint" in out:
        hint = coerce_kind_hint(out["kind_hint"])
        if hint is None:
            out.pop("kind_hint", None)
        else:
            out["kind_hint"] = hint
    if "reference_kind" in out:
        out["reference_kind"] = coerce_reference_kind(out["reference_kind"])
    return out


def normalize_time_dict(temporal: dict[str, Any]) -> dict[str, Any]:
    out = dict(temporal)
    if "occurrence_aspect" in out:
        aspect = coerce_occurrence_aspect(out["occurrence_aspect"])
        if aspect is None:
            out.pop("occurrence_aspect", None)
        else:
            out["occurrence_aspect"] = aspect
    if "relative_day" in out:
        day = coerce_relative_day(out["relative_day"])
        if day is None:
            out.pop("relative_day", None)
        else:
            out["relative_day"] = day
    return out
