"""I11.14 — Cross-primitive semantic audit harness."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pke.interpretation.semantic.models import PrimitiveKind, ResolutionStatus, SemanticProposal
from pke.interpretation.semantic.persistability import (
    PersistabilityAssessment,
    PersistabilityStatus,
    assess_persistability,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.semantic.router import route_primitive


class InformationLoss(StrEnum):
    NONE = "none"
    NON_CRITICAL = "non_critical"
    CRITICAL = "critical"


class GapKind(StrEnum):
    NONE = "none"
    ONTOLOGY = "ontology"
    REPRESENTATION = "representation"
    TEMPORAL = "temporal"
    QUERY = "query"
    MEASUREMENT = "measurement"
    CORRECTION = "correction"
    SAFE_UNRESOLVED = "safe_unresolved"
    SAFE_PARTIAL = "safe_partial"


@dataclass(frozen=True)
class CorpusCase:
    id: str
    factory: object  # Callable[[], SemanticProposal]
    expected_primitive: PrimitiveKind
    forbid: tuple[PrimitiveKind, ...] = ()
    allow_unresolved_persist: bool = False
    must_not_wire: bool = False
    gap: GapKind = GapKind.NONE
    notes: str = ""
    category: str = "mandatory"


@dataclass(frozen=True)
class AuditOutcome:
    case_id: str
    routed: PrimitiveKind
    expected: PrimitiveKind
    false_collapse: bool
    persist: PersistabilityAssessment
    wire_ir: bool
    concepts_status: ResolutionStatus
    ontology_gap: bool
    safe_abstention: bool
    attribute_dimension: str | None
    state_dimension: str | None
    state_value: str | None
    action: str | None
    relation_type: str | None
    information_loss: InformationLoss
    gap: GapKind
    notes: tuple[str, ...]


def audit_case(case: CorpusCase) -> AuditOutcome:
    proposal: SemanticProposal = case.factory()  # type: ignore[operator]
    routed, route_notes = route_primitive(proposal)
    result = resolve_proposal(proposal)
    concepts = result.concepts
    assessment = assess_persistability(result)
    outcome = proposal_to_canonical_ir(proposal)
    wire_ir = outcome.ir is not None

    false = routed is not case.expected_primitive
    if false and case.expected_primitive is PrimitiveKind.UNKNOWN:
        false = False  # audit accepts any safe route when expected unknown

    # Forbidden primitive collapse (even if expected matches elsewhere)
    for forbidden in case.forbid:
        if routed is forbidden:
            false = True

    info_loss = InformationLoss.NONE
    if routed is PrimitiveKind.EVENT and not (concepts.action or proposal.action_expression):
        info_loss = InformationLoss.NON_CRITICAL
    if routed is PrimitiveKind.ATTRIBUTE and wire_ir is False and not case.allow_unresolved_persist:
        if concepts.attribute_dimension_key is None and case.expected_primitive is PrimitiveKind.ATTRIBUTE:
            info_loss = InformationLoss.NON_CRITICAL
    if routed is PrimitiveKind.RELATION and proposal.object is None:
        info_loss = InformationLoss.CRITICAL
    if routed is PrimitiveKind.EVENT and proposal.change_semantics and not (
        proposal.subject or proposal.object or proposal.entities_mentioned
    ):
        info_loss = InformationLoss.CRITICAL

    gap = case.gap
    if concepts.ontology_gap:
        gap = GapKind.ONTOLOGY
    elif assessment.status is PersistabilityStatus.PARTIALLY_RESOLVED_NONPERSISTABLE:
        if gap is GapKind.NONE:
            gap = GapKind.SAFE_UNRESOLVED if concepts.safe_abstention else GapKind.REPRESENTATION
    elif concepts.safe_abstention and not wire_ir:
        gap = GapKind.SAFE_UNRESOLVED
    elif concepts.resolution_status is ResolutionStatus.SAFE_PARTIAL:
        gap = GapKind.SAFE_PARTIAL

    return AuditOutcome(
        case_id=case.id,
        routed=routed,
        expected=case.expected_primitive,
        false_collapse=false,
        persist=assessment,
        wire_ir=wire_ir,
        concepts_status=concepts.resolution_status,
        ontology_gap=bool(concepts.ontology_gap),
        safe_abstention=bool(concepts.safe_abstention),
        attribute_dimension=concepts.attribute_dimension_key,
        state_dimension=concepts.state_dimension,
        state_value=concepts.state_value,
        action=concepts.action,
        relation_type=concepts.relation_type,
        information_loss=info_loss,
        gap=gap,
        notes=tuple(route_notes) + tuple(concepts.notes),
    )


def audit_query_primitive(proposal: SemanticProposal) -> PrimitiveKind:
    q = proposal.model_copy(update={"utterance_kind": "query"})
    routed, _ = route_primitive(q)
    return routed


def query_outcome(proposal: SemanticProposal):
    return proposal_to_query_ir(proposal.model_copy(update={"utterance_kind": "query"}))
