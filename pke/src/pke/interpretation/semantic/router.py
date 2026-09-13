"""PrimitiveRouter — EVENT/STATE/RELATION/ATTRIBUTE/TYPE/MEASUREMENT.

Measurement routing uses measurement_semantics (and related structured cues),
never number+unit lexical shortcuts.

I12.5: Event+Measurement preservation when both evidences are already on the
proposal. Does not invent missing primitives from raw text.
"""

from __future__ import annotations

from pke.interpretation.semantic.models import (
    PrimitiveKind,
    SemanticAssertionFrame,
    SemanticClaimKind,
    SemanticClaimOrigin,
    SemanticProposal,
)
from pke.interpretation.semantic.multi_primitive_evidence import (
    has_explicit_occurrence_evidence,
    has_measurement_evidence,
    is_instrument_reading_report,
)


def _has_measurement_evidence(proposal: SemanticProposal) -> bool:
    return has_measurement_evidence(proposal)


def _assertion_confidence(proposal: SemanticProposal, kind: PrimitiveKind) -> float:
    return proposal.assertion_confidence.get(kind.value, proposal.confidence)


def collect_assertions(proposal: SemanticProposal) -> list[SemanticAssertionFrame]:
    """Explicit multi-primitive propositions from one utterance.

    Distinct from Knowledge Enrichment: each frame requires direct evidence.
    List order is not epistemic priority.

    Single authority for proposal → assertion frames (I12.5).
    """
    if proposal.utterance_kind == "query":
        primary, notes = route_primitive(proposal)
        return [
            SemanticAssertionFrame(
                primitive=primary,
                confidence=_assertion_confidence(proposal, primary),
                notes=notes,
            )
        ]

    has_m = _has_measurement_evidence(proposal)
    has_e = has_explicit_occurrence_evidence(proposal)

    # Event + Measurement: both already explicit on the proposal — preserve both.
    if has_e and has_m:
        return [
            SemanticAssertionFrame(
                primitive=PrimitiveKind.EVENT,
                confidence=_assertion_confidence(proposal, PrimitiveKind.EVENT),
                notes=["explicit occurrence evidence → EVENT"],
            ),
            SemanticAssertionFrame(
                primitive=PrimitiveKind.MEASUREMENT,
                confidence=_assertion_confidence(proposal, PrimitiveKind.MEASUREMENT),
                notes=["explicit quantitative result → MEASUREMENT"],
            ),
        ]

    primary, notes = route_primitive(proposal)
    frames = [
        SemanticAssertionFrame(
            primitive=primary,
            confidence=_assertion_confidence(proposal, primary),
            notes=list(notes),
        )
    ]
    # Measurement companion: primary routing must not drop an explicit quantitative claim.
    # Attribute/relation companions are overlaid from proposal.claims (not extra frames)
    # so execution_readiness is not downgraded by unresolved sibling concepts.
    if has_m and primary is not PrimitiveKind.MEASUREMENT:
        frames.append(
            SemanticAssertionFrame(
                primitive=PrimitiveKind.MEASUREMENT,
                confidence=_assertion_confidence(proposal, PrimitiveKind.MEASUREMENT),
                notes=["explicit quantitative result → MEASUREMENT"],
            )
        )
    return frames


