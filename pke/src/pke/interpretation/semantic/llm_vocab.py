"""LLM-facing vocabulary → PKE closed slots.

The provider fills a semantic ficha with a wider everyday lexicon
(possessive, present, automobile, …). Transport must accept those values
and translate them — not reject the payload as schema_invalid.
"""

from __future__ import annotations

import re
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

REFERENCE_KINDS = frozenset({"named", "contextual", "possessive", "class"})
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
    "type": "class",
    "generic": "class",
    "category": "class",
    "class_constraint": "class",
    "type_constraint": "class",
    "entity_type": "class",
    "entity_class": "class",
}
_CLASS_HINT_RE = re.compile(r"[^a-z0-9]+")
_CLASS_HINT_MAX = 48

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

RELATION_TO_REFERENCE = frozenset({"before", "after", "during", "habitual"})
RELATION_TO_REFERENCE_ALIASES = {
    "previous": "before",
    "prior": "before",
    "earlier": "before",
    "later": "after",
    "next": "after",
}

TEMPORAL_SELECTIONS = frozenset({"current", "previous", "first", "last"})
TEMPORAL_SELECTION_ALIASES = {
    "prior": "previous",
    "earliest": "first",
    "oldest": "first",
    "latest": "last",
    "newest": "last",
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


def coerce_class_hint(value: object) -> str | None:
    """Open class lemma from the Interpreter — not a closed kind_hint."""
    text = _lower(value)
    if text is None:
        return None
    cleaned = _CLASS_HINT_RE.sub("_", text).strip("_")
    if not cleaned or not cleaned[0].isalpha():
        return None
    if len(cleaned) > _CLASS_HINT_MAX:
        cleaned = cleaned[:_CLASS_HINT_MAX].rstrip("_")
    return cleaned or None


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


DISCOURSE_DECISIONS = frozenset({"continue", "new_topic", "ambiguous", "none"})
DISCOURSE_DECISION_ALIASES = {
    "follow_up": "continue",
    "followup": "continue",
    "same_topic": "continue",
    "topic_switch": "new_topic",
    "switch": "new_topic",
    "clarify": "ambiguous",
    "unclear": "ambiguous",
}


def coerce_discourse_decision(value: object) -> str | None:
    return coerce_closed(value, DISCOURSE_DECISIONS, DISCOURSE_DECISION_ALIASES, default=None)


def coerce_primitive_hint(value: object) -> str:
    return coerce_closed(value, PRIMITIVE_HINTS, {}, default="unknown") or "unknown"


def coerce_relative_day(value: object) -> str | None:
    return coerce_closed(value, RELATIVE_DAYS, RELATIVE_DAY_ALIASES, default=None)


def coerce_relation_to_reference(value: object) -> str | None:
    return coerce_closed(
        value, RELATION_TO_REFERENCE, RELATION_TO_REFERENCE_ALIASES, default=None
    )


def coerce_temporal_selection(value: object) -> str | None:
    return coerce_closed(value, TEMPORAL_SELECTIONS, TEMPORAL_SELECTION_ALIASES, default=None)


def coerce_lifecycle_cue(value: object) -> str | None:
    return coerce_closed(value, LIFECYCLE_CUES, LIFECYCLE_ALIASES, default=None)


def normalize_entity_dict(entity: dict[str, Any]) -> dict[str, Any]:
    out = dict(entity)
    if "text" not in out and "expression" in out:
        out["text"] = out.pop("expression")
    if "kind_hint" in out:
        raw_hint = out.get("kind_hint")
        hint = coerce_kind_hint(raw_hint)
        if hint is None:
            out.pop("kind_hint", None)
            if not out.get("class_hint"):
                salvaged = coerce_class_hint(raw_hint)
                if salvaged:
                    out["class_hint"] = salvaged
        else:
            out["kind_hint"] = hint
    if "class_hint" in out:
        class_hint = coerce_class_hint(out["class_hint"])
        if class_hint is None:
            out.pop("class_hint", None)
        else:
            out["class_hint"] = class_hint
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
    if "relation_to_reference" in out:
        rel = coerce_relation_to_reference(out["relation_to_reference"])
        if rel is None:
            out.pop("relation_to_reference", None)
        else:
            out["relation_to_reference"] = rel
    if "selection" in out:
        sel = coerce_temporal_selection(out["selection"])
        if sel is None:
            out.pop("selection", None)
        else:
            out["selection"] = sel
    return out
