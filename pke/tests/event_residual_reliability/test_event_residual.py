"""I12.17 Event residual reliability — freeze-gate suite."""

from __future__ import annotations

from collections import Counter

import pytest

from pke.interpretation.semantic.capability_strategy import decide_capability
from pke.interpretation.semantic.event_preservation import (
    event_assertion_present,
    event_false_canonicalization,
    event_semantically_preserved,
)
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.router import collect_assertions
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from tests.event_residual_reliability.corpus import I1217_EVENT_RESIDUAL_CORPUS


@pytest.fixture(scope="module", autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def test_corpus_size() -> None:
    assert len(I1217_EVENT_RESIDUAL_CORPUS) >= 120


@pytest.mark.parametrize("case", I1217_EVENT_RESIDUAL_CORPUS, ids=lambda c: c.case_id)
def test_residual_case(case) -> None:
    proposal = case.factory()
    outcome = proposal_to_canonical_ir(proposal)
    result = outcome.result
    assertions = {a.primitive for a in collect_assertions(proposal)}

    assert event_false_canonicalization(outcome) is False
    assert result.proposal.raw_input == proposal.raw_input

    if case.expect == "partial_non_materialized":
        assert event_assertion_present(result)
        assert PrimitiveKind.EVENT in result.non_materialized_primitives
        assert event_semantically_preserved(outcome)
        if outcome.ir is not None:
            assert outcome.ir.event is None
            # sibling measurement may or may not materialize depending on entity

    elif case.expect == "measurement_only":
        assert PrimitiveKind.EVENT not in assertions or not event_assertion_present(result)
        assert PrimitiveKind.EVENT not in result.non_materialized_primitives
        if outcome.ir is not None:
            assert outcome.ir.event is None
            assert outcome.ir.measurement is not None

    elif case.expect == "resolved_materialized":
        assert outcome.ir is not None and outcome.ir.event is not None
        assert outcome.ir.event.type.key in ConceptCatalog.event_types
        assert outcome.ir.event.type.key != "event.intent" or result.concepts.event_type == "event.intent"
        assert PrimitiveKind.EVENT not in result.non_materialized_primitives

    elif case.expect == "event_only_partial":
        assert event_assertion_present(result)
        assert PrimitiveKind.EVENT in result.non_materialized_primitives
        assert event_semantically_preserved(outcome)
        if outcome.ir is not None:
            assert outcome.ir.event is None

    elif case.expect == "state_no_event":
        assert PrimitiveKind.STATE in assertions
        assert PrimitiveKind.EVENT not in assertions

    elif case.expect == "relation_no_event":
        assert PrimitiveKind.RELATION in assertions
        assert PrimitiveKind.EVENT not in assertions

    elif case.expect == "no_event":
        assert PrimitiveKind.EVENT not in assertions
        if outcome.ir is not None:
            assert outcome.ir.event is None


def test_aggregate_safety_metrics() -> None:
    safety = Counter()
    expect_ok = Counter()
    for case in I1217_EVENT_RESIDUAL_CORPUS:
        proposal = case.factory()
        before = proposal.raw_input
        outcome = proposal_to_canonical_ir(proposal)
        result = outcome.result
        assertions = {a.primitive for a in collect_assertions(proposal)}

        if result.proposal.raw_input != before:
            safety["RAW_TEXT_REINTERPRETED_DOWNSTREAM"] += 1
        if event_false_canonicalization(outcome):
            safety["EVENT_FALSE_CANONICALIZATION"] += 1
        if (
            event_assertion_present(result)
            and PrimitiveKind.EVENT not in result.non_materialized_primitives
            and (outcome.ir is None or outcome.ir.event is None)
            and case.expect
            in {"partial_non_materialized", "event_only_partial", "resolved_materialized"}
        ):
            # resolved should have event; partial should be non_mat
            if case.expect != "resolved_materialized":
                safety["VALID_EXPLICIT_EVENT_DROPPED_DOWNSTREAM"] += 1
            elif outcome.ir is None or outcome.ir.event is None:
                safety["VALID_EXPLICIT_EVENT_DROPPED_DOWNSTREAM"] += 1

        if case.family == "state_control" and PrimitiveKind.EVENT in assertions:
            safety["STATE_FALSE_CAUSAL_EVENT"] += 1
        if case.family == "relation_control" and PrimitiveKind.EVENT in assertions:
            safety["RELATION_FALSE_START_EVENT"] += 1
        if case.family == "measurement_only" or case.expect == "measurement_only":
            if outcome.ir and outcome.ir.event is not None:
                safety["MP5_FALSE_EVENT"] += 1
            if PrimitiveKind.EVENT in result.non_materialized_primitives:
                safety["MP5_FALSE_EVENT"] += 1

        # false intent fallback
        if (
            outcome.ir
            and outcome.ir.event
            and outcome.ir.event.type.key == "event.intent"
            and result.concepts.event_type != "event.intent"
        ):
            safety["EVENT_FALSE_CANONICALIZATION"] += 1

        expect_ok[case.expect] += 1

    assert all(v == 0 for v in safety.values()), dict(safety)
    assert expect_ok["partial_non_materialized"] > 0
    assert expect_ok["measurement_only"] > 0
    assert expect_ok["resolved_materialized"] > 0


def test_mp_anchors_commit_independently() -> None:
    from tests.event_partial_semantics.corpus import mp1, mp5

    # MP1: Event partial, Measurement may materialize with entity in fixture
    o1 = proposal_to_canonical_ir(mp1())
    assert event_assertion_present(o1.result)
    assert PrimitiveKind.EVENT in o1.result.non_materialized_primitives
    assert not event_false_canonicalization(o1)
    if o1.ir is not None:
        assert o1.ir.event is None

    # MP5: measurement only
    o5 = proposal_to_canonical_ir(mp5())
    assert PrimitiveKind.EVENT not in o5.result.non_materialized_primitives
    assert o5.ir is not None
    assert o5.ir.event is None
    assert o5.ir.measurement is not None


def test_capability_boundary_still_intact() -> None:
    from tests.structured_proposal_reliability.corpus import mp1_missing_subject

    p = mp1_missing_subject()
    d = decide_capability(assess_execution_readiness(resolve_proposal(p)))
    assert d.outcome.value in {
        "partial_execute",
        "clarify",
        "safe_abstain",
        "auto_execute",
    }
