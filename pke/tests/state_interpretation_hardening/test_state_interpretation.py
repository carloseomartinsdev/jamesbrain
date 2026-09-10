"""I12.15 State interpretation characterization & bounded hardening tests."""

from __future__ import annotations

from collections import Counter

import pytest

from pke.interpretation.semantic.capability_strategy import (
    CapabilityOutcome,
    decide_capability,
)
from pke.interpretation.semantic.execution_readiness import (
    REASON_STATE_CANONICAL_UNRESOLVED,
    assess_execution_readiness,
)
from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.pipeline import resolve_proposal
from pke.interpretation.semantic.router import collect_assertions, route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from tests.state_interpretation_hardening.corpus import I1215_STATE_CORPUS


@pytest.fixture(scope="module", autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def test_corpus_size() -> None:
    assert len(I1215_STATE_CORPUS) >= 220


@pytest.mark.parametrize("case", I1215_STATE_CORPUS, ids=lambda c: c.case_id)
def test_state_case(case) -> None:
    proposal = case.proposal_factory()
    result = resolve_proposal(proposal)
    readiness = assess_execution_readiness(result)
    decision = decide_capability(readiness)

    assert decision.outcome.value == case.expected_outcome, (
        f"{case.case_id}: got {decision.outcome.value} expected {case.expected_outcome} "
        f"reasons={readiness.reasons} notes={decision.notes}"
    )

    if case.family == "canonical_gap":
        assert decision.outcome is CapabilityOutcome.UNSUPPORTED
        assert decision.clarification is None
        assert REASON_STATE_CANONICAL_UNRESOLVED in readiness.reasons or any(
            REASON_STATE_CANONICAL_UNRESOLVED in p.reasons for p in readiness.primitives
        )

    if case.family == "missing_value":
        assert decision.outcome is CapabilityOutcome.CLARIFY
        assert decision.clarification is not None
        assert decision.clarification.missing_slot == "state_value"
        assert decision.clarification.question_key == "clarify.state.value"

    if case.family == "attribute_control":
        assertions = {a.primitive for a in collect_assertions(proposal)}
        assert PrimitiveKind.STATE not in assertions
        assert PrimitiveKind.ATTRIBUTE in assertions

    if case.family == "relation_control":
        assertions = {a.primitive for a in collect_assertions(proposal)}
        assert PrimitiveKind.STATE not in assertions
        assert PrimitiveKind.RELATION in assertions

    if case.family == "event_control":
        assertions = {a.primitive for a in collect_assertions(proposal)}
        assert PrimitiveKind.STATE not in assertions

    if case.family == "measurement_control":
        assertions = {a.primitive for a in collect_assertions(proposal)}
        assert PrimitiveKind.STATE not in assertions
        assert PrimitiveKind.MEASUREMENT in assertions

    # No raw reinterpretation: raw_input unchanged through resolve
    assert result.proposal.raw_input == proposal.raw_input


def test_aggregate_safety_and_metrics() -> None:
    safety = Counter()
    outcomes = Counter()
    core_ok = 0
    core_n = 0
    for case in I1215_STATE_CORPUS:
        proposal = case.proposal_factory()
        before_raw = proposal.raw_input
        result = resolve_proposal(proposal)
        readiness = assess_execution_readiness(result)
        decision = decide_capability(readiness)
        outcomes[decision.outcome.value] += 1
        if result.proposal.raw_input != before_raw:
            safety["RAW_TEXT_REINTERPRETED"] += 1
        assertions = {a.primitive for a in collect_assertions(proposal)}
        if case.family == "attribute_control" and PrimitiveKind.STATE in assertions:
            safety["ATTRIBUTE_FALSELY_ROUTED_TO_STATE"] += 1
        if case.family == "relation_control" and PrimitiveKind.STATE in assertions:
            safety["RELATION_FALSELY_ROUTED_TO_STATE"] += 1
        if case.family == "event_control" and PrimitiveKind.STATE in assertions:
            safety["EVENT_FALSELY_ROUTED_TO_STATE"] += 1
        if case.family == "measurement_control" and PrimitiveKind.STATE in assertions:
            safety["MEASUREMENT_FALSELY_ROUTED_TO_STATE"] += 1
        if case.family == "core_value":
            core_n += 1
            if decision.outcome is CapabilityOutcome.AUTO_EXECUTE:
                core_ok += 1
        if case.family == "canonical_gap" and decision.outcome is CapabilityOutcome.CLARIFY:
            safety["FALSE_CLARIFY_ON_CANONICAL_GAP"] += 1
        if case.expected_primitive == "state" and case.family == "core_value":
            routed, _ = route_primitive(proposal)
            if routed is not PrimitiveKind.STATE and case.expected_outcome == "auto_execute":
                # multi may prefer other; still require state assertion present
                if PrimitiveKind.STATE not in assertions:
                    safety["STATE_NOT_ROUTED"] += 1

    assert all(v == 0 for v in safety.values()), dict(safety)
    precision = core_ok / max(1, core_n)
    assert precision >= 0.95
    assert outcomes["unsupported"] > 0
    assert outcomes["clarify"] > 0
    assert outcomes["auto_execute"] > 0


def test_state_dimension_recovery_unsupported() -> None:
    from pke.application.pending_operation import PendingSemanticOperation

    pending = PendingSemanticOperation(
        originating_raw="x",
        proposal_dump=state_prop(
            raw="x", entity="porta", expr="quebrado"
        ).model_dump(),
        missing_slot="state_dimension",
        expected_answer_kind="dimension",
        primitive="state",
        reason="missing_state_dimension",
        question_key="clarify.state.dimension",
    )
    assert pending.is_supported() is False


def test_proposal_can_express_complete_state() -> None:
    p = state_prop(raw="porta aberta", entity="porta", expr="aberta")
    assert p.condition_semantics is True
    assert p.state_expression == "aberta"
    assert p.subject is not None
    result = resolve_proposal(p)
    readiness = assess_execution_readiness(result)
    assert decide_capability(readiness).outcome is CapabilityOutcome.AUTO_EXECUTE


# re-export helper for test_state_dimension
from tests.state_interpretation_hardening.corpus import state_prop  # noqa: E402
