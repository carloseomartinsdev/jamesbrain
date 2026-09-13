"""Owned-object identity — possessive reference is actor relation, not a class name.

Does not read raw_input. Does not map City/Samsung/MacBook linguistically.
Atomic claims decide which mentions persist as entities; attribute values do not.
"""

from __future__ import annotations

from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticClaimKind,
    SemanticClaimOrigin,
    SemanticEntityMention,
    SemanticProposal,
)
from pke.resolution.self_ref import is_self_lexeme, is_self_semantic_mention

_IDENTITY_KINDS = frozenset(
    {
        SemanticClaimKind.ENTITY,
        SemanticClaimKind.CLASSIFICATION,
        SemanticClaimKind.RELATION,
        SemanticClaimKind.ATTRIBUTE,
        SemanticClaimKind.INTRINSIC_PROPERTY,
        SemanticClaimKind.MEASUREMENT,
        SemanticClaimKind.STATE,
        SemanticClaimKind.EVENT,
    }
)
_SUBJECT_ONLY = frozenset(
    {
        SemanticClaimKind.ATTRIBUTE,
        SemanticClaimKind.INTRINSIC_PROPERTY,
        SemanticClaimKind.MEASUREMENT,
        SemanticClaimKind.STATE,
        SemanticClaimKind.CLASSIFICATION,
        SemanticClaimKind.EVENT,
    }
)


def actor_mention() -> SemanticEntityMention:
    return SemanticEntityMention(
        text="self",
        kind_hint="person",
        reference_kind="contextual",
        confidence=1.0,
    )


def has_explicit_claims(proposal: SemanticProposal) -> bool:
    return any(claim.origin is SemanticClaimOrigin.EXPLICIT for claim in proposal.claims)


def identity_mentions(proposal: SemanticProposal) -> list[SemanticEntityMention]:
    """Mentions that require a persisted entity. Attribute values are excluded.

    With claims: only identity roles on explicit claims.
    Without claims: legacy subject/object/participants/entities_mentioned.
    """
    if not has_explicit_claims(proposal):
        return _legacy_mentions(proposal)
    found: list[SemanticEntityMention] = []
    seen: set[str] = set()

    def add(mention: SemanticEntityMention | None) -> None:
        if mention is None:
            return
        key = mention.text
        if not key or key in seen:
            return
        if _is_value_only(proposal, mention):
            return
        seen.add(key)
        found.append(mention)

    for claim in proposal.claims:
        if claim.origin is not SemanticClaimOrigin.EXPLICIT:
            continue
        if claim.kind not in _IDENTITY_KINDS:
            continue
        if claim.kind in _SUBJECT_ONLY:
            add(claim.subject)
            continue
        if claim.kind is SemanticClaimKind.RELATION:
            add(claim.subject)
            add(claim.object)
            continue
        add(claim.subject or claim.object)
    for mention in (
        proposal.subject,
        proposal.object,
        proposal.context,
        *proposal.participants,
        *proposal.entities_mentioned,
    ):
        if mention is not None and mention.reference_kind == "possessive":
            add(mention)
    return found


def possessive_mentions(proposal: SemanticProposal) -> list[SemanticEntityMention]:
    return [
        mention
        for mention in identity_mentions(proposal)
        if mention.reference_kind == "possessive" and not is_self_semantic_mention(mention)
    ]


def intrinsic_name_for(proposal: SemanticProposal, mention: SemanticEntityMention) -> str | None:
    for claim in proposal.claims:
        if claim.origin is not SemanticClaimOrigin.EXPLICIT:
            continue
        if claim.kind is not SemanticClaimKind.INTRINSIC_PROPERTY:
            continue
        dim = (claim.dimension or claim.predicate or "").strip().lower()
        if dim not in {"name", "canonical_name"}:
            continue
        subject = claim.subject
        if subject is None or subject.text != mention.text:
            continue
        value = (claim.value_key or claim.value_text or "").strip()
        return value or None
    return None


def anonymous_owned_name(type_key: str | None) -> str:
    """Stable-looking placeholder; uniqueness is applied at materialization."""
    slug = (type_key or "thing").rsplit(".", 1)[-1]
    return f"owned:{slug}"


def claims_require_owns(proposal: SemanticProposal) -> bool:
    return any(
        claim.origin is SemanticClaimOrigin.EXPLICIT
        and claim.kind is SemanticClaimKind.RELATION
        and _owns_predicate(claim.predicate)
        for claim in proposal.claims
    )


def _owns_predicate(predicate: str | None) -> bool:
    text = (predicate or "").strip().lower()
    if not text:
        return False
    return text in {"owns", "own", "relation.owns"} or text.endswith(".owns")


def _legacy_mentions(proposal: SemanticProposal) -> list[SemanticEntityMention]:
    found: list[SemanticEntityMention] = []
    seen: set[str] = set()
    for mention in (
        proposal.subject,
        proposal.object,
        proposal.context,
        *proposal.participants,
        *proposal.entities_mentioned,
    ):
        if mention is None or mention.text in seen:
            continue
        seen.add(mention.text)
        found.append(mention)
    return found


def _is_value_only(proposal: SemanticProposal, mention: SemanticEntityMention) -> bool:
    """True when the mention only appears as an attribute/classification value."""
    if mention.reference_kind == "possessive":
        return False
    if is_self_semantic_mention(mention) or is_self_lexeme(mention.text):
        return False
    identity = False
    value_only = False
    for claim in proposal.claims:
        if claim.origin is not SemanticClaimOrigin.EXPLICIT:
            continue
        if _mention_is_identity_role(claim, mention):
            identity = True
        if _mention_is_value(claim, mention):
            value_only = True
    return value_only and not identity


def _mention_is_identity_role(claim: SemanticClaim, mention: SemanticEntityMention) -> bool:
    if claim.kind in _SUBJECT_ONLY:
        return claim.subject is not None and claim.subject.text == mention.text
    if claim.kind is SemanticClaimKind.RELATION:
        return (claim.subject is not None and claim.subject.text == mention.text) or (
            claim.object is not None and claim.object.text == mention.text
        )
    if claim.kind is SemanticClaimKind.ENTITY:
        target = claim.subject or claim.object
        return target is not None and target.text == mention.text
    return False


def _mention_is_value(claim: SemanticClaim, mention: SemanticEntityMention) -> bool:
    token = mention.text.strip()
    if not token:
        return False
    folded = token.casefold()
    if claim.kind is SemanticClaimKind.ATTRIBUTE:
        return (claim.value_text or "").strip().casefold() == folded or (
            claim.value_key or ""
        ).strip().casefold() == folded
    if claim.kind is SemanticClaimKind.CLASSIFICATION:
        return (claim.value_text or "").strip().casefold() == folded
    if claim.kind is SemanticClaimKind.INTRINSIC_PROPERTY:
        return (claim.value_text or "").strip().casefold() == folded
    return False
