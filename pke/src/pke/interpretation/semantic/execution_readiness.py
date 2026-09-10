"""Execution readiness — valid proposal vs materialization-complete (I12.10).

Single authority for whether a structurally valid SemanticProposal is
execution-ready. Inspects proposal + persistability + assertion set only.
Does not read raw_input to invent missing entities, roles, or primitives.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pke.interpretation.semantic.models import (
    PrimitiveKind,
    ResolutionResult,
    SemanticProposal,
)
from pke.interpretation.semantic.persistability import (
    PersistabilityStatus,
    assess_persistability,
)
from pke.interpretation.semantic.router import collect_assertions


class PrimitiveExecutionStatus(StrEnum):
    READY = "ready"
    SAFE_PARTIAL_NON_MATERIALIZABLE = "safe_partial_non_materializable"
    INCOMPLETE_REQUIRED_INFORMATION = "incomplete_required_information"
    REJECTED_INVALID = "rejected_invalid"


class ProposalExecutionOutcome(StrEnum):
    VALID_EXECUTABLE = "valid_executable"
    VALID_PARTIALLY_EXECUTABLE = "valid_partially_executable"
    VALID_EXECUTION_INCOMPLETE = "valid_execution_incomplete"
    INVALID = "invalid"


# Frozen reason codes — not free-text authority.
REASON_MISSING_ENTITY = "missing_entity"
REASON_MISSING_RELATION_OBJECT = "missing_relation_object"
REASON_MISSING_RELATION_SUBJECT = "missing_relation_subject"
REASON_RELATION_CANONICAL_UNRESOLVED = "relation_canonical_unresolved"
REASON_MISSING_STATE_DIMENSION = "missing_state_dimension"
REASON_MISSING_STATE_VALUE = "missing_state_value"
REASON_STATE_CANONICAL_UNRESOLVED = "state_canonical_unresolved"
REASON_CANONICAL_TYPE_UNRESOLVED_SAFE_PARTIAL = "canonical_type_unresolved_safe_partial"
REASON_MISSING_MEASUREMENT_DIMENSION = "missing_measurement_dimension"
REASON_MISSING_MEASUREMENT_VALUE = "missing_measurement_value"
REASON_MISSING_ATTRIBUTE_DIMENSION = "missing_attribute_dimension"
REASON_MISSING_ATTRIBUTE_VALUE = "missing_attribute_value"
REASON_UNSUPPORTED_ATTRIBUTE_DIMENSION = "unsupported_attribute_dimension"
REASON_UNSUPPORTED_PRIMITIVE = "unsupported_primitive"
REASON_AMBIGUOUS_CORRECTION_TARGET = "ambiguous_correction_target"
REASON_EVENT_IDENTITY_INCOMPLETE = "event_identity_incomplete"
REASON_CLASSIFICATION_NOT_MATERIALIZABLE = "classification_not_materializable"
REASON_ONTOLOGY_GAP = "ontology_gap"

_CLARIFIABLE_REASONS = frozenset(
    {
        REASON_MISSING_ENTITY,
        REASON_MISSING_RELATION_OBJECT,
        REASON_MISSING_RELATION_SUBJECT,
        REASON_MISSING_STATE_VALUE,
        REASON_MISSING_MEASUREMENT_DIMENSION,
        REASON_MISSING_MEASUREMENT_VALUE,
        REASON_MISSING_ATTRIBUTE_DIMENSION,
        REASON_MISSING_ATTRIBUTE_VALUE,
        REASON_AMBIGUOUS_CORRECTION_TARGET,
    }
)

# Known capability gaps — user cannot unlock by providing more of the same kind of info.
_UNSUPPORTED_REASONS = frozenset(
    {
        REASON_UNSUPPORTED_ATTRIBUTE_DIMENSION,
        REASON_UNSUPPORTED_PRIMITIVE,
        REASON_CLASSIFICATION_NOT_MATERIALIZABLE,
        REASON_ONTOLOGY_GAP,
        REASON_STATE_CANONICAL_UNRESOLVED,
        REASON_RELATION_CANONICAL_UNRESOLVED,
        "unknown_primitive",
    }
)


@dataclass(frozen=True)
class PrimitiveReadiness:
    primitive: PrimitiveKind
    status: PrimitiveExecutionStatus
    reasons: tuple[str, ...] = ()
    clarification_eligible: bool = False


@dataclass(frozen=True)
class ExecutionReadiness:
    """Aggregate readiness — does not erase per-primitive outcomes."""

    outcome: ProposalExecutionOutcome
    primitives: tuple[PrimitiveReadiness, ...] = ()
    proposed_count: int = 0
    semantically_valid_count: int = 0
    materializable_count: int = 0
    incomplete_count: int = 0
    safe_partial_count: int = 0
    clarification_eligible: bool = False
    reasons: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def zero_materializable_valid(self) -> bool:
        return (
            self.outcome is ProposalExecutionOutcome.VALID_EXECUTION_INCOMPLETE
            and self.materializable_count == 0
            and self.semantically_valid_count > 0
        )


def _entity_present(proposal: SemanticProposal) -> bool:
    if proposal.subject is not None and (proposal.subject.text or "").strip():
        return True
    if proposal.object is not None and (proposal.object.text or "").strip():
        return True
    if proposal.context is not None and (proposal.context.text or "").strip():
        return True
    if any((m.text or "").strip() for m in proposal.entities_mentioned):
        return True
    if any((m.text or "").strip() for m in proposal.participants):
        return True
    return False


def _map_persistability_notes(
    kind: PrimitiveKind, notes: tuple[str, ...], critical: tuple[str, ...]
) -> tuple[str, ...]:
    mapped: list[str] = []
    for note in notes:
        if note == "measurement_entity_required":
            mapped.append(REASON_MISSING_ENTITY)
        elif note == "measurement_dimension_value_required":
            if "measurement_dimension" in critical:
                mapped.append(REASON_MISSING_MEASUREMENT_DIMENSION)
            if "measurement_value" in critical:
                mapped.append(REASON_MISSING_MEASUREMENT_VALUE)
            if not mapped:
                mapped.append(REASON_MISSING_MEASUREMENT_DIMENSION)
        elif note == "event_category_unresolved_safe_partial":
            mapped.append(REASON_CANONICAL_TYPE_UNRESOLVED_SAFE_PARTIAL)
        elif note == "event_identity_incomplete":
            mapped.append(REASON_EVENT_IDENTITY_INCOMPLETE)
        elif note == "relation_identity_incomplete":
            if "object" in critical:
                mapped.append(REASON_MISSING_RELATION_OBJECT)
            if "subject" in critical:
                mapped.append(REASON_MISSING_RELATION_SUBJECT)
            if "relation_type" in critical and not mapped:
                mapped.append("missing_relation_identity")
        elif note == "relation_type_canonical_unresolved":
            mapped.append(REASON_RELATION_CANONICAL_UNRESOLVED)
        elif note == "state_value_required":
            mapped.append(REASON_MISSING_STATE_VALUE)
        elif note == "state_value_canonical_unresolved":
            mapped.append(REASON_STATE_CANONICAL_UNRESOLVED)
        elif note == "attribute_dimension_value_required":
            mapped.append(REASON_MISSING_ATTRIBUTE_DIMENSION)
        elif note == "attribute_value_required":
            mapped.append(REASON_MISSING_ATTRIBUTE_VALUE)
        elif note == "unsupported_attribute_dimension":
            mapped.append(REASON_UNSUPPORTED_ATTRIBUTE_DIMENSION)
        elif note == "unsupported_primitive":
            mapped.append(REASON_UNSUPPORTED_PRIMITIVE)
        elif note == "ontology_gap":
            mapped.append(REASON_ONTOLOGY_GAP)
        elif note == "classification_not_materializable":
            mapped.append(REASON_CLASSIFICATION_NOT_MATERIALIZABLE)
        else:
            mapped.append(note)
    if kind is PrimitiveKind.EVENT and REASON_EVENT_IDENTITY_INCOMPLETE in mapped:
        # Event identity incomplete without entity is missing-entity class, not fake type.
        pass
    return tuple(dict.fromkeys(mapped))


def _status_for_assessment(
    kind: PrimitiveKind, assessment
) -> PrimitiveExecutionStatus:
    if assessment.wire_allowed:
        return PrimitiveExecutionStatus.READY
    if "event_category_unresolved_safe_partial" in assessment.notes:
        return PrimitiveExecutionStatus.SAFE_PARTIAL_NON_MATERIALIZABLE
    if assessment.status is PersistabilityStatus.UNSAFE:
        return PrimitiveExecutionStatus.REJECTED_INVALID
    if kind is PrimitiveKind.TYPE:
        return PrimitiveExecutionStatus.SAFE_PARTIAL_NON_MATERIALIZABLE
    if assessment.status is PersistabilityStatus.PARTIALLY_RESOLVED_NONPERSISTABLE:
        return PrimitiveExecutionStatus.INCOMPLETE_REQUIRED_INFORMATION
    return PrimitiveExecutionStatus.INCOMPLETE_REQUIRED_INFORMATION


def assess_primitive_readiness(
    result: ResolutionResult, kind: PrimitiveKind
) -> PrimitiveReadiness:
    """Readiness for one assertion primitive — persistability authority reused."""
    sliced = ResolutionResult(
        proposal=result.proposal,
        primitive=kind,
        concepts=result.concepts,
        primitive_routing_notes=result.primitive_routing_notes,
        assertions=result.assertions,
        non_materialized_primitives=result.non_materialized_primitives,
        non_materialized_reasons=result.non_materialized_reasons,
    )
    assessment = assess_persistability(sliced)
    status = _status_for_assessment(kind, assessment)
    reasons = _map_persistability_notes(
        kind, assessment.notes, assessment.critical_unresolved
    )
    if (
        kind is PrimitiveKind.EVENT
        and status is PrimitiveExecutionStatus.INCOMPLETE_REQUIRED_INFORMATION
        and not _entity_present(result.proposal)
    ):
        reasons = tuple(dict.fromkeys((*reasons, REASON_MISSING_ENTITY)))
    if (
        kind is PrimitiveKind.STATE
        and status is PrimitiveExecutionStatus.READY
        and not _entity_present(result.proposal)
    ):
        # Existing persistability does not require subject; do not tighten.
        pass
    clarifiable = status is PrimitiveExecutionStatus.INCOMPLETE_REQUIRED_INFORMATION and any(
        r in _CLARIFIABLE_REASONS for r in reasons
    )
    return PrimitiveReadiness(
        primitive=kind,
        status=status,
        reasons=reasons,
        clarification_eligible=clarifiable,
    )


def assess_execution_readiness(result: ResolutionResult) -> ExecutionReadiness:
    """Aggregate execution completeness. Does not reinterpret raw_input."""
    frames = result.assertions or collect_assertions(result.proposal)
    kinds: list[PrimitiveKind] = []
    seen: set[PrimitiveKind] = set()
    for frame in frames:
        if frame.primitive not in seen:
            kinds.append(frame.primitive)
            seen.add(frame.primitive)
    if not kinds:
        kinds = [result.primitive]

    items = tuple(assess_primitive_readiness(result, k) for k in kinds)
    ready = sum(1 for p in items if p.status is PrimitiveExecutionStatus.READY)
    partial = sum(
        1 for p in items if p.status is PrimitiveExecutionStatus.SAFE_PARTIAL_NON_MATERIALIZABLE
    )
    incomplete = sum(
        1 for p in items if p.status is PrimitiveExecutionStatus.INCOMPLETE_REQUIRED_INFORMATION
    )
    rejected = sum(1 for p in items if p.status is PrimitiveExecutionStatus.REJECTED_INVALID)
    valid = ready + partial + incomplete
    reasons = tuple(r for p in items for r in p.reasons)
    clarifiable = any(p.clarification_eligible for p in items)

    if rejected and valid == 0:
        outcome = ProposalExecutionOutcome.INVALID
    elif ready > 0 and incomplete == 0 and partial == 0:
        outcome = ProposalExecutionOutcome.VALID_EXECUTABLE
    elif ready > 0:
        outcome = ProposalExecutionOutcome.VALID_PARTIALLY_EXECUTABLE
    elif valid > 0 and ready == 0:
        outcome = ProposalExecutionOutcome.VALID_EXECUTION_INCOMPLETE
    else:
        outcome = ProposalExecutionOutcome.INVALID

    notes: list[str] = []
    if outcome is ProposalExecutionOutcome.VALID_EXECUTION_INCOMPLETE:
        notes.append("zero_materializable_valid_proposal")
    if clarifiable:
        notes.append("clarification_eligible")

    return ExecutionReadiness(
        outcome=outcome,
        primitives=items,
        proposed_count=len(items),
        semantically_valid_count=valid,
        materializable_count=ready,
        incomplete_count=incomplete,
        safe_partial_count=partial,
        clarification_eligible=clarifiable,
        reasons=reasons,
        notes=tuple(notes),
    )


def primary_reason(readiness: ExecutionReadiness) -> str:
    for r in readiness.reasons:
        if r in _CLARIFIABLE_REASONS:
            return r
    if readiness.reasons:
        return readiness.reasons[0]
    return "execution_incomplete"


def question_key_for_reason(reason: str) -> str:
    mapping = {
        REASON_MISSING_ENTITY: "clarify.entity.which_one",
        REASON_MISSING_RELATION_OBJECT: "clarify.entity.which_one",
        REASON_MISSING_RELATION_SUBJECT: "clarify.entity.which_one",
        REASON_MISSING_STATE_VALUE: "clarify.state.value",
        REASON_MISSING_STATE_DIMENSION: "clarify.state.dimension",
        REASON_MISSING_MEASUREMENT_DIMENSION: "clarify.measurement.dimension",
        REASON_MISSING_MEASUREMENT_VALUE: "clarify.measurement.value",
        REASON_MISSING_ATTRIBUTE_DIMENSION: "clarify.attribute.dimension",
        REASON_MISSING_ATTRIBUTE_VALUE: "clarify.attribute.value",
        REASON_AMBIGUOUS_CORRECTION_TARGET: "clarify.correction.target",
    }
    return mapping.get(reason, "clarify.generic")
