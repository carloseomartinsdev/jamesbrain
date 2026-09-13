"""Preserve Interpreter class vs instance slots. No linguistic discovery."""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

CLASS_REFERENCE_KIND = "class"
_EXPLICIT_INSTANCE_KINDS = frozenset({"named", "possessive"})


def is_class_reference(mention: SemanticEntityMention | None) -> bool:
    return mention is not None and mention.reference_kind == CLASS_REFERENCE_KIND


def is_explicit_instance_or_class(mention: SemanticEntityMention | None) -> bool:
    if mention is None:
        return False
    return mention.reference_kind in {CLASS_REFERENCE_KIND, *_EXPLICIT_INSTANCE_KINDS}


def iter_mentions(proposal: SemanticProposal) -> list[SemanticEntityMention]:
    found: list[SemanticEntityMention] = []
    for item in (
        proposal.subject,
        proposal.object,
        proposal.context,
        *proposal.participants,
        *proposal.entities_mentioned,
    ):
        if item is not None:
            found.append(item)
    return found


def unique_class_hint(proposal: SemanticProposal) -> str | None:
    hints: list[str] = []
    for mention in iter_mentions(proposal):
        if mention.reference_kind != CLASS_REFERENCE_KIND:
            continue
        hint = (mention.class_hint or "").strip()
        if hint:
            hints.append(hint)
    unique = list(dict.fromkeys(hints))
    return unique[0] if len(unique) == 1 else None


def propagate_class_hints(proposal: SemanticProposal) -> SemanticProposal:
    """Copy a unique class lemma onto named instances that lack class_hint."""
    hint = unique_class_hint(proposal)
    if hint is None:
        return proposal

    def apply(mention: SemanticEntityMention | None) -> SemanticEntityMention | None:
        if mention is None:
            return None
        if mention.reference_kind == CLASS_REFERENCE_KIND:
            return mention
        if mention.class_hint:
            return mention
        if mention.reference_kind != "named":
            return mention
        return mention.model_copy(update={"class_hint": hint})

    return proposal.model_copy(
        update={
            "subject": apply(proposal.subject),
            "object": apply(proposal.object),
            "context": apply(proposal.context),
            "participants": [apply(m) or m for m in proposal.participants],
            "entities_mentioned": [apply(m) or m for m in proposal.entities_mentioned],
        }
    )
