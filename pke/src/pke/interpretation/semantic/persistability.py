"""Persistability — validity vs completeness for partial canonical IR."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pke.interpretation.semantic.models import (
    PrimitiveKind,
    ResolutionResult,
    ResolutionStatus,
    SemanticProposal,
    ResolvedConcepts,
)
from pke.interpretation.semantic.multi_primitive_evidence import has_explicit_occurrence_evidence
from pke.interpretation.transport.catalog import ConceptCatalog


class PersistabilityStatus(StrEnum):
    FULLY_RESOLVED = "fully_resolved"
    PARTIALLY_RESOLVED_PERSISTABLE = "partially_resolved_persistable"
    PARTIALLY_RESOLVED_NONPERSISTABLE = "partially_resolved_nonpersistable"
    UNSAFE = "unsafe"


@dataclass(frozen=True)
class PersistabilityAssessment:
    wire_allowed: bool
    status: PersistabilityStatus
    critical_unresolved: tuple[str, ...] = ()
    noncritical_unresolved: tuple[str, ...] = ()
    semantic_anchors: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()



def _event_anchors(concepts: ResolvedConcepts, proposal: SemanticProposal) -> tuple[str, ...]:
    found: list[str] = []
    if concepts.action and concepts.action in ConceptCatalog.actions:
        found.append("action")
    if concepts.event_type and concepts.event_type in ConceptCatalog.event_types:
        found.append("event_type")
    if proposal.subject or proposal.object or proposal.participants or proposal.entities_mentioned:
        found.append("entity_context")
    if proposal.action_expression or proposal.event_expression:
        found.append("expression")
    return tuple(found)


def _compositional_event_identity(anchors: tuple[str, ...]) -> bool:
    """Occurrence + expression + entity context — partial Event identity without catalog keys."""
    return "expression" in anchors and "entity_context" in anchors


def _deny(reason: str, *, critical: tuple[str, ...] = ()) -> PersistabilityAssessment:
    return PersistabilityAssessment(
        wire_allowed=False,
        status=PersistabilityStatus.PARTIALLY_RESOLVED_NONPERSISTABLE,
        critical_unresolved=critical or (reason,),
        notes=(reason,),
    )


def assess_persistability(result: ResolutionResult) -> PersistabilityAssessment:
    """Primitive-specific minimum persistable knowledge — no semantic invention."""
    concepts = result.concepts
    primitive = result.primitive
    proposal = result.proposal

    if primitive is PrimitiveKind.UNKNOWN:
        return _deny("unknown_primitive")

    if concepts.resolution_status in {ResolutionStatus.BLOCKED, ResolutionStatus.AMBIGUOUS}:
        return PersistabilityAssessment(
            wire_allowed=False,
            status=PersistabilityStatus.UNSAFE,
            critical_unresolved=("blocked_or_ambiguous",),
            notes=(f"status={concepts.resolution_status.value}",),
        )

    if concepts.ontology_gap:
        return PersistabilityAssessment(
            wire_allowed=False,
            status=PersistabilityStatus.PARTIALLY_RESOLVED_NONPERSISTABLE,
            critical_unresolved=("ontology_gap",),
            notes=("ontology_gap", *tuple(concepts.notes)),
        )

    if primitive is PrimitiveKind.STATE:
        return _assess_state(concepts, proposal)

    if primitive is PrimitiveKind.RELATION:
        return _assess_relation(concepts, proposal)

    if primitive is PrimitiveKind.EVENT:
        return _assess_event(concepts, proposal)

    if primitive is PrimitiveKind.ATTRIBUTE:
        return _assess_attribute(concepts, proposal)

    if primitive is PrimitiveKind.TYPE:
        return _deny(
            "classification_not_materializable",
            critical=("classification",),
        )

    if primitive is PrimitiveKind.MEASUREMENT:
        from pke.interpretation.semantic.measurement_resolution import resolve_measurement_value

        measured = resolve_measurement_value(proposal)
        subject = proposal.subject or proposal.object
        if measured is None:
            return _deny(
                "measurement_dimension_value_required",
                critical=("measurement_dimension", "measurement_value"),
            )
        if subject is None:
            return _deny(
                "measurement_entity_required",
                critical=("entity",),
            )
        status = (
            PersistabilityStatus.FULLY_RESOLVED
            if not concepts.unresolved
            else PersistabilityStatus.PARTIALLY_RESOLVED_PERSISTABLE
        )
        return PersistabilityAssessment(
            wire_allowed=True,
            status=status,
            semantic_anchors=("measurement_dimension", "measurement_value", "entity"),
            notes=tuple(concepts.notes),
        )

    return _deny("unsupported_primitive")


def _attribute_surface_incomplete(proposal: SemanticProposal) -> bool:
    """True when the user left an incomplete value cue (unlockable by more text)."""
    import re

    expr = (proposal.attribute_expression or "").strip()
    raw = (proposal.raw_input or "").strip()
    if not expr and not raw:
        return True
    if expr in {"", "...", "…"} or expr.endswith("...") or expr.endswith("…"):
        return True
    if re.search(
        r"(?:meu\s+carro|minha\s+moto|meu\s+ve[ií]culo)\s+(?:e|é|=)\s*(?:\.{0,3}|…)?\s*$",
        raw,
        flags=re.IGNORECASE,
    ):
        return True
    if re.search(r"(?:e|é|=)\s*(?:\.{2,}|…)\s*$", raw, flags=re.IGNORECASE):
        return True
    if re.search(r"(?:e|é|=)\s*$", raw, flags=re.IGNORECASE) and len(raw.split()) <= 4:
        return True
    return False


def _assess_attribute(
    concepts: ResolvedConcepts, proposal: SemanticProposal
) -> PersistabilityAssessment:
    """Distinguish user value gaps (clarify) from known unsupported dimensions."""
    from pke.interpretation.semantic.learned_attribute import structured_attribute_claim

    if concepts.attribute_dimension_key and concepts.attribute_value_kind:
        status = (
            PersistabilityStatus.FULLY_RESOLVED
            if not concepts.unresolved
            else PersistabilityStatus.PARTIALLY_RESOLVED_PERSISTABLE
        )
        return PersistabilityAssessment(
            wire_allowed=True,
            status=status,
            semantic_anchors=("attribute_dimension", "attribute_value"),
            notes=tuple(concepts.notes),
        )

    claimed = structured_attribute_claim(proposal, learn=True)
    if claimed is not None:
        identity, _claim = claimed
        return PersistabilityAssessment(
            wire_allowed=True,
            status=PersistabilityStatus.FULLY_RESOLVED,
            semantic_anchors=("attribute_dimension", "attribute_value"),
            notes=(f"attribute dimension={identity.key} source={identity.source}",),
        )

    if concepts.attribute_dimension_key and not concepts.attribute_value_kind:
        return _deny("attribute_value_required", critical=("attribute_value",))

    if concepts.ontology_gap or concepts.safe_abstention:
        # Resolver already marked known non-materializable Attribute semantics.
        # Prefer unsupported over clarify when surface is not an incomplete cue.
        if _attribute_surface_incomplete(proposal):
            return _deny("attribute_value_required", critical=("attribute_value",))
        return _deny(
            "unsupported_attribute_dimension",
            critical=("attribute_dimension",),
        )

    if _attribute_surface_incomplete(proposal):
        return _deny("attribute_value_required", critical=("attribute_value",))

    expr = (proposal.attribute_expression or "").strip()
    if expr:
        return _deny(
            "unsupported_attribute_dimension",
            critical=("attribute_dimension",),
        )
    return _deny(
        "attribute_dimension_value_required",
        critical=("attribute_dimension", "attribute_value"),
    )


def _assess_state(
    concepts: ResolvedConcepts, proposal: SemanticProposal
) -> PersistabilityAssessment:
    if not concepts.state_value or concepts.state_value not in ConceptCatalog.state_values:
        # Present expression that failed CORE alias resolution is not a missing-value clarify.
        if (proposal.state_expression or "").strip():
            return _deny(
                "state_value_canonical_unresolved",
                critical=("state_value",),
            )
        return _deny("state_value_required", critical=("state_value",))
    if concepts.unresolved and not concepts.state_value:
        return _deny("state_identity_incomplete", critical=("state_value",))
    status = (
        PersistabilityStatus.FULLY_RESOLVED
        if not concepts.unresolved
        else PersistabilityStatus.PARTIALLY_RESOLVED_PERSISTABLE
    )
    noncritical: list[str] = []
    if concepts.unresolved and not concepts.state_dimension:
        noncritical.append("state_dimension")
    return PersistabilityAssessment(
        wire_allowed=True,
        status=status,
        noncritical_unresolved=tuple(noncritical),
        semantic_anchors=("state_value",),
    )


def _assess_relation(concepts: ResolvedConcepts, proposal: SemanticProposal) -> PersistabilityAssessment:
    # Complete link whose expression still has no catalog key (slug failed):
    # not an endpoint CLARIFY (I12.16). Missing endpoint → clarify that slot.
    if not concepts.relation_type or concepts.relation_type not in ConceptCatalog.relation_types:
        if (
            (proposal.relation_expression or "").strip()
            and proposal.subject is not None
            and proposal.object is not None
        ):
            return _deny(
                "relation_type_canonical_unresolved",
                critical=("relation_type",),
            )
    critical: list[str] = []
    if not concepts.relation_type or concepts.relation_type not in ConceptCatalog.relation_types:
        critical.append("relation_type")
    if proposal.subject is None:
        critical.append("subject")
    if proposal.object is None:
        critical.append("object")
    if critical:
        return PersistabilityAssessment(
            wire_allowed=False,
            status=PersistabilityStatus.PARTIALLY_RESOLVED_NONPERSISTABLE,
            critical_unresolved=tuple(critical),
            notes=("relation_identity_incomplete",),
        )
    status = (
        PersistabilityStatus.FULLY_RESOLVED
        if not concepts.unresolved
        else PersistabilityStatus.PARTIALLY_RESOLVED_PERSISTABLE
    )
    return PersistabilityAssessment(
        wire_allowed=True,
        status=status,
        semantic_anchors=("relation_type", "subject", "object"),
    )


def _assess_event(concepts: ResolvedConcepts, proposal: SemanticProposal) -> PersistabilityAssessment:
    if not has_explicit_occurrence_evidence(proposal):
        return _deny("event_occurrence_required", critical=("occurrence",))

    anchors = _event_anchors(concepts, proposal)
    if not anchors:
        return _deny("event_semantic_anchor_required", critical=("semantic_anchor",))

    if concepts.safe_abstention and not (
        concepts.action or concepts.event_type
    ):
        return _deny("safe_abstention_without_anchor")

    noncritical: list[str] = []
    critical: list[str] = []
    if concepts.unresolved:
        if not concepts.action:
            noncritical.append("action")
        if not concepts.event_type:
            noncritical.append("event_type")
        if not concepts.action and not concepts.event_type:
            if not _compositional_event_identity(anchors):
                critical.extend(("action", "event_type"))

    if critical:
        return PersistabilityAssessment(
            wire_allowed=False,
            status=PersistabilityStatus.PARTIALLY_RESOLVED_NONPERSISTABLE,
            critical_unresolved=tuple(critical),
            semantic_anchors=anchors,
            notes=("event_identity_incomplete",),
        )

    wire_type = event_type_for_wire(concepts, proposal)
    if wire_type is None and _compositional_event_identity(anchors):
        return PersistabilityAssessment(
            wire_allowed=False,
            status=PersistabilityStatus.PARTIALLY_RESOLVED_NONPERSISTABLE,
            noncritical_unresolved=tuple(noncritical),
            semantic_anchors=anchors,
            notes=("event_category_unresolved_safe_partial",),
        )

    if wire_type is None:
        return PersistabilityAssessment(
            wire_allowed=False,
            status=PersistabilityStatus.PARTIALLY_RESOLVED_NONPERSISTABLE,
            noncritical_unresolved=tuple(noncritical),
            semantic_anchors=anchors,
            notes=("event_type_unresolved",),
        )

    status = (
        PersistabilityStatus.FULLY_RESOLVED
        if not concepts.unresolved and not noncritical
        else PersistabilityStatus.PARTIALLY_RESOLVED_PERSISTABLE
    )
    return PersistabilityAssessment(
        wire_allowed=True,
        status=status,
        noncritical_unresolved=tuple(noncritical),
        semantic_anchors=anchors,
        notes=tuple(concepts.notes),
    )


def _proposal_has_vehicle(proposal: SemanticProposal) -> bool:
    mentions = [
        proposal.subject,
        proposal.object,
        *proposal.participants,
        *proposal.entities_mentioned,
    ]
    return any(
        m is not None and m.kind_hint in {"vehicle", "automobile"}
        for m in mentions
    )


def event_type_for_wire(concepts: ResolvedConcepts, proposal: SemanticProposal) -> str | None:
    """Safe canonical event type for wire — never generic/false fallback (I12.7.1)."""
    event_type = concepts.event_type
    if event_type == "event.vehicle_maintenance" and not _proposal_has_vehicle(proposal):
        event_type = "event.maintenance"
    if event_type and event_type in ConceptCatalog.event_types:
        return event_type
    if concepts.action and concepts.action in ConceptCatalog.actions:
        if "event.maintenance" in ConceptCatalog.event_types:
            return "event.maintenance"
    return None
