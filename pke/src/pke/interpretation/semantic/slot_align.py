"""Translate LLM ficha slots onto PKE execution slots.

Does not re-parse the utterance. Uses only structured proposal fields.
"""

from __future__ import annotations

import re

from pke.interpretation.semantic.attribute_commit import commit_attribute_slots
from pke.interpretation.semantic.attribute_registry import (
    alias_to_dimension_key,
    is_registered_dimension,
)
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal
from pke.interpretation.semantic.multi_primitive_evidence import has_measurement_evidence
from pke.interpretation.semantic.possessive_attribute_repair import (
    SNAPSHOT_EXPRESSION,
    dimension_in_text,
)


def _has_registered_dimension(expr: str) -> bool:
    text = (expr or "").strip()
    if not text or text == SNAPSHOT_EXPRESSION:
        return False
    key = alias_to_dimension_key(text)
    if key and is_registered_dimension(key):
        return True
    return dimension_in_text(text) is not None


def _head_noun(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^(?:o|a|os|as|the)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^(?:meu|minha|meus|minhas|my)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip() or (text or "").strip()


def _rewrite_mention(mention: SemanticEntityMention | None) -> SemanticEntityMention | None:
    if mention is None or mention.reference_kind != "possessive":
        return mention
    head = _head_noun(mention.text)
    if head == mention.text:
        return mention
    return mention.model_copy(update={"text": head})


def _rewrite_list(items: list[SemanticEntityMention]) -> list[SemanticEntityMention]:
    return [_rewrite_mention(item) or item for item in items]


def _has_event_leftovers(proposal: SemanticProposal) -> bool:
    return (
        proposal.change_semantics
        or proposal.primitive_hint == "event"
        or bool(proposal.action_expression)
        or bool(proposal.event_expression)
        or proposal.temporal.occurrence_aspect == "happened"
        or proposal.lifecycle_cue in {"start", "end"}
    )


def align_llm_slots(proposal: SemanticProposal) -> SemanticProposal:
    """Widen-to-narrow: keep possessive, expose the possessed head noun."""
    updated = proposal.model_copy(
        update={
            "subject": _rewrite_mention(proposal.subject),
            "object": _rewrite_mention(proposal.object),
            "context": _rewrite_mention(proposal.context),
            "participants": _rewrite_list(proposal.participants),
            "entities_mentioned": _rewrite_list(proposal.entities_mentioned),
        }
    )
    updated = _align_registered_attribute_over_event(updated)
    return _align_possessive_identity_query(updated)


def _align_registered_attribute_over_event(proposal: SemanticProposal) -> SemanticProposal:
    """Assert with a registered dimension already on the ficha is Attribute.

    LLM often also fills event leftovers (pintar, change, happened). Those
    must not win routing when attribute_expression already names a dimension.
    Does not require a color-word whitelist — the value stays on the slot.
    """
    if proposal.utterance_kind not in {"assert", "change", "describe"}:
        return proposal
    if proposal.correction_semantics or has_measurement_evidence(proposal):
        return proposal
    expression = proposal.attribute_expression or ""
    if not _has_registered_dimension(expression):
        return proposal
    if not _has_event_leftovers(proposal):
        return proposal
    subject = proposal.subject or proposal.object
    if subject is None:
        return proposal
    return commit_attribute_slots(
        proposal,
        utterance_kind="assert",
        subject=subject,
        attribute_expression=expression,
    )


def _align_possessive_identity_query(proposal: SemanticProposal) -> SemanticProposal:
    """LLM often labels 'what is my X?' as TYPE/classification.

    PKE TYPE has no query path; identity of a possessed entity is an
    attribute snapshot of that entity.
    """
    if proposal.utterance_kind != "query":
        return proposal
    subject = proposal.subject
    if subject is None or subject.reference_kind != "possessive":
        return proposal
    if _has_registered_dimension(proposal.attribute_expression or ""):
        return commit_attribute_slots(
            proposal,
            attribute_expression=proposal.attribute_expression or "",
        )
    identity = (
        proposal.classification_semantics
        or proposal.primitive_hint == "type"
        or bool((proposal.attribute_expression or "").strip())
    )
    if not identity:
        return proposal
    return commit_attribute_slots(
        proposal,
        attribute_expression=SNAPSHOT_EXPRESSION,
    )
