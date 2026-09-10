"""I12.5 — Multi-primitive routing hardening tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.router import collect_assertions, route_primitive
from tests.multi_primitive_routing_hardening.corpus import (
    ANCHORS,
    CAPTURED,
    all_cases,
    mp1,
    mp2,
    mp3,
    mp4,
    mp5,
)


@pytest.mark.parametrize("case", all_cases(), ids=lambda c: c.case_id)
def test_mp_routing_case(case) -> None:
    proposal = case.factory()
    frames = collect_assertions(proposal)
    got = frozenset(f.primitive for f in frames)
    assert got == case.expected, (
        f"{case.case_id}: got {sorted(p.value for p in got)} "
        f"expected {sorted(p.value for p in case.expected)}"
    )
    # No duplicates
    assert len(frames) == len(got)


def test_corpus_floor() -> None:
    assert len(all_cases()) >= 200
    assert len(ANCHORS) == 5


@pytest.mark.parametrize("case", ANCHORS, ids=lambda c: c.case_id)
def test_mp_anchors_frozen(case) -> None:
    frames = collect_assertions(case.factory())
    assert frozenset(f.primitive for f in frames) == case.expected


def test_mp5_no_false_event() -> None:
    frames = collect_assertions(mp5())
    assert [f.primitive for f in frames] == [PrimitiveKind.MEASUREMENT]
    assert route_primitive(mp5())[0] is PrimitiveKind.MEASUREMENT


def test_ms18_engine_preserve_without_change_flag() -> None:
    case = next(c for c in CAPTURED if c.case_id == "MS18_ENGINE_PRESERVE")
    frames = collect_assertions(case.factory())
    assert {f.primitive for f in frames} == {
        PrimitiveKind.EVENT,
        PrimitiveKind.MEASUREMENT,
    }


def test_ms18_interpreter_omission_does_not_invent_event() -> None:
    case = next(c for c in CAPTURED if c.case_id == "MS18_INTERPRETER_OMISSION")
    frames = collect_assertions(case.factory())
    assert [f.primitive for f in frames] == [PrimitiveKind.MEASUREMENT]


def test_explicit_assertion_preservation_rate() -> None:
    """Engine-only: when proposal already encodes expected frames, preserve 100%."""
    preserved = total = 0
    false_add = 0
    for case in all_cases():
        if not case.explicit_on_proposal:
            continue
        total += 1
        frames = collect_assertions(case.factory())
        got = frozenset(f.primitive for f in frames)
        if case.expected <= got and got <= case.expected:
            preserved += 1
        extra = got - case.expected
        if extra:
            false_add += 1
    rate = preserved / total if total else 0.0
    assert rate == 1.0, f"preservation {rate}"
    assert false_add == 0


def test_no_duplicate_same_primitive() -> None:
    for factory in (mp1, mp2, mp3, mp4, mp5):
        frames = collect_assertions(factory())
        kinds = [f.primitive for f in frames]
        assert len(kinds) == len(set(kinds))


def test_event_only_does_not_invent_measurement() -> None:
    from tests.multi_primitive_routing_hardening.corpus import _e_only

    case = _e_only("X", "Pesei a caixa.", action="pesei", obj="caixa")
    frames = collect_assertions(case.factory())
    assert [f.primitive for f in frames] == [PrimitiveKind.EVENT]


def test_safety_counters_zero() -> None:
    """§61 safety targets on deterministic explicit-proposal corpus."""
    lost = false_event = false_meas = dup_e = dup_m = 0
    for case in all_cases():
        frames = collect_assertions(case.factory())
        kinds = [f.primitive for f in frames]
        got = set(kinds)
        if len(kinds) != len(got):
            if PrimitiveKind.EVENT in kinds and kinds.count(PrimitiveKind.EVENT) > 1:
                dup_e += 1
            if PrimitiveKind.MEASUREMENT in kinds and kinds.count(PrimitiveKind.MEASUREMENT) > 1:
                dup_m += 1
        if case.expected - got:
            # missing expected on explicit proposal = loss
            if case.explicit_on_proposal:
                lost += 1
        extra = got - case.expected
        if PrimitiveKind.EVENT in extra:
            false_event += 1
        if PrimitiveKind.MEASUREMENT in extra:
            false_meas += 1
    assert lost == 0
    assert false_event == 0
    assert false_meas == 0
    assert dup_e == 0
    assert dup_m == 0


def test_i123_mp_ledger_file_exists_or_write() -> None:
    """Failure ledger artifact for I12.5 analysis (§13)."""
    path = Path("docs/reports/I12.5-MP-FAILURE-LEDGER.json")
    assert path.exists(), "ledger must be written by I12.5 close"


def test_correction_guard_still_blocks_s4() -> None:
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
