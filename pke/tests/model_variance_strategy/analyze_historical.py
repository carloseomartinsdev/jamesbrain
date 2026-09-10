"""Analyze historical live artifacts for I12.9 (no provider calls)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from tests.engine_v1_baseline.corpus import CORPUS
from tests.model_variance_strategy.failure_taxonomy import (
    MP1SubClass,
    PrimaryFailure,
    classify_run,
    trace_from_raw,
)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATHS = (
    ROOT / "docs" / "reports" / "i126_artifacts" / "baseline_deepseek_chat.jsonl",
    ROOT / "docs" / "reports" / "i127_artifacts" / "checkpoint.jsonl",
    ROOT / "docs" / "reports" / "i128_artifacts" / "checkpoint.jsonl",
)


def _case_by_id(case_id: str):
    for c in CORPUS:
        if c.id == case_id:
            return c
    return None


def analyze_artifacts() -> dict:
    by_id = {c.id: c for c in CORPUS}
    primary = Counter()
    mp1_sub = Counter()
    stage_fault = Counter()
    mp1_rows: list[dict] = []
    total = 0

    for path in ARTIFACT_PATHS:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            case_id = row.get("case_id")
            if case_id not in by_id:
                continue
            case = by_id[case_id]
            raw = row.get("raw_content")
            # Historical runners omitted raw on exception — try proposal_dump
            if not raw and row.get("proposal_dump"):
                raw = json.dumps(
                    {"ir_kind": "semantic_proposal", "ir": row["proposal_dump"]},
                    ensure_ascii=False,
                )
            err = row.get("error")
            ir_ok = bool(row.get("FINAL_MEASUREMENT_PRESENT") or row.get("FINAL_EVENT_SEMANTIC"))
            if row.get("post_score"):
                ir_ok = row["post_score"].get("ok", False) or ir_ok

            cls = classify_run(case, raw_content=raw, interpret_error=err, ir_ok=ir_ok)
            primary[cls.primary] += 1
            if cls.trace.first_fault_stage:
                stage_fault[cls.trace.first_fault_stage] += 1
            if cls.mp1_subclass:
                mp1_sub[cls.mp1_subclass.value] += 1
            if case.utterance.casefold().startswith("medi a temperatura e deu 95"):
                mp1_rows.append(
                    {
                        "experiment": row.get("experiment_id"),
                        "run": row.get("run"),
                        "provider_valid": cls.trace.provider_response_present,
                        "proposal_valid": cls.trace.proposal_valid,
                        "event_evidence": cls.event_evidence_on_proposal,
                        "event_primitive": "event" in cls.observed_primitive_set,
                        "resolution": cls.trace.failure_stage or ("OK" if cls.trace.outcome_ir else "FAIL"),
                        "primary": cls.primary,
                        "mp1_sub": cls.mp1_subclass.value if cls.mp1_subclass else None,
                        "inconsistencies": list(cls.trace.internal_inconsistencies),
                    }
                )
            total += 1

    return {
        "HISTORICAL_ROWS_ANALYZED": total,
        "PRIMARY_FAILURE_DISTRIBUTION": dict(primary),
        "FIRST_FAULT_STAGE": dict(stage_fault),
        "MP1_SUBCLASS": dict(mp1_sub),
        "MP1_FORENSIC": mp1_rows,
    }


if __name__ == "__main__":
    print(json.dumps(analyze_artifacts(), indent=2))
