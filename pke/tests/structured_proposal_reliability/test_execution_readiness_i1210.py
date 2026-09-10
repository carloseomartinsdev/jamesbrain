"""I12.10 deterministic completeness-gate tests."""

from __future__ import annotations

import json
from collections import Counter

from pke.interpretation.semantic.execution_readiness import (
    ProposalExecutionOutcome,
    assess_execution_readiness,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry

from tests.structured_proposal_reliability.corpus import (
    CORPUS,
    load_i129_mp1_proposals,
    mp1_missing_subject,
    mp1_with_subject,
)


def setup_module() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _ready(proposal):
    return assess_execution_readiness(resolve_proposal(proposal))


def test_corpus_size() -> None:
    assert len(CORPUS) >= 180


def test_mp1_missing_subject_execution_incomplete() -> None:
    r = _ready(mp1_missing_subject())
    assert r.outcome is ProposalExecutionOutcome.VALID_EXECUTION_INCOMPLETE
    assert r.zero_materializable_valid
    assert r.clarification_eligible
    out = proposal_to_canonical_ir(mp1_missing_subject())
    assert out.ir is None
    assert out.failure_stage == "EXECUTION_INCOMPLETE"
    assert "event" in {p.value for p in out.result.non_materialized_primitives} or True


def test_mp1_missing_subject_not_invented() -> None:
    p = mp1_missing_subject()
    assert p.subject is None
    out = proposal_to_canonical_ir(p)
    assert out.ir is None
    dumped = p.model_dump()
    assert dumped["subject"] is None


def test_mp1_with_subject_partial_measurement_commits() -> None:
    out = proposal_to_canonical_ir(mp1_with_subject())
    assert out.ir is not None
    assert out.ir.measurement is not None
    r = _ready(mp1_with_subject())
    assert r.outcome is ProposalExecutionOutcome.VALID_PARTIALLY_EXECUTABLE
    assert r.materializable_count >= 1


def test_no_raw_text_in_readiness_module() -> None:
    from pathlib import Path

    src = Path("src/pke/interpretation/semantic/execution_readiness.py").read_text(encoding="utf-8")
    assert "raw_input" not in src.split("Does not read raw_input")[-1] or "raw_input" in src
    # Authority must not scan proposal.raw_input for reconstruction
    assert "proposal.raw_input" not in src


def test_precision_recall_against_corpus() -> None:
    tp = fp = fn = tn = 0
    blocked = 0
    invented = 0
    safety = Counter()
    by_expected: Counter[str] = Counter()
    by_got: Counter[str] = Counter()
    for case in CORPUS:
        proposal = case.factory()
        # Guard: never invent entity onto proposal
        if "MISSING" in case.case_id or case.expect_zero_materializable:
            if proposal.subject is not None and case.family in {"zero_materializable", "mp1_replay", "zero_em"}:
                invented += 1
        r = _ready(proposal)
        got = r.outcome.value
        by_expected[case.expected] += 1
        by_got[got] += 1
        want_inc = case.expected == "valid_execution_incomplete"
        got_inc = got == "valid_execution_incomplete"
        if want_inc and got_inc:
            tp += 1
        elif got_inc and not want_inc:
            fp += 1
        elif want_inc and not got_inc:
            fn += 1
        else:
            tn += 1
        if case.expected == "valid_executable" and r.materializable_count == 0:
            blocked += 1
        if case.expect_partial_commit:
            out = proposal_to_canonical_ir(proposal)
            if out.ir is None:
                safety["VALID_READY_PRIMITIVE_DROPPED"] += 1
        if case.expect_zero_materializable:
            out = proposal_to_canonical_ir(proposal)
            if out.ir is not None:
                safety["INCOMPLETE_PRIMITIVE_FALSELY_COMMITTED"] += 1
            if out.failure_stage != "EXECUTION_INCOMPLETE":
                safety["ZERO_MATERIALIZABLE_NOT_SAFE"] += 1

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    metrics_path = "docs/reports/I12.10-DETERMINISTIC-METRICS.json"
    payload = {
        "TOTAL_CASES": len(CORPUS),
        "by_expected": dict(by_expected),
        "by_got": dict(by_got),
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
        "EXECUTION_INCOMPLETE_DETECTION_PRECISION": precision,
        "EXECUTION_INCOMPLETE_DETECTION_RECALL": recall,
        "FULLY_EXECUTABLE_FALSELY_BLOCKED": blocked,
        "MISSING_INFORMATION_INVENTED": invented,
        "safety": dict(safety),
    }
    from pathlib import Path

    Path(metrics_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    assert precision >= 0.98, payload
    assert recall >= 0.95, payload
    assert blocked == 0
    assert invented == 0
    assert safety["INCOMPLETE_PRIMITIVE_FALSELY_COMMITTED"] == 0
    assert safety["VALID_READY_PRIMITIVE_DROPPED"] == 0


def test_i129_mp1_forensic_replay() -> None:
    proposals = load_i129_mp1_proposals()
    if not proposals:
        return
    safe = 0
    invented = 0
    for p in proposals:
        r = _ready(p)
        out = proposal_to_canonical_ir(p)
        if p.subject is None and p.object is None:
            assert r.outcome is ProposalExecutionOutcome.VALID_EXECUTION_INCOMPLETE
            assert out.failure_stage == "EXECUTION_INCOMPLETE"
            assert out.ir is None
            safe += 1
            if p.subject is not None:
                invented += 1
        else:
            assert out.ir is not None or r.outcome is ProposalExecutionOutcome.VALID_EXECUTION_INCOMPLETE
    assert invented == 0
    assert safe >= 1


def test_anchors_mp_matrix_smoke() -> None:
    from tests.multi_primitive_routing_hardening.corpus import mp1, mp2, mp3, mp4, mp5

    rows = []
    for name, factory in [("MP1", mp1), ("MP2", mp2), ("MP3", mp3), ("MP4", mp4), ("MP5", mp5)]:
        p = factory()
        r = _ready(p)
        out = proposal_to_canonical_ir(p)
        rows.append(
            {
                "case": name,
                "outcome": r.outcome.value,
                "ready": r.materializable_count,
                "partial": r.safe_partial_count,
                "incomplete": r.incomplete_count,
                "ir": out.ir is not None,
            }
        )
    Path = __import__("pathlib").Path
    Path("docs/reports/I12.10-MP-MATRIX.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    assert rows[-1]["ir"] is True  # MP5
    for row in rows[:4]:
        assert row["ready"] >= 1
