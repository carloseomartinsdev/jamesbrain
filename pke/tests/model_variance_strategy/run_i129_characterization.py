"""I12.9 live characterization runner — prompt v4 only.

Usage:
  .\\.venv\\Scripts\\python.exe -m tests.model_variance_strategy.run_i129_characterization

Env:
  DEEPSEEK_API_KEY required
  PKE_I129_LIMIT=0
  PKE_I129_RESUME=1
  PKE_I129_MP1_ONLY=1  (MP1 forensic only)
  PKE_I129_DUAL=1      (dual-sample subset)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "src", _ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.semantic.event_preservation import event_semantically_preserved
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION

from tests.engine_v1_baseline.corpus import EngineCase
from tests.event_interpreter_hardening.corpus import mp_label
from tests.model_provider_evaluation.candidates import all_candidates, build_provider
from tests.model_variance_strategy.analyze_historical import analyze_artifacts
from tests.model_variance_strategy.corpus import DUAL_SAMPLE_CASES, I129_CORPUS
from tests.model_variance_strategy.failure_taxonomy import (
    audit_proposal_inconsistencies,
    classify_run,
    trace_from_raw,
)

EXPERIMENT_ID = os.environ.get("PKE_I129_EXPERIMENT", "I12.9")
ROOT = _ROOT
ARTIFACT_DIR = ROOT / "docs" / "reports" / "i129_artifacts"
CHECKPOINT = ARTIFACT_DIR / "checkpoint.jsonl"
FREEZE_JSON = ARTIFACT_DIR / "FREEZE.json"
SUMMARY_JSON = ROOT / "docs" / "reports" / "I12.9-MODEL-VARIANCE-STRATEGY.json"
SUMMARY_MD = ROOT / "docs" / "reports" / "I12.9-MODEL-VARIANCE-STRATEGY.md"
FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = datetime(2026, 9, 3, 18, 0, tzinfo=FORTALEZA)


def load_env_silent() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _reps(case: EngineCase) -> int:
    if mp_label(case) or case.utterance.casefold().startswith("medi a temperatura"):
        return 5
    return 3


def _ctx() -> InterpretationContext:
    return InterpretationContext(
        user=UserContext(user_id="i129-char", timezone="America/Fortaleza", now=NOW)
    )


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return None


def _done_keys() -> set[tuple[str, int, str]]:
    if not CHECKPOINT.is_file():
        return set()
    done: set[tuple[str, int, str]] = set()
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("experiment_id") == EXPERIMENT_ID:
            done.add((r["case_id"], int(r["run"]), r.get("sample_id", "A")))
    return done


def _disagreement(a: dict, b: dict) -> dict[str, bool]:
    return {
        "intent": a.get("utterance_kind") != b.get("utterance_kind"),
        "primitive_set": set(a.get("assertion_kinds") or []) != set(b.get("assertion_kinds") or []),
        "event_presence": a.get("event_evidence") != b.get("event_evidence"),
        "measurement_presence": a.get("measurement_evidence") != b.get("measurement_evidence"),
        "correction_intent": a.get("correction_semantics") != b.get("correction_semantics"),
    }


def _proposal_summary(proposal) -> dict | None:
    if proposal is None:
        return None
    from pke.interpretation.semantic.multi_primitive_evidence import (
        has_explicit_occurrence_evidence,
        has_measurement_evidence,
    )
    from pke.interpretation.semantic.router import collect_assertions

    kinds = [f.primitive.value for f in collect_assertions(proposal)]
    return {
        "utterance_kind": proposal.utterance_kind,
        "assertion_kinds": kinds,
        "event_evidence": has_explicit_occurrence_evidence(proposal),
        "measurement_evidence": has_measurement_evidence(proposal),
        "correction_semantics": proposal.correction_semantics,
        "inconsistencies": list(audit_proposal_inconsistencies(proposal)),
    }


def run_one(
    interpreter: DeepSeekInterpreter,
    case: EngineCase,
    *,
    run_no: int,
    sample_id: str = "A",
) -> dict:
    logical_id = str(uuid.uuid4())
    t0 = time.perf_counter()
    raw_content = None
    first_raw = None
    error = None
    ir = None
    attempts = 1
    trace = None

    try:
        ir = interpreter.interpret(case.utterance, _ctx())
        attempts = interpreter.last_provider_attempts or 1
        raw_content = interpreter.last_raw_content
        first_raw = raw_content
    except InterpretationError as exc:
        error = str(exc)
        attempts = interpreter.last_provider_attempts or 1
        raw_content = interpreter.last_raw_content
        first_raw = raw_content
        if interpreter.last_request_trace and interpreter.last_request_trace.attempts:
            first_raw = interpreter.last_request_trace.attempts[0].provider_request_id  # placeholder
        # Capture first attempt raw from trace if available
        trace_obj = interpreter.last_request_trace
        if trace_obj and len(trace_obj.attempts) >= 1:
            first_raw = raw_content  # same content on semantic failure (single attempt typical)

    latency_ms = (time.perf_counter() - t0) * 1000
    tr = trace_from_raw(raw_content, interpret_error=error)
    outcome = proposal_to_canonical_ir(tr.proposal) if tr.proposal else None
    ir_ok = ir is not None or (outcome and outcome.ir is not None)
    cls = classify_run(
        case,
        raw_content=raw_content,
        interpret_error=error,
        ir_ok=ir_ok,
        attempts=attempts,
        first_attempt_raw=raw_content,
        trace=tr,
    )

    prop_summary = _proposal_summary(tr.proposal)
    downstream_loss = False
    if tr.proposal and cls.event_evidence_on_proposal and outcome:
        downstream_loss = not event_semantically_preserved(outcome)

    return {
        "experiment_id": EXPERIMENT_ID,
        "case_id": case.id,
        "run": run_no,
        "sample_id": sample_id,
        "utterance": case.utterance,
        "category": case.category,
        "expected_primitive": case.expected_primitive,
        "logical_request_id": logical_id,
        "prompt_version": PROMPT_VERSION_V4,
        "attempts": attempts,
        "latency_ms": latency_ms,
        "raw_content": raw_content,
        "proposal_dump": tr.proposal.model_dump() if tr.proposal else None,
        "proposal_summary": prop_summary,
        "primary_failure": cls.primary,
        "secondary_labels": list(cls.secondary),
        "mp1_subclass": cls.mp1_subclass.value if cls.mp1_subclass else None,
        "first_fault_stage": cls.trace.first_fault_stage,
        "internal_inconsistencies": list(cls.trace.internal_inconsistencies),
        "interpret_error": error,
        "outcome_ir": cls.trace.outcome_ir,
        "wire_built": cls.trace.wire_built,
        "DOWNSTREAM_INFORMATION_LOSS": downstream_loss,
        "event_evidence_on_proposal": cls.event_evidence_on_proposal,
        "event_in_assertions": cls.event_in_assertions,
        "observed_primitive_set": list(cls.observed_primitive_set),
    }


def aggregate(rows: list[dict]) -> dict:
    primary = Counter(r["primary_failure"] for r in rows)
    stages = Counter(r.get("first_fault_stage") for r in rows if r.get("first_fault_stage"))
    valid_proposal = sum(1 for r in rows if r.get("proposal_dump"))
    useful = sum(
        1
        for r in rows
        if r.get("proposal_dump")
        and r.get("primary_failure") in {"CORRECT", "SAFE_ABSTENTION", "SEMANTIC_OMISSION", "WRONG_SEMANTIC_DECISION"}
    )
    inconsistent = sum(1 for r in rows if r.get("internal_inconsistencies"))
    downstream = sum(1 for r in rows if r.get("DOWNSTREAM_INFORMATION_LOSS"))
    first_valid = sum(1 for r in rows if r.get("proposal_dump") and int(r.get("attempts", 1)) == 1)
    retry_trig = sum(1 for r in rows if int(r.get("attempts", 1)) > 1)
    mp1 = [r for r in rows if r.get("mp1_subclass")]

    # Dual sample disagreement
    dual_disagree = 0
    dual_total = 0
    by_case_sample: dict[tuple[str, int], dict[str, dict]] = defaultdict(dict)
    for r in rows:
        if r.get("sample_id") in {"A", "B"}:
            by_case_sample[(r["case_id"], r["run"])][r["sample_id"]] = r.get("proposal_summary") or {}
    for summaries in by_case_sample.values():
        if "A" in summaries and "B" in summaries and summaries["A"] and summaries["B"]:
            dual_total += 1
            d = _disagreement(summaries["A"], summaries["B"])
            if any(d.values()):
                dual_disagree += 1

    return {
        "TOTAL_RUNS": len(rows),
        "PRIMARY_FAILURE": dict(primary),
        "FIRST_FAULT_STAGE": dict(stages),
        "VALID_SEMANTIC_PROPOSAL_RATE": valid_proposal / len(rows) if rows else 0,
        "VALID_AND_SEMANTICALLY_USEFUL_PROPOSAL_RATE": useful / len(rows) if rows else 0,
        "FIRST_ATTEMPT_VALID_PROPOSAL_RATE": first_valid / len(rows) if rows else 0,
        "PROPOSAL_INTERNAL_INCONSISTENCY_RATE": inconsistent / valid_proposal if valid_proposal else 0,
        "DOWNSTREAM_INFORMATION_LOSS": downstream,
        "RETRY_TRIGGERED": retry_trig,
        "PROPOSAL_DISAGREEMENT_RATE": dual_disagree / dual_total if dual_total else None,
        "PROPOSAL_DISAGREEMENT_PAIRS": dual_total,
        "MP1_FORENSIC": mp1,
    }


def run() -> int:
    load_env_silent()
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("NOT_EXECUTED_NO_CREDENTIAL")
        SUMMARY_JSON.write_text(json.dumps({"status": "NOT_EXECUTED_NO_CREDENTIAL"}, indent=2))
        return 0

    if os.environ.get("PKE_I129_MP1_ONLY") == "1":
        cases = [c for c in I129_CORPUS if c.utterance.casefold().startswith("medi a temperatura e deu 95")]
    else:
        cases = list(I129_CORPUS)

    limit = int(os.environ.get("PKE_I129_LIMIT", "0"))
    if limit > 0:
        cases = cases[:limit]

    dual = os.environ.get("PKE_I129_DUAL", "0") == "1"
    dual_cases = {c.id for c in DUAL_SAMPLE_CASES}

    spec = next(c for c in all_candidates() if c.candidate_id == "baseline_deepseek_chat")
    freeze = {
        "experiment_id": EXPERIMENT_ID,
        "prompt_version": PROMPT_VERSION_V4,
        "model": spec.model,
        "schema": STORAGE_SCHEMA_VERSION,
        "core_version": 65,
        "corpus_size": len(cases),
        "dual_sample": dual,
        "git_commit": _git_commit(),
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    FREEZE_JSON.write_text(json.dumps(freeze, indent=2))

    provider = build_provider(spec)
    interpreter = DeepSeekInterpreter(
        provider, OntologyRegistry.with_core_seeds(), prompt_version=PROMPT_VERSION_V4
    )
    done = _done_keys() if os.environ.get("PKE_I129_RESUME", "1") != "0" else set()

    samples = ("A", "B") if dual else ("A",)
    total = sum(_reps(c) * len(samples) for c in cases)
    completed = 0
    t_start = time.perf_counter()

    for ci, case in enumerate(cases, 1):
        reps = _reps(case)
        do_dual = dual and case.id in dual_cases
        sample_ids = ("A", "B") if do_dual else ("A",)
        for sample_id in sample_ids:
            for run_no in range(1, reps + 1):
                if (case.id, run_no, sample_id) in done:
                    continue
                completed += 1
                elapsed = time.perf_counter() - t_start
                eta = (total - completed) * (elapsed / completed) if completed else 0
                print(
                    f"[{EXPERIMENT_ID}] {ci}/{len(cases)} run {run_no}/{reps} "
                    f"sample={sample_id} | {completed}/{total} | ETA {eta:.0f}s"
                )
                row = run_one(interpreter, case, run_no=run_no, sample_id=sample_id)
                with CHECKPOINT.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f"  -> {case.id} {row['primary_failure']} stage={row.get('first_fault_stage')}")

    rows = [
        json.loads(line)
        for line in CHECKPOINT.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("experiment_id") == EXPERIMENT_ID
    ]
    historical = analyze_artifacts()
    agg = aggregate(rows)

    summary = {
        **freeze,
        **agg,
        "historical_analysis": historical,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md = [
        "# I12.9 Model Variance Strategy",
        "",
        f"- Valid proposal rate: {agg['VALID_SEMANTIC_PROPOSAL_RATE']:.1%}",
        f"- Downstream loss: {agg['DOWNSTREAM_INFORMATION_LOSS']}",
        f"- Primary failures: {agg['PRIMARY_FAILURE']}",
        "",
        "## MP1 forensic (live)",
    ]
    for r in [x for x in rows if x.get("mp1_subclass")][:15]:
        md.append(
            f"- run {r['run']}: {r['mp1_subclass']} | prop_valid={bool(r.get('proposal_dump'))} "
            f"| event_ev={r.get('event_evidence_on_proposal')} | stage={r.get('first_fault_stage')}"
        )
    SUMMARY_MD.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
