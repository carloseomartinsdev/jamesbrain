"""Deterministic vehicle possessive repairs (E1.2) — narrow patterns only."""

from __future__ import annotations

import re
import unicodedata

from pke.interpretation.semantic.attribute_commit import commit_attribute_slots
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

_VEHICLE_ATTR = re.compile(
    r"^\s*meu\s+carro\s+(?:e|é|=)\s+(?:um\s+|uma\s+)?(?P<rest>.+?)\s*\.?\s*$",
    re.IGNORECASE,
)

_COLOR_WORDS = frozenset(
    {
        "prata",
        "silver",
        "branca",
        "branco",
        "white",
        "preto",
        "preta",
        "black",
        "cinza",
        "gray",
        "grey",
        "azul",
        "blue",
        "vermelho",
        "vermelha",
        "red",
    }
)


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold().strip()


def repair_my_car_attribute(proposal: SemanticProposal) -> SemanticProposal:
    """Legacy E1.2 vehicle attribute translation — retired when Atomic Claims exist.

    Does not grow a model lexicon. Does not overwrite a multi-claim proposal.
    """
    if proposal.utterance_kind not in {"assert", "correction"}:
        return proposal
    if proposal.correction_semantics:
        return proposal
    from pke.interpretation.semantic.owned_object import has_explicit_claims

    if has_explicit_claims(proposal):
        return proposal
    raw = (proposal.raw_input or "").strip()
    match = _VEHICLE_ATTR.match(raw)
    if match is None:
        return proposal
    rest = match.group("rest").strip().strip(".,;:!")
    if not rest:
        return proposal

    folded_rest = _fold(rest)
    vehicle = SemanticEntityMention(
        text="carro",
        kind_hint="vehicle",
        reference_kind="contextual",
        confidence=1.0,
    )

    # Color-only
    color_token = folded_rest.split()[0] if folded_rest else ""
    if color_token in _COLOR_WORDS and len(folded_rest.split()) == 1:
        return commit_attribute_slots(
            proposal,
            subject=vehicle,
            attribute_expression=f"cor {color_token}",
            object=None,
        )

    # Brand / brand+model — strip leading articles already handled by regex
    return commit_attribute_slots(
        proposal,
        subject=vehicle,
        attribute_expression=rest,
        object=None,
    )


def repair_my_name_query(proposal: SemanticProposal) -> SemanticProposal:
    """Unequivocal self-name queries → ATTRIBUTE query cues (E1 Patch P1).

    High precision only. Does not invent Knowledge answers.
    Applied before semantic sufficiency gate on the provider path.
    """
    raw = _fold(proposal.raw_input or "")
    raw = re.sub(r"[!?.…]+$", "", raw).strip()
    raw = re.sub(r"[,\s]+james$", "", raw).strip()
    if not raw:
        return proposal

    # Hard negatives — never map third-party / meta / vehicle name queries.
    if re.search(
        r"\b(nome\s+do|nome\s+da|amigo|armazen|artistico|carro|veiculo|usuario|pergunt)\b",
        raw,
    ):
        return proposal

    # Whitelist: whole-utterance self-name questions only.
    allowed = (
        re.compile(r"^qual(?:\s+e)?\s+(?:o\s+)?meu\s+nome$"),
        re.compile(r"^como(?:\s+eu)?\s+me\s+chamo$"),
        re.compile(r"^como(?:\s+e)?\s+(?:o\s+)?meu\s+nome$"),
        re.compile(r"^voce\s+sabe(?:\s+o)?\s+meu\s+nome$"),
    )
    if not any(p.match(raw) for p in allowed):
        return proposal

    return commit_attribute_slots(
        proposal,
        utterance_kind="query",
        subject=SemanticEntityMention(
            text="eu",
            kind_hint="person",
            reference_kind="contextual",
            confidence=1.0,
        ),
        attribute_expression="nome",
    )


def repair_my_car_query(proposal: SemanticProposal) -> SemanticProposal:
    """Vehicle identity fallback — never steals a registry dimension (ano/cor/marca/…)."""
    from pke.interpretation.semantic.possessive_attribute_repair import (
        SNAPSHOT_EXPRESSION,
        dimension_in_text,
    )

    raw = _fold(proposal.raw_input or "")
    if dimension_in_text(raw):
        return proposal
    if (proposal.attribute_expression or "").strip() in {SNAPSHOT_EXPRESSION}:
        return proposal
    if proposal.attribute_expression and proposal.utterance_kind == "query":
        return proposal
    vehicle = SemanticEntityMention(
        text="carro",
        kind_hint="vehicle",
        reference_kind="contextual",
        confidence=1.0,
    )
    if re.search(r"\b(qual|como)\b", raw) and re.search(
        r"\bcor\b.*\bmeu\s+carro\b|\bmeu\s+carro\b.*\bcor\b", raw
    ):
        return commit_attribute_slots(
            proposal,
            utterance_kind="query",
            subject=vehicle,
            attribute_expression="cor",
        )
    if (
        re.search(r"\bqual\b", raw)
        and re.search(r"\bmeu\s+carro\b", raw)
        and "cor" not in raw
        and "marca" not in raw
    ):
        # Identity of a possessed vehicle is a snapshot, not a brand lookup.
        return commit_attribute_slots(
            proposal,
            utterance_kind="query",
            subject=vehicle,
            attribute_expression=SNAPSHOT_EXPRESSION,
        )
    return proposal
