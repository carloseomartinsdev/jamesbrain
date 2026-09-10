"""I12.9 failure taxonomy and pipeline stage tracing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from pydantic import ValidationError

from pke.interpretation.interpreter import InterpretationError
from pke.interpretation.semantic.envelope_dispatch import ProviderRoute, dispatch_provider_payload
from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.multi_primitive_evidence import (
    has_explicit_occurrence_evidence,
    has_measurement_evidence,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolution_to_wire_ingest, resolve_proposal
from pke.interpretation.semantic.proposal_assessment import SemanticActionability, assess_semantic_proposal
from pke.interpretation.semantic.router import collect_assertions
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from tests.engine_v1_baseline.corpus import EngineCase

PrimaryFailure = Literal[
    "CORRECT",
    "SAFE_ABSTENTION",
    "SEMANTIC_OMISSION",
    "WRONG_SEMANTIC_DECISION",
    "STRUCTURED_OUTPUT_INVALID",
    "NORMALIZATION_FAILURE",
    "CONCEPT_RESOLUTION_REJECTION",
    "TRANSPORT_FAILURE",
    "DOWNSTREAM_INFORMATION_LOSS",
    "OTHER",
]

StageId = Literal[
    "S0_PROVIDER_RESPONSE",
    "S1_TRANSPORT_NORMALIZED",
    "S2_SEMANTIC_PROPOSAL",
    "S3_PRIMITIVE_ROUTING",
    "S4_CONCEPT_RESOLUTION",
    "S5_ASSERTION_SET",
    "S6_PERSISTABILITY",
    "S7_MATERIALIZATION",
    "S8_FINAL_OUTCOME",
]


class MP1SubClass(StrEnum):
    NO_PARSEABLE_PROPOSAL = "NO_PARSEABLE_PROPOSAL"
    VALID_PROPOSAL_MISSING_EVENT = "VALID_PROPOSAL_MISSING_EVENT"
    VALID_PROPOSAL_WRONG_PRIMITIVE = "VALID_PROPOSAL_WRONG_PRIMITIVE"
    VALID_PROPOSAL_CORRECT = "VALID_PROPOSAL_CORRECT"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    NORMALIZATION_FAILURE = "NORMALIZATION_FAILURE"
    RESOLUTION_FAILURE = "RESOLUTION_FAILURE"
    OTHER = "OTHER"


@dataclass
class PipelineTrace:
    provider_response_present: bool = False
    normalization_ok: bool = False
    normalization_stage: str | None = None
    proposal_valid: bool = False
    proposal_assessment: str | None = None
    routed_primitive: str | None = None
    assertion_kinds: tuple[str, ...] = ()
    wire_built: bool = False
    outcome_ir: bool = False
    failure_stage: str | None = None
    interpret_error: str | None = None
    first_fault_stage: StageId | None = None
    proposal: SemanticProposal | None = None
    internal_inconsistencies: tuple[str, ...] = ()


@dataclass
class RunClassification:
    primary: PrimaryFailure
    secondary: tuple[str, ...] = ()
    mp1_subclass: MP1SubClass | None = None
    trace: PipelineTrace = field(default_factory=PipelineTrace)
    expected_primitive: str | None = None
    observed_primitive_set: tuple[str, ...] = ()
    event_evidence_on_proposal: bool = False
    event_in_assertions: bool = False
    first_attempt_valid: bool = False
    retry_triggered: bool = False
    retry_recovered: bool = False


def audit_proposal_inconsistencies(proposal: SemanticProposal) -> tuple[str, ...]:
    """Proposal-side only — no raw text reinterpretation."""
    issues: list[str] = []
    kinds = {f.primitive for f in collect_assertions(proposal)}

    has_occurrence = has_explicit_occurrence_evidence(proposal)
    has_meas = has_measurement_evidence(proposal)

    if has_occurrence and PrimitiveKind.EVENT not in kinds:
        issues.append("occurrence_semantics_without_event_assertion")
    if has_meas and PrimitiveKind.MEASUREMENT not in kinds:
        issues.append("measurement_semantics_without_measurement_assertion")
    if proposal.correction_semantics and proposal.utterance_kind != "correct":
        issues.append("correction_semantics_without_correct_intent")
    if proposal.link_semantics and PrimitiveKind.RELATION not in kinds and proposal.primitive_hint not in {
        "relation",
        None,
        "unknown",
    }:
        if not (proposal.lifecycle_cue and proposal.relation_expression):
            issues.append("link_semantics_without_relation_assertion")
    if proposal.condition_semantics and PrimitiveKind.STATE not in kinds and proposal.primitive_hint not in {
        "state",
        None,
        "unknown",
    }:
        issues.append("condition_semantics_without_state_assertion")

    return tuple(issues)


def trace_from_raw(
    raw_content: str | None,
    *,
    interpret_error: str | None = None,
    attempts: int = 1,
) -> PipelineTrace:
    trace = PipelineTrace(interpret_error=interpret_error)
    if not raw_content:
        trace.first_fault_stage = "S0_PROVIDER_RESPONSE"
        return trace

    trace.provider_response_present = True
    dispatched = dispatch_provider_payload(raw_content)
    if dispatched.route is ProviderRoute.INVALID:
        trace.normalization_stage = dispatched.failure_stage
        trace.first_fault_stage = (
            "S0_PROVIDER_RESPONSE"
            if dispatched.failure_stage == "PROVIDER_EMPTY"
            else "S1_TRANSPORT_NORMALIZED"
        )
        return trace

    trace.normalization_ok = True
    trace.first_fault_stage = "S1_TRANSPORT_NORMALIZED"

    try:
        if dispatched.route is ProviderRoute.V2_CANONICAL:
            trace.first_fault_stage = "S2_SEMANTIC_PROPOSAL"
            return trace
        payload = dispatched.payload or {}
        ir = payload.get("ir") if isinstance(payload, dict) else None
        if ir is not None:
            proposal = SemanticProposal.model_validate(ir)
        else:
            env = WireSemanticEnvelope.model_validate(payload)
            proposal = (
                env.parsed_query_proposal()
                if env.ir_kind == "semantic_query"
                else env.parsed_proposal()
            )
    except ValidationError:
        trace.first_fault_stage = "S2_SEMANTIC_PROPOSAL"
        return trace

    trace.proposal_valid = True
    trace.proposal = proposal
    assessment = assess_semantic_proposal(proposal)
    trace.proposal_assessment = assessment.status.value
    trace.routed_primitive = assessment.routed_primitive.value
    trace.internal_inconsistencies = audit_proposal_inconsistencies(proposal)

    if assessment.status is SemanticActionability.INSUFFICIENT:
        trace.first_fault_stage = "S2_SEMANTIC_PROPOSAL"
        return trace

    frames = collect_assertions(proposal)
    trace.assertion_kinds = tuple(sorted(f.primitive.value for f in frames))
    trace.first_fault_stage = "S3_PRIMITIVE_ROUTING"

    result = resolve_proposal(proposal)
    try:
        wire = resolution_to_wire_ingest(result)
    except Exception:  # noqa: BLE001
        trace.first_fault_stage = "S4_CONCEPT_RESOLUTION"
        trace.failure_stage = "CONCEPT_RESOLUTION"
        return trace
    if wire is None:
        trace.first_fault_stage = "S4_CONCEPT_RESOLUTION"
        trace.failure_stage = "CONCEPT_RESOLUTION"
        return trace

    trace.wire_built = True
    trace.first_fault_stage = "S5_ASSERTION_SET"

    outcome = proposal_to_canonical_ir(proposal)
    if outcome.ir is None:
        trace.failure_stage = outcome.failure_stage
        trace.first_fault_stage = "S4_CONCEPT_RESOLUTION"
        return trace

    trace.outcome_ir = True
    trace.first_fault_stage = "S8_FINAL_OUTCOME"
    return trace


def _expected_kinds(case: EngineCase) -> set[str]:
    if case.expected_primitive == "multi":
        return {"event", "measurement"}
    if case.expected_primitive:
        return {case.expected_primitive}
    return set()


def _observed_kinds(proposal: SemanticProposal | None) -> set[str]:
    if proposal is None:
        return set()
    return {f.primitive.value for f in collect_assertions(proposal)}


def classify_run(
    case: EngineCase,
    *,
    raw_content: str | None,
    interpret_error: str | None = None,
    ir_ok: bool = False,
    attempts: int = 1,
    first_attempt_raw: str | None = None,
    trace: PipelineTrace | None = None,
) -> RunClassification:
    tr = trace or trace_from_raw(raw_content, interpret_error=interpret_error, attempts=attempts)
    expected = _expected_kinds(case)
    observed = _observed_kinds(tr.proposal)
    event_ev = has_explicit_occurrence_evidence(tr.proposal) if tr.proposal else False
    event_asrt = "event" in tr.assertion_kinds

    secondary: list[str] = []
    if case.category in {"event", "multi_primitive"} or "event" in expected:
        secondary.append("EVENT")
    if case.category in {"state"} or "state" in expected:
        secondary.append("STATE")
    if case.category in {"relation"} or "relation" in expected:
        secondary.append("RELATION")
    if case.category in {"measurement", "multi_primitive"} or "measurement" in expected:
        secondary.append("MEASUREMENT")
    if case.category == "correction":
        secondary.append("CORRECTION")
    if case.expected_primitive == "multi":
        secondary.append("MULTI_PRIMITIVE")

    first_valid = bool(first_attempt_raw and dispatch_provider_payload(first_attempt_raw).route != ProviderRoute.INVALID)
    retry_triggered = attempts > 1
    retry_recovered = retry_triggered and ir_ok and not interpret_error

    mp1_sub: MP1SubClass | None = None
    if case.utterance.casefold().startswith("medi a temperatura e deu 95"):
        if not tr.proposal_valid:
            mp1_sub = (
                MP1SubClass.NORMALIZATION_FAILURE
                if tr.first_fault_stage == "S1_TRANSPORT_NORMALIZED"
                else MP1SubClass.NO_PARSEABLE_PROPOSAL
            )
        elif not tr.wire_built and not tr.outcome_ir:
            mp1_sub = MP1SubClass.RESOLUTION_FAILURE
        elif "event" in expected and "event" not in observed:
            mp1_sub = MP1SubClass.VALID_PROPOSAL_MISSING_EVENT
        elif observed == expected or (ir_ok and tr.outcome_ir):
            mp1_sub = MP1SubClass.VALID_PROPOSAL_CORRECT
        else:
            mp1_sub = MP1SubClass.VALID_PROPOSAL_WRONG_PRIMITIVE

    # Primary classification
    primary: PrimaryFailure = "OTHER"

    if interpret_error and interpret_error.startswith("provider:"):
        primary = "TRANSPORT_FAILURE"
    elif not tr.provider_response_present:
        primary = "TRANSPORT_FAILURE" if interpret_error else "STRUCTURED_OUTPUT_INVALID"
    elif not tr.normalization_ok:
        primary = "NORMALIZATION_FAILURE"
    elif not tr.proposal_valid:
        primary = "STRUCTURED_OUTPUT_INVALID"
    elif tr.proposal_assessment == "insufficient":
        primary = "STRUCTURED_OUTPUT_INVALID"
    elif not tr.wire_built and tr.proposal_valid:
        primary = "CONCEPT_RESOLUTION_REJECTION"
    elif ir_ok and tr.outcome_ir:
        if case.expected_safe_abstention or case.expected_primitive == "unknown":
            primary = "SAFE_ABSTENTION" if tr.proposal_assessment in {"partial", "actionable"} else "CORRECT"
        elif expected and observed == expected:
            primary = "CORRECT"
        elif expected and expected <= observed:
            primary = "CORRECT"  # superset ok for multi if all expected present
        elif expected and not expected.isdisjoint(observed) and expected != observed:
            missing = expected - observed
            if missing:
                primary = "SEMANTIC_OMISSION"
            else:
                primary = "WRONG_SEMANTIC_DECISION"
        elif expected and observed and not expected.intersection(observed):
            primary = "WRONG_SEMANTIC_DECISION"
        elif expected and not observed:
            primary = "SEMANTIC_OMISSION"
        else:
            primary = "CORRECT"
    elif interpret_error and "acceptance_guard" in interpret_error:
        primary = "SAFE_ABSTENTION"
    elif event_ev and not event_asrt and "event" in expected:
        primary = "SEMANTIC_OMISSION"
    elif tr.internal_inconsistencies:
        primary = "SEMANTIC_OMISSION"
    elif tr.proposal_valid and not tr.wire_built:
        primary = "CONCEPT_RESOLUTION_REJECTION"
    else:
        primary = "OTHER"

    # Downstream loss check
    if tr.proposal and event_ev and tr.outcome_ir:
        outcome = proposal_to_canonical_ir(tr.proposal)
        from pke.interpretation.semantic.event_preservation import event_semantically_preserved

        if not event_semantically_preserved(outcome) and "event" in expected:
            primary = "DOWNSTREAM_INFORMATION_LOSS"

    return RunClassification(
        primary=primary,
        secondary=tuple(dict.fromkeys(secondary)),
        mp1_subclass=mp1_sub,
        trace=tr,
        expected_primitive=case.expected_primitive,
        observed_primitive_set=tuple(sorted(observed)),
        event_evidence_on_proposal=event_ev,
        event_in_assertions=event_asrt,
        first_attempt_valid=first_valid,
        retry_triggered=retry_triggered,
        retry_recovered=retry_recovered,
    )
