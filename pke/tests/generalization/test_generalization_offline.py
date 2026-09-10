"""Testes offline da infraestrutura do benchmark I11 (sem provider live)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from pke.interpretation.models import IngestIR, IngestIntent, IrEvent, IrFact, IrTime, EntityMention
from pke.domain import ConceptRef, EventStatus, Qualifier, EpistemicStatus, RelativeDay

from tests.generalization.cases import (
    BENCHMARK,
    DEVELOPMENT_CASES,
    HOLDOUT_CASES,
    GeneralizationCase,
    _ACCEPTANCE_TEXTS,
)
from tests.generalization.invariants import check_forbidden, check_semantic, stability_label
from tests.generalization.cases import FailureCategory
from tests.generalization.evaluator import compute_global_metrics, RunResult


def test_benchmark_sizes() -> None:
    assert len(DEVELOPMENT_CASES) == 30
    assert len(HOLDOUT_CASES) == 15
    assert len(BENCHMARK.all_cases) == 45


def test_no_acceptance_text_overlap() -> None:
    all_texts: set[str] = set()
    for case in BENCHMARK.all_cases:
        all_texts.update(case.all_texts())
    assert all_texts.isdisjoint(_ACCEPTANCE_TEXTS)


def test_each_case_has_metadata() -> None:
    for case in BENCHMARK.all_cases:
        assert case.case_id
        assert case.raw_text
        assert case.domain_hint
        assert case.expected_capability
        assert case.expected_invariants is not None


def test_equiv_groups_have_four_variants() -> None:
    equiv = [c for c in DEVELOPMENT_CASES if c.case_id.startswith("EQUIV_")]
    assert len(equiv) == 5
    for case in equiv:
        assert len(case.variants) == 4


def test_semantic_invariant_yesterday() -> None:
    ir = IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input="Troquei a resistência do chuveiro ontem.",
        domains=[ConceptRef(key="domain.home")],
        entities_mentioned=[EntityMention(text="chuveiro")],
        event=IrEvent(
            type=ConceptRef(key="event.home_maintenance"),
            action=ConceptRef(key="action.replace"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text="ontem", relative_day=RelativeDay.YESTERDAY),
            facts=[],
        ),
    )
    case = next(c for c in DEVELOPMENT_CASES if c.case_id == "HOME_002")
    fails = check_semantic(ir, case.expected_invariants)
    assert fails == []


def test_forbidden_invented_date() -> None:
    ir = IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input="A geladeira começou a fazer um barulho estranho.",
        event=IrEvent(
            type=ConceptRef(key="event.anomaly"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text="hoje", relative_day=RelativeDay.TODAY, date=__import__("datetime").date(2026, 9, 1)),
            facts=[],
        ),
    )
    case = next(c for c in DEVELOPMENT_CASES if c.case_id == "HOME_001")
    hits = check_forbidden(ir, list(case.forbidden_inferences))
    assert "invented_absolute_date" in hits


def test_stability_labels() -> None:
    assert "stable" in stability_label(3, 3)
    assert "acceptable" in stability_label(2, 3)
    assert "weak" in stability_label(1, 3)
    assert "failed" in stability_label(0, 3)


def test_global_metrics_empty() -> None:
    m = compute_global_metrics([])
    assert m["total_runs"] == 1  # divisor guard


def test_global_metrics_sample() -> None:
    runs = [
        RunResult(
            case_id="X",
            run=1,
            text="t",
            provider_json_valid=True,
            wire_valid=True,
            canonical_valid=True,
            semantic_required_pass=True,
        ),
        RunResult(
            case_id="X",
            run=2,
            text="t",
            provider_json_valid=False,
            failure_category=FailureCategory.PROVIDER,
        ),
    ]
    m = compute_global_metrics(runs)
    assert m["provider_json_valid_rate"] == 0.5
    assert m["semantic_accuracy"] == 0.5
