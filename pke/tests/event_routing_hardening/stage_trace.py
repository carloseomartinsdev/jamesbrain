"""Development/test stage snapshots for Event routing trace (I12.7 §§7–9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.multi_primitive_evidence import (
    has_explicit_occurrence_evidence,
    has_measurement_evidence,
)
from pke.interpretation.semantic.persistability import assess_persistability, event_type_for_wire
from pke.interpretation.semantic.event_preservation import event_semantically_preserved
from pke.interpretation.semantic.pipeline import (
    proposal_to_canonical_ir,
    resolution_to_wire_ingest,
    resolve_proposal,
)
from pke.interpretation.semantic.router import collect_assertions


@dataclass
class StageLedger:
    """Structural assertion summary per stage — not opaque string dumps."""

    primitive: str | None = None
    action: str | None = None
    entity_object: str | None = None
    measurement_dimension: str | None = None
    materializable: bool | None = None
    resolved_concept: bool | None = None
    non_materialized: bool | None = None
    event_present: bool = False
    measurement_present: bool = False
    notes: tuple[str, ...] = ()


@dataclass
class EventRoutingTrace:
    case_id: str
    s2_semantic_proposal: StageLedger
    s3_canonical_ir: StageLedger
    s4_collected_assertions: StageLedger
    s5_resolution_result: StageLedger
    s6_materialization_input: StageLedger
    s7_materialization_result: StageLedger
    s8_engine_outcome: StageLedger
    proposal_event_present: bool = False
    assertion_event_present: bool = False
    resolution_event_present: bool = False
    materialization_event_present: bool = False
    final_event_present: bool = False
    loss_taxonomy: str | None = None

    def classify_loss(self) -> str | None:
        if not self.proposal_event_present:
            return None
        if self.final_event_present:
            return None
        if not self.assertion_event_present:
            return "ASSERTION_COLLECTION_LOSS"
        if not self.resolution_event_present:
            return "RESOLUTION_LOSS"
        if not self.materialization_event_present:
            return "MATERIALIZATION_LOSS"
        return "PUBLIC_OUTCOME_LOSS"


def _entity_object(proposal: SemanticProposal) -> str | None:
    if proposal.object:
        return proposal.object.text
    if proposal.subject:
        return proposal.subject.text
    return None


def _proposal_ledger(proposal: SemanticProposal) -> StageLedger:
    return StageLedger(
        primitive=proposal.primitive_hint,
        action=proposal.action_expression,
        entity_object=_entity_object(proposal),
        measurement_dimension=proposal.measurable_dimension_key,
        event_present=has_explicit_occurrence_evidence(proposal),
        measurement_present=has_measurement_evidence(proposal),
        notes=("S2_SEMANTIC_PROPOSAL",),
    )


def trace_event_routing(proposal: SemanticProposal, *, case_id: str = "") -> EventRoutingTrace:
    """Full deterministic path trace from proposal to engine outcome."""
    s2 = _proposal_ledger(proposal)
    result = resolve_proposal(proposal)
    frames = collect_assertions(proposal)
    assertion_kinds = {f.primitive for f in frames}

    s4 = StageLedger(
        primitive=",".join(sorted(k.value for k in assertion_kinds)) or None,
        action=proposal.action_expression,
        entity_object=_entity_object(proposal),
        measurement_dimension=proposal.measurable_dimension_key,
        event_present=PrimitiveKind.EVENT in assertion_kinds,
        measurement_present=PrimitiveKind.MEASUREMENT in assertion_kinds,
        notes=tuple(f.notes[0] if f.notes else f.primitive.value for f in frames),
    )

    assessment = assess_persistability(result)
    event_type = event_type_for_wire(result.concepts, proposal)
    wire = resolution_to_wire_ingest(result)

    s5 = StageLedger(
        primitive=result.primitive.value,
        action=result.concepts.action,
        entity_object=_entity_object(proposal),
        measurement_dimension=proposal.measurable_dimension_key,
        materializable=assessment.wire_allowed,
        resolved_concept=bool(result.concepts.action or result.concepts.event_type),
        event_present=PrimitiveKind.EVENT in assertion_kinds,
        measurement_present=PrimitiveKind.MEASUREMENT in assertion_kinds,
        notes=assessment.notes,
    )

    s6 = StageLedger(
        primitive=result.primitive.value,
        action=result.concepts.action,
        entity_object=_entity_object(proposal),
        measurement_dimension=proposal.measurable_dimension_key,
        materializable=assessment.wire_allowed and event_type is not None,
        resolved_concept=event_type is not None,
        event_present=PrimitiveKind.EVENT in assertion_kinds,
        measurement_present=PrimitiveKind.MEASUREMENT in assertion_kinds,
        notes=(f"event_type={event_type}",),
    )

    s7 = StageLedger(
        primitive=wire.intent if wire else None,
        action=wire.event.action if wire and wire.event else None,
        entity_object=_entity_object(proposal),
        measurement_dimension=proposal.measurable_dimension_key,
        materializable=wire is not None,
        event_present=wire.event is not None if wire else False,
        measurement_present=wire.measurement is not None if wire else False,
        notes=("S7_MATERIALIZATION_RESULT",),
    )

    outcome = proposal_to_canonical_ir(proposal)
    ir = outcome.ir
    s8 = StageLedger(
        primitive=result.primitive.value,
        action=result.concepts.action,
        entity_object=_entity_object(proposal),
        measurement_dimension=proposal.measurable_dimension_key,
        materializable=ir is not None,
        event_present=event_semantically_preserved(outcome),
        measurement_present=ir.measurement is not None if ir else False,
        non_materialized=PrimitiveKind.EVENT in result.non_materialized_primitives,
        notes=(outcome.failure_stage or outcome.wire_stage,),
    )

    trace = EventRoutingTrace(
        case_id=case_id,
        s2_semantic_proposal=s2,
        s3_canonical_ir=s2,
        s4_collected_assertions=s4,
        s5_resolution_result=s5,
        s6_materialization_input=s6,
        s7_materialization_result=s7,
        s8_engine_outcome=s8,
        proposal_event_present=s2.event_present,
        assertion_event_present=s4.event_present,
        resolution_event_present=s5.event_present and s5.materializable is True,
        materialization_event_present=s7.event_present,
        final_event_present=event_semantically_preserved(outcome),
    )
    trace.loss_taxonomy = trace.classify_loss()
    return trace


def stage_matrix_row(trace: EventRoutingTrace) -> dict[str, Any]:
    """Compact row for MP/MS18 matrix (§91)."""

    def _cell(ledger: StageLedger) -> str:
        parts: list[str] = []
        if ledger.event_present:
            parts.append("E")
        if ledger.measurement_present:
            parts.append("M")
        if ledger.non_materialized:
            parts.append("NON_MATERIALIZED")
        if not parts:
            return "NONE"
        if ledger.materializable is False and ledger.event_present:
            return "UNRESOLVED"
        return "+".join(parts)

    return {
        "case_id": trace.case_id,
        "proposal": _cell(trace.s2_semantic_proposal),
        "assertions": _cell(trace.s4_collected_assertions),
        "resolution": _cell(trace.s5_resolution_result),
        "materialization": _cell(trace.s7_materialization_result),
        "post": _cell(trace.s8_engine_outcome),
        "loss": trace.loss_taxonomy,
    }
