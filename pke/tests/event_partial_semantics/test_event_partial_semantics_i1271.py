"""I12.7.1 partial Event semantics tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pke.interpretation.semantic.event_preservation import (
    event_assertion_present,
    event_false_canonicalization,
    event_semantically_preserved,
)
from pke.interpretation.semantic.models import (
    PrimitiveKind,
    ResolutionResult,
    ResolvedConcepts,
    ResolutionConfidence,
    ResolutionProvenance,
    ResolutionStatus,
    SemanticProposal,
)
from pke.interpretation.semantic.persistability import assess_persistability, event_type_for_wire
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.router import collect_assertions
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology.registry import OntologyRegistry
from tests.event_partial_semantics.corpus import (
    ANCHOR_CASES,
    all_cases,
    partial_event_cases,
    mp1,
    mp5,
)
from tests.event_routing_hardening.corpus import ms18_i126
from tests.semantic_resolution.fixtures import sc4_replace_clutch


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def test_corpus_floor() -> None:
    assert len(all_cases()) >= 150


@pytest.mark.parametrize("case", ANCHOR_CASES, ids=lambda c: c.case_id)
def test_anchor_matrix(case) -> None:
    proposal = case.factory()
    outcome = proposal_to_canonical_ir(proposal)
    result = outcome.result

    if case.expect == "partial_non_materialized":
        assert event_assertion_present(result)
        assert event_semantically_preserved(outcome)
        assert outcome.ir is not None
        assert outcome.ir.event is None
        assert outcome.ir.measurement is not None
        assert PrimitiveKind.EVENT in result.non_materialized_primitives
        assert not event_false_canonicalization(outcome)
    elif case.expect == "measurement_only":
        assert not event_assertion_present(result)
        assert outcome.ir is not None
        assert outcome.ir.event is None
        assert outcome.ir.measurement is not None
        assert PrimitiveKind.EVENT not in result.non_materialized_primitives
    elif case.expect == "resolved_materialized":
        assert outcome.ir is not None
        assert outcome.ir.event is not None
        assert outcome.ir.event.type.key in ConceptCatalog.event_types
        assert outcome.ir.event.type.key != "event.intent" or result.concepts.event_type == "event.intent"
        assert PrimitiveKind.EVENT not in result.non_materialized_primitives


def test_mp5_no_non_materialized_event() -> None:
    outcome = proposal_to_canonical_ir(mp5())
    assert PrimitiveKind.EVENT not in outcome.result.non_materialized_primitives
    assert outcome.ir is not None and outcome.ir.event is None


def test_ms18_partial_flow() -> None:
    outcome = proposal_to_canonical_ir(ms18_i126())
    assert event_semantically_preserved(outcome)
    assert outcome.ir.event is None
    assert outcome.ir.measurement is not None
    assert "event_category_unresolved_safe_partial" in outcome.result.non_materialized_reasons


def test_no_event_intent_false_fallback_on_mp1() -> None:
    outcome = proposal_to_canonical_ir(mp1())
    if outcome.ir and outcome.ir.event:
        assert outcome.ir.event.type.key != "event.intent"
    assert not event_false_canonicalization(outcome)


def test_legitimate_event_intent_when_resolver_sets_type() -> None:
    """event.intent wireable only when concepts.event_type is legitimately resolved."""
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime

    proposal = SemanticProposal(
        raw_input="Pretendo trocar a embreagem.",
        object=SemanticEntityMention(text="embreagem", kind_hint="thing"),
        action_expression="pretendo trocar",
        change_semantics=True,
        temporal=SemanticTime(occurrence_aspect="planned"),
    )
    concepts = ResolvedConcepts(
        primitive=PrimitiveKind.EVENT,
        event_type="event.intent",
        confidence=ResolutionConfidence.CONTEXTUAL,
        provenance=ResolutionProvenance.SEMANTIC,
        resolution_status=ResolutionStatus.RESOLVED,
    )
    assert event_type_for_wire(concepts, proposal) == "event.intent"
    assessment = assess_persistability(
        ResolutionResult(
            proposal=proposal,
            primitive=PrimitiveKind.EVENT,
            concepts=concepts,
            assertions=[],
        )
    )
    assert assessment.wire_allowed is True


@pytest.mark.parametrize("case", partial_event_cases(), ids=lambda c: c.case_id)
def test_partial_events_never_false_canonicalized(case) -> None:
    outcome = proposal_to_canonical_ir(case.factory())
    assert not event_false_canonicalization(outcome)
    assert event_semantically_preserved(outcome)


def test_safety_metrics_zero() -> None:
    false_canon = silent = fake_persist = unsupported = resolved_nm = 0
    preserved_nm = resolved_mat = meas_with_partial = 0
    for case in all_cases():
        proposal = case.factory()
        outcome = proposal_to_canonical_ir(proposal)
        result = outcome.result
        if event_false_canonicalization(outcome):
            false_canon += 1
        if event_assertion_present(result) and not event_semantically_preserved(outcome):
            silent += 1
        if outcome.ir and outcome.ir.event and outcome.ir.event.type.key == "event.intent":
            if result.concepts.event_type != "event.intent":
                fake_persist += 1
        exp = case.expect
        if exp == "measurement_only" and event_assertion_present(result):
            unsupported += 1
        if exp == "resolved_materialized" and PrimitiveKind.EVENT in result.non_materialized_primitives:
            resolved_nm += 1
        if (
            exp == "partial_non_materialized"
            and PrimitiveKind.EVENT in result.non_materialized_primitives
        ):
            preserved_nm += 1
        if exp == "resolved_materialized" and outcome.ir and outcome.ir.event:
            resolved_mat += 1
        if (
            outcome.ir
            and outcome.ir.measurement
            and PrimitiveKind.EVENT in result.non_materialized_primitives
        ):
            meas_with_partial += 1
    assert false_canon == 0
    assert silent == 0
    assert fake_persist == 0
    assert unsupported == 0
    assert resolved_nm == 0
    assert preserved_nm > 0
    assert resolved_mat > 0
    assert meas_with_partial > 0


def test_mp_matrix_artifact() -> None:
    rows = []
    for case in ANCHOR_CASES:
        p = case.factory()
        r = resolve_proposal(p)
        o = proposal_to_canonical_ir(p)
        wire_evt = o.ir.event is not None if o.ir else False
        rows.append(
            {
                "case": case.case_id,
                "proposal": "E+M" if case.expect == "partial_non_materialized" else case.expect,
                "resolution": "E partial" if PrimitiveKind.EVENT in r.non_materialized_primitives else "E resolved",
                "persistability": "E wire-blocked" if PrimitiveKind.EVENT in r.non_materialized_primitives else "E allowed",
                "wire": "M" if o.ir and o.ir.measurement and not wire_evt else "E+M" if wire_evt else "M",
                "persisted": "M" if o.ir and o.ir.measurement and not wire_evt else "E+M",
                "non_materialized": "E" if PrimitiveKind.EVENT in r.non_materialized_primitives else "NONE",
            }
        )
    path = Path("docs/reports/I12.7.1-MP-MATRIX.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def test_correction_guard_unchanged() -> None:
    from pke.interpretation.acceptance.correction_guard import (
        AcceptanceOutcome,
        evaluate_correction_acceptance,
    )
    from tests.interpreter_acceptance_guard.corpus import CAPTURED_S4

    blocked = sum(
        1
        for c in CAPTURED_S4
        if evaluate_correction_acceptance(
            c.utterance, proposed_as_correction=True
        ).outcome
        is not AcceptanceOutcome.ACCEPT
    )
    assert blocked == 9


def test_core_frozen() -> None:
    assert len(list(OntologyRegistry.with_core_seeds().concepts())) == 67


def test_resolved_event_still_materializes() -> None:
    outcome = proposal_to_canonical_ir(sc4_replace_clutch())
    assert outcome.ir is not None
    assert outcome.ir.event is not None
    assert outcome.ir.event.type.key == "event.maintenance"


def test_i127_r_false_intent_replay_regression() -> None:
    """Reproduce I12.7-R proposals that received false event.intent — expect non-materialized."""
    path = Path("docs/reports/i127_artifacts/checkpoint.jsonl")
    if not path.is_file():
        pytest.skip("I12.7-R artifacts not present")

    false_intent = 0
    replayed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        audit = row.get("canonicalization_audit") or {}
        if audit.get("EVENT_TYPE_ASSIGNED") != "event.intent":
            continue
        dump = row.get("proposal_dump")
        if not dump:
            continue
        false_intent += 1
        proposal = SemanticProposal.model_validate(dump)
        outcome = proposal_to_canonical_ir(proposal)
        assert not event_false_canonicalization(outcome)
        if event_assertion_present(outcome.result):
            assert event_semantically_preserved(outcome)
            assert (
                outcome.ir is None
                or outcome.ir.event is None
                or outcome.ir.event.type.key != "event.intent"
            )
        replayed += 1
    assert false_intent > 0
    assert replayed == false_intent
