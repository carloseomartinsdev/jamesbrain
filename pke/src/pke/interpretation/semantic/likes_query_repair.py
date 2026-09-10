"""Query inventory for likes — subject known, object not required.

Does not re-parse the utterance into new primitives. Uses raw_input / expressions
already on the ficha, with word-boundary tokens (so 'agosto' does not match).
"""

from __future__ import annotations

import re

from pke.interpretation.semantic.aliases import normalize_expression
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

_LIKES_TOKEN = re.compile(
    r"\b(?:gosto|gosta|gostam|likes|curte|adora|adoro|prefiro|prefere|fan|fa)\b",
)
_PLACEHOLDER_OBJECT = frozenset(
    {
        "que",
        "o que",
        "do que",
        "de que",
        "what",
        "which",
    }
)


def is_relation_object_placeholder(mention: SemanticEntityMention | None) -> bool:
    if mention is None:
        return True
    text = normalize_expression(mention.text or "")
    return not text or text in _PLACEHOLDER_OBJECT


def repair_likes_inventory_query(proposal: SemanticProposal) -> SemanticProposal:
    """Open likes question ('do que eu gosto?') → relation ficha without inventing object."""
    if proposal.utterance_kind != "query":
        return proposal
    if proposal.correction_semantics:
        return proposal
    if proposal.measurement_semantics or proposal.measurable_dimension_key:
        return proposal
    if proposal.stable_property_semantics or (
        proposal.attribute_expression and proposal.primitive_hint == "attribute"
    ):
        return proposal

    folded = normalize_expression(proposal.raw_input or "")
    expr = normalize_expression(proposal.relation_expression or "")
    if not (_LIKES_TOKEN.search(folded) or _LIKES_TOKEN.search(expr)):
        return proposal

    updates: dict = {
        "primitive_hint": "relation",
        "link_semantics": True,
        "relation_expression": proposal.relation_expression or "gosto de",
    }
    subject = proposal.subject
    if subject is None or not (subject.text or "").strip():
        updates["subject"] = SemanticEntityMention(
            text="eu",
            kind_hint="person",
            reference_kind="contextual",
            confidence=1.0,
        )
    if is_relation_object_placeholder(proposal.object):
        updates["object"] = None
    return proposal.model_copy(update=updates)
