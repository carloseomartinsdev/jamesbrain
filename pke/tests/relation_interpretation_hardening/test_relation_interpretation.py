"""I12.16 Relation interpretation characterization & bounded hardening tests."""

from __future__ import annotations

from collections import Counter

import pytest

from pke.interpretation.semantic.capability_strategy import (
    CapabilityOutcome,
    decide_capability,
)
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.pipeline import resolve_proposal
from pke.interpretation.semantic.router import collect_assertions
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from tests.relation_interpretation_hardening.corpus import I1216_RELATION_CORPUS


@pytest.fixture(scope="module", autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def test_corpus_size() -> None:
    assert len(I1216_RELATION_CORPUS) >= 220


@pytest.mark.parametrize("case", I1216_RELATION_CORPUS, ids=lambda c: c.case_id)
def test_relation_case(case) -> None:
    proposal = case.proposal_factory()
    result = resolve_proposal(proposal)
    readiness = assess_execution_readiness(result)
    decision = decide_capability(readiness)

    assert decision.outcome.value == case.expected_outcome, (
        f"{case.case_id}: got {decision.outcome.value} expected {case.expected_outcome} "
        f"reasons={readiness.reasons} notes={decision.notes} "
        f"rel={result.concepts.relation_type} unresolved={result.concepts.unresolved}"
    )

    if case.family == "canonical_gap":
        assert decision.outcome is CapabilityOutcome.AUTO_EXECUTE
        assert result.concepts.relation_type

    if case.family == "missing_object":
        assert decision.clarification is not None
        assert decision.clarification.missing_slot == "relation_object"
        assert decision.clarification.expected_answer_kind == "entity_reference"

    if case.family == "missing_subject":
        assert decision.clarification is not None
        assert decision.clarification.missing_slot == "relation_subject"

    if case.family == "state_control":
        assertions = {a.primitive for a in collect_assertions(proposal)}
        assert PrimitiveKind.RELATION not in assertions
        assert PrimitiveKind.STATE in assertions

    if case.family == "attribute_control":
        assertions = {a.primitive for a in collect_assertions(proposal)}
        assert PrimitiveKind.RELATION not in assertions

    if case.family == "event_control":
        assertions = {a.primitive for a in collect_assertions(proposal)}
        assert PrimitiveKind.RELATION not in assertions

    assert result.proposal.raw_input == proposal.raw_input


def test_aggregate_safety_and_metrics() -> None:
    safety = Counter()
    outcomes = Counter()
    core_ok = 0
    core_n = 0
    for case in I1216_RELATION_CORPUS:
        proposal = case.proposal_factory()
        before = proposal.model_dump()
        result = resolve_proposal(proposal)
        readiness = assess_execution_readiness(result)
        decision = decide_capability(readiness)
        outcomes[decision.outcome.value] += 1
        if result.proposal.raw_input != before["raw_input"]:
            safety["RAW_TEXT_REINTERPRETED"] += 1
        # subject/object must not swap on resolve for direction family
        if case.family in {"direction", "core_relation"} and proposal.subject and proposal.object:
            if result.proposal.subject and result.proposal.object:
                if (
                    result.proposal.subject.text == proposal.object.text
                    and result.proposal.object.text == proposal.subject.text
                ):
                    safety["RELATION_SUBJECT_OBJECT_FALSE_REVERSAL"] += 1
        assertions = {a.primitive for a in collect_assertions(proposal)}
        if case.family == "state_control" and PrimitiveKind.RELATION in assertions:
            safety["STATE_FALSELY_ROUTED_TO_RELATION"] += 1
        if case.family == "attribute_control" and PrimitiveKind.RELATION in assertions:
            safety["ATTRIBUTE_FALSELY_ROUTED_TO_RELATION"] += 1
        if case.family == "event_control" and PrimitiveKind.RELATION in assertions:
            safety["EVENT_FALSELY_ROUTED_TO_RELATION"] += 1
        if case.family == "core_relation" and PrimitiveKind.STATE in assertions:
            safety["RELATION_FALSELY_ROUTED_TO_STATE"] += 1
        if case.family == "canonical_gap" and decision.outcome is CapabilityOutcome.CLARIFY:
            safety["RELATION_FALSE_RECOVERABLE_GAP"] += 1
        if case.family == "core_relation":
            core_n += 1
            if decision.outcome is CapabilityOutcome.AUTO_EXECUTE:
                core_ok += 1
        # no invented start event from relation-only proposal
        if case.expected_primitive == "relation" and case.family == "core_relation":
            if PrimitiveKind.EVENT in assertions and not proposal.change_semantics:
                safety["RELATION_ASSERTION_FALSE_CAUSAL_EVENT"] += 1

    assert all(v == 0 for v in safety.values()), dict(safety)
    precision = core_ok / max(1, core_n)
    assert precision >= 0.95
    assert outcomes["clarify"] > 0
    assert outcomes["auto_execute"] > 0


def test_proposal_expresses_complete_relation() -> None:
    from tests.relation_interpretation_hardening.corpus import rel_prop

    p = rel_prop(
        raw="Alice trabalha em Acme",
        subject="Alice",
        obj="Acme",
        expr="trabalha em",
    )
    assert p.link_semantics and p.relation_expression and p.subject and p.object
    decision = decide_capability(assess_execution_readiness(resolve_proposal(p)))
    assert decision.outcome is CapabilityOutcome.AUTO_EXECUTE
