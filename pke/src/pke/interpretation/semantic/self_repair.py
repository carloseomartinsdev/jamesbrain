"""Deterministic self / name-misparse repair (E1.1). Prompt tuning is secondary (D-E1-12)."""

from __future__ import annotations

import re
import unicodedata

from pke.interpretation.semantic.attribute_commit import commit_attribute_slots
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal
from pke.interpretation.semantic.slot_align import align_llm_slots
from pke.resolution.normalize import normalize_lexical

_NAME_SELF_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^\s*meu\s+nome\s+(?:e|é|=)\s+(?P<value>.+?)\s*\.?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*eu\s+me\s+chamo\s+(?P<value>.+?)\s*\.?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*me\s+chamo\s+(?P<value>.+?)\s*\.?\s*$",
        re.IGNORECASE,
    ),
)


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold().strip()


def _extract_self_name_value(raw: str) -> str | None:
    text = (raw or "").strip()
    for pattern in _NAME_SELF_PATTERNS:
        match = pattern.match(text)
        if match:
            value = match.group("value").strip().strip(".,;:!")
            return value or None
    return None


def repair_self_name_misparse(proposal: SemanticProposal) -> SemanticProposal:
    """Repair 'Meu nome é X' when Interpreter placed X as named subject.

    Does not rewrite event-like first person ('Eu vi Carlos').
    Does not invent Attribute dimension materialization (E1.2).
    """
    if proposal.utterance_kind not in {"assert", "correction", "describe", "change", "none"}:
        return proposal
    if proposal.correction_semantics:
        return proposal
    value = _extract_self_name_value(proposal.raw_input or "")
    if value is None:
        return proposal

    # Reject friend / third-party name patterns already excluded by regex,
    # but also require attribute-ish signals when present.
    expr = _fold(proposal.attribute_expression or "")
    primitive_ok = proposal.primitive_hint in {None, "unknown", "attribute", "event"}
    attr_ok = (
        proposal.stable_property_semantics
        or "name" in expr
        or "nome" in expr
        or not proposal.attribute_expression
    )
    if not primitive_ok or not attr_ok:
        return proposal

    subject = proposal.subject
    expression = proposal.attribute_expression or f"name is {value}"
    if subject is None:
        return commit_attribute_slots(
            proposal,
            utterance_kind="assert",
            subject=SemanticEntityMention(
                text="eu",
                kind_hint="person",
                reference_kind="contextual",
                confidence=1.0,
            ),
            attribute_expression=expression,
        )

    # Already contextual self — keep, ensure attribute expression carries value.
    if subject.reference_kind == "contextual":
        return commit_attribute_slots(
            proposal,
            utterance_kind="assert",
            attribute_expression=expression,
        )

    # Misparse: named subject equals the name value.
    if subject.reference_kind == "named" and normalize_lexical(subject.text) == normalize_lexical(
        value
    ):
        return commit_attribute_slots(
            proposal,
            utterance_kind="assert",
            subject=SemanticEntityMention(
                text="eu",
                kind_hint="person",
                reference_kind="contextual",
                confidence=1.0,
            ),
            attribute_expression=expression,
        )

    return proposal


def apply_e1_self_repairs(
    proposal: SemanticProposal,
    *,
    prior_utterances: list[str] | tuple[str, ...] = (),
) -> SemanticProposal:
    """Ordered deterministic repairs for E1 — narrow, non-heuristic stack."""
    from pke.interpretation.semantic.likes_query_repair import repair_likes_inventory_query
    from pke.interpretation.semantic.possessive_attribute_repair import (
        repair_possessive_attributes,
    )
    from pke.interpretation.semantic.vehicle_repair import (
        repair_my_car_attribute,
        repair_my_car_query,
        repair_my_name_query,
    )

    proposal = align_llm_slots(proposal)
    proposal = repair_self_name_misparse(proposal)
    proposal = repair_my_name_query(proposal)
    proposal = repair_possessive_attributes(proposal, prior_utterances=prior_utterances)
    proposal = repair_my_car_attribute(proposal)
    proposal = repair_my_car_query(proposal)
    proposal = repair_likes_inventory_query(proposal)
    return proposal
