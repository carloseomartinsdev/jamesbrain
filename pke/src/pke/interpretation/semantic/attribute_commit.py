"""Commit a ficha translation onto ATTRIBUTE execution slots.

The LLM often fills a competing primitive (relation / event) for the same
utterance. Repair may set primitive_hint=attribute and still leave
relation_expression, action_expression, event_expression, or occurrence
happened on the proposal. PrimitiveRouter ranks those leftovers first, so
the translation never executes.

This helper is the single place that drops competing slots after a
structured translation to Attribute. It does not parse the utterance.
"""

from __future__ import annotations

from typing import Any

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal


def commit_attribute_slots(
    proposal: SemanticProposal,
    *,
    attribute_expression: str,
    subject: SemanticEntityMention | None = None,
    utterance_kind: str | None = None,
    **extra: Any,
) -> SemanticProposal:
    temporal = proposal.temporal
    if temporal.occurrence_aspect == "happened":
        temporal = temporal.model_copy(update={"occurrence_aspect": None})
    cue = proposal.lifecycle_cue
    if cue in {"start", "end"}:
        cue = None
    updates: dict[str, Any] = {
        "primitive_hint": "attribute",
        "stable_property_semantics": True,
        "classification_semantics": False,
        "change_semantics": False,
        "condition_semantics": False,
        "link_semantics": False,
        "measurement_semantics": False,
        "relation_expression": None,
        "action_expression": None,
        "event_expression": None,
        "lifecycle_cue": cue,
        "temporal": temporal,
        "attribute_expression": attribute_expression,
    }
    if subject is not None:
        updates["subject"] = subject
    if utterance_kind is not None:
        updates["utterance_kind"] = utterance_kind
    updates.update(extra)
    return proposal.model_copy(update=updates)
