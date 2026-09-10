"""I12.7 — Event routing & canonicalization preservation (downstream)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.event_preservation import event_semantically_preserved
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.interpretation.transport.proposal_wire import WireSemanticProposal
from pke.ontology.registry import OntologyRegistry
from tests.multi_primitive_routing_hardening.corpus import CAPTURED, mp1, mp2, mp3, mp4, mp5
from tests.event_routing_hardening.corpus import (
    all_cases,
    anchor_cases,
    explicit_event_cases,
    ms18_i126,
)
from tests.event_routing_hardening.stage_trace import stage_matrix_row, trace_event_routing


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _outcome_primitives(proposal):
    outcome = proposal_to_canonical_ir(proposal)
    ir = outcome.ir
    found: set[PrimitiveKind] = set()
    if event_semantically_preserved(outcome):
        found.add(PrimitiveKind.EVENT)
    elif ir is not None and ir.event is not None:
        found.add(PrimitiveKind.EVENT)
    if ir is not None and ir.measurement is not None:
        found.add(PrimitiveKind.MEASUREMENT)
    if ir is None:
        return outcome, found
    if ir.state is not None:
        found.add(PrimitiveKind.STATE)
    if ir.relation is not None:
        found.add(PrimitiveKind.RELATION)
    if ir.attribute is not None:
        found.add(PrimitiveKind.ATTRIBUTE)
    return outcome, found


@pytest.mark.parametrize("case", anchor_cases(), ids=lambda c: c.case_id)
def test_mp_ms18_anchor_downstream(case) -> None:
    proposal = case.factory()
    _, got = _outcome_primitives(proposal)
    if case.expect_event:
        assert PrimitiveKind.EVENT in got, f"{case.case_id}: Event lost downstream"
    else:
        assert PrimitiveKind.EVENT not in got, f"{case.case_id}: unsupported Event added"
    if case.expect_measurement:
        assert PrimitiveKind.MEASUREMENT in got
    else:
        assert PrimitiveKind.MEASUREMENT not in got


def test_corpus_floor() -> None:
    assert len(all_cases()) >= 200
    assert len(anchor_cases()) >= 6


@pytest.mark.parametrize("case", explicit_event_cases(), ids=lambda c: c.case_id)
def test_explicit_event_preserved_downstream(case) -> None:
    proposal = case.factory()
    trace = trace_event_routing(proposal, case_id=case.case_id)
    assert trace.final_event_present, (
        f"{case.case_id} lost Event at {trace.loss_taxonomy} "
        f"(proposal={trace.proposal_event_present} "
        f"assertions={trace.assertion_event_present} "
        f"resolution={trace.resolution_event_present} "
        f"materialization={trace.materialization_event_present})"
    )


def test_mp5_measurement_only_no_event() -> None:
    _, got = _outcome_primitives(mp5())
    assert got == {PrimitiveKind.MEASUREMENT}


def test_ms18_i126_stage_loss_closed() -> None:
    trace = trace_event_routing(ms18_i126(), case_id="MS18")
    assert trace.loss_taxonomy is None
    assert trace.final_event_present
    assert trace.final_event_present and trace.s8_engine_outcome.measurement_present


def test_ms18_interpreter_omission_no_event_invention() -> None:
    case = next(c for c in CAPTURED if c.case_id == "MS18_INTERPRETER_OMISSION")
    _, got = _outcome_primitives(case.factory())
    assert PrimitiveKind.EVENT not in got
    assert PrimitiveKind.MEASUREMENT in got


def test_safety_counters_zero() -> None:
    lost = unsupported = dup_e = meas_lost = 0
    state_mis = rel_mis = attr_mis = 0
    for case in all_cases():
        proposal = case.factory()
        _, got = _outcome_primitives(proposal)
        if case.explicit_event_on_proposal and case.expect_event:
            if PrimitiveKind.EVENT not in got:
                lost += 1
        if not case.expect_event and PrimitiveKind.EVENT in got:
            unsupported += 1
        if case.expect_measurement and PrimitiveKind.MEASUREMENT not in got:
            meas_lost += 1
        if case.family == "state" and PrimitiveKind.EVENT in got:
            state_mis += 1
        if case.family == "relation" and PrimitiveKind.EVENT in got:
            rel_mis += 1
        if case.family == "attribute" and PrimitiveKind.EVENT in got:
            attr_mis += 1
    assert lost == 0
    assert unsupported == 0
    assert dup_e == 0
    assert meas_lost == 0
    assert state_mis == 0
    assert rel_mis == 0
    assert attr_mis == 0


def test_explicit_event_preservation_rate() -> None:
    cases = explicit_event_cases()
    preserved = sum(
        1
        for c in cases
        if trace_event_routing(c.factory(), case_id=c.case_id).final_event_present
    )
    rate = preserved / len(cases) if cases else 0.0
    assert rate == 1.0


def test_stage_matrix_anchors() -> None:
    rows = [
        stage_matrix_row(trace_event_routing(c.factory(), case_id=c.case_id))
        for c in anchor_cases()
    ]
    path = Path("docs/reports/I12.7-STAGE-MATRIX-ANCHORS.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    for row in rows:
        if "E" in row["proposal"] or "E" in row["assertions"]:
            assert "E" in row["post"], row


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


def test_can_event_preservation_invent_event() -> None:
    """Safety §6: NO — measurement-only proposals must not gain Event."""
    case = next(c for c in CAPTURED if c.case_id == "MS18_INTERPRETER_OMISSION")
    trace = trace_event_routing(case.factory(), case_id="MS18_INTERPRETER_OMISSION")
    assert not trace.proposal_event_present
    assert not trace.final_event_present