def route_primitive(proposal: SemanticProposal) -> tuple[PrimitiveKind, list[str]]:
    """Primary primitive for backward-compatible single-primitive pipeline.

    For Event+Measurement, returns EVENT while collect_assertions retains both.
    """
    notes: list[str] = []

    if proposal.utterance_kind == "query":
        notes.append("query utterance — primitive resolved downstream")
        if proposal.link_semantics or proposal.relation_expression:
            return PrimitiveKind.RELATION, notes
        if proposal.classification_semantics:
            notes.append("classification query → TYPE (not Attribute)")
            return PrimitiveKind.TYPE, notes
        if _has_measurement_evidence(proposal):
            notes.append("measurement query → MEASUREMENT")
            return PrimitiveKind.MEASUREMENT, notes
        if proposal.stable_property_semantics or (
            proposal.attribute_expression and not proposal.condition_semantics
        ):
            notes.append("stable property query → ATTRIBUTE")
            return PrimitiveKind.ATTRIBUTE, notes
        if any(
            claim.kind is SemanticClaimKind.ATTRIBUTE
            and claim.origin is SemanticClaimOrigin.EXPLICIT
            for claim in proposal.claims
        ):
            notes.append("attribute claim → ATTRIBUTE")
            return PrimitiveKind.ATTRIBUTE, notes
        if proposal.condition_semantics or proposal.state_expression:
            return PrimitiveKind.STATE, notes
        return PrimitiveKind.EVENT, notes

    # I12.5: occurrence + measurement already on proposal → EVENT primary (both in assertions).
    if has_explicit_occurrence_evidence(proposal) and _has_measurement_evidence(proposal):
        notes.append("occurrence + measurement evidence → EVENT primary (multi)")
        notes.append("also explicit Measurement evidence (see assertions)")
        return PrimitiveKind.EVENT, notes

    if proposal.change_semantics or proposal.lifecycle_cue in {"start", "end"}:
        if (
            proposal.link_semantics
            and proposal.relation_expression
            and not proposal.change_semantics
            and not proposal.action_expression
            and not proposal.event_expression
        ):
            notes.append("lifecycle cue on link without occurrence → RELATION")
            return PrimitiveKind.RELATION, notes
        if proposal.link_semantics and proposal.relation_expression:
            notes.append("change + link — occurrence/change over relation")
        notes.append("change/lifecycle semantics → EVENT")
        if _has_measurement_evidence(proposal):
            notes.append("also explicit Measurement evidence (see assertions)")
        return PrimitiveKind.EVENT, notes

    if proposal.temporal.occurrence_aspect == "happened" and (
        proposal.action_expression or proposal.event_expression
    ):
        if is_instrument_reading_report(proposal):
            notes.append("instrument reading report — not user occurrence Event")
        else:
            notes.append("happened aspect + action/event expression → EVENT")
            if _has_measurement_evidence(proposal):
                notes.append("also explicit Measurement evidence (see assertions)")
            return PrimitiveKind.EVENT, notes

    if proposal.link_semantics or proposal.relation_expression:
        if proposal.change_semantics:
            notes.append("link with change — EVENT preferred")
            return PrimitiveKind.EVENT, notes
        notes.append("link semantics → RELATION")
        return PrimitiveKind.RELATION, notes

    if proposal.classification_semantics:
        notes.append("classification semantics → TYPE (not Attribute)")
        return PrimitiveKind.TYPE, notes

    if proposal.stable_property_semantics or (
        proposal.attribute_expression
        and not proposal.condition_semantics
        and not _has_measurement_evidence(proposal)
    ):
        notes.append("stable property → ATTRIBUTE")
        return PrimitiveKind.ATTRIBUTE, notes

    if _has_measurement_evidence(proposal):
        notes.append("measurement_semantics → MEASUREMENT")
        return PrimitiveKind.MEASUREMENT, notes

    if proposal.condition_semantics or proposal.temporal.occurrence_aspect == "ongoing":
        if proposal.attribute_expression and not proposal.state_expression:
            notes.append("ongoing stable attribute → ATTRIBUTE")
            return PrimitiveKind.ATTRIBUTE, notes
        notes.append("condition/ongoing → STATE")
        return PrimitiveKind.STATE, notes

    if proposal.action_expression or proposal.event_expression:
        if is_instrument_reading_report(proposal):
            notes.append("instrument reading — defer; no standalone Event")
        else:
            notes.append("residual action/event expression → EVENT")
            return PrimitiveKind.EVENT, notes

    if proposal.state_expression:
        notes.append("residual state expression → STATE")
        return PrimitiveKind.STATE, notes

    if proposal.primitive_hint != "unknown":
        notes.append(f"fallback to LLM primitive_hint={proposal.primitive_hint}")
        try:
            return PrimitiveKind(proposal.primitive_hint), notes
        except ValueError:
            notes.append("invalid primitive_hint")
            return PrimitiveKind.UNKNOWN, notes

    notes.append("insufficient semantic signals")
    return PrimitiveKind.UNKNOWN, notes
