"""I12.11 live model capability re-evaluation (prompt v4, Engine frozen).

Usage:
  .\\.venv\\Scripts\\python.exe -m tests.model_capability_reevaluation.run_i1211

Env:
  DEEPSEEK_API_KEY required for DeepSeek candidates
  OPENAI_API_KEY optional
  PKE_I1211_CANDIDATES=baseline_deepseek_chat,deepseek_reasoner
  PKE_I1211_LIMIT=0
  PKE_I1211_RESUME=1
"""

from __future__ import annotations

import hashlib
import json
import math
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
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.semantic.envelope_dispatch import ProviderRoute, dispatch_provider_payload
from pke.interpretation.semantic.event_preservation import event_false_canonicalization, event_semantically_preserved
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.semantic.multi_primitive_evidence import (
    has_explicit_occurrence_evidence,
    has_measurement_evidence,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.ontology import OntologyRegistry

from tests.engine_v1_baseline.corpus import EngineCase
from tests.engine_v1_live_characterization.scoring import classify_case_variance
from tests.event_interpreter_hardening.corpus import mp_label
from tests.model_capability_reevaluation.corpus import I1211_CORPUS
from tests.model_capability_reevaluation.freeze import default_freeze, frozen_thresholds
from tests.model_capability_reevaluation.scoring import (
    execution_ready_flag,
    invented_required_information,
    primitive_family_status,
    safe_handled,
    score_completeness,
    useful_capture,
)
from tests.model_provider_evaluation.candidates import all_candidates, build_provider
from tests.model_provider_evaluation.dual_scoring import score_post_engine

EXPERIMENT_ID = os.environ.get("PKE_I1211_EXPERIMENT", "I12.11")
ROOT = _ROOT
ARTIFACT_DIR = ROOT / "docs" / "reports" / "i1211_artifacts"
CHECKPOINT = ARTIFACT_DIR / "checkpoint.jsonl"
FREEZE_JSON = ARTIFACT_DIR / "FREEZE.json"
SUMMARY_JSON = ROOT / "docs" / "reports" / "I12.11-MODEL-CAPABILITY-SEMANTIC-COMPLETENESS.json"
SUMMARY_MD = ROOT / "docs" / "reports" / "I12.11-MODEL-CAPABILITY-SEMANTIC-COMPLETENESS.md"
NOW = datetime(2026, 9, 3, 20, 0, tzinfo=ZoneInfo("America/Fortaleza"))


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


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return None


def corpus_fingerprint(cases: list[EngineCase]) -> str:
    blob = "\n".join(f"{c.id}\t{c.utterance}\t{c.expected_primitive}" for c in cases)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _reps(case: EngineCase) -> int:
    label = mp_label(case)
    if label == "MP1":
        return 10
    if label:
        return 5
    return 3


def _ctx() -> InterpretationContext:
    return InterpretationContext(
        user=UserContext(user_id="i1211", timezone="America/Fortaleza", now=NOW)
    )


def _parse(raw: str | None) -> SemanticProposal | None:
    if not raw:
        return None
    try:
        dispatched = dispatch_provider_payload(raw)
        if dispatched.route is ProviderRoute.INVALID or not dispatched.payload:
            return None
        if dispatched.route is ProviderRoute.V2_CANONICAL:
            return None
        ir = dispatched.payload.get("ir")
        if dispatched.payload.get("ir_kind") == "semantic_query":
            return None
        if ir is not None:
            return SemanticProposal.model_validate(ir)
        env = WireSemanticEnvelope.model_validate(dispatched.payload)
        return env.parsed_proposal()
    except Exception:
        return None


def _done() -> set[tuple[str, str, int]]:
    if not CHECKPOINT.is_file():
        return set()
    out: set[tuple[str, str, int]] = set()
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("experiment_id") == EXPERIMENT_ID:
            out.add((r["candidate_id"], r["case_id"], int(r["run"])))
    return out


def _pctile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    k = min(len(ys) - 1, max(0, int(math.ceil(p / 100.0 * len(ys)) - 1)))
    return ys[k]


def selectable_candidates() -> list:
    names = os.environ.get("PKE_I1211_CANDIDATES", "").strip()
    specs = all_candidates()
    if names:
        wanted = {x.strip() for x in names.split(",") if x.strip()}
        specs = [s for s in specs if s.candidate_id in wanted]
    return [s for s in specs if s.credential_present()]


def write_freeze(cases: list[EngineCase], specs: list) -> dict:
    fr = default_freeze()
    freeze = {
        **{k: getattr(fr, k) for k in fr.__dataclass_fields__},
        "started_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "corpus_fingerprint": corpus_fingerprint(cases),
        "expected_label_hash": hashlib.sha256(
            "\n".join(f"{c.id}:{c.expected_primitive}:{c.expected_intent}" for c in cases).encode()
        ).hexdigest()[:16],
        "corpus_size": len(cases),
        "candidates": [
            {
                "candidate_id": s.candidate_id,
                "provider": s.provider,
                "model": s.model,
                "role": s.role,
            }
            for s in specs
        ],
        "thresholds": frozen_thresholds().__dict__,
        "logical_requests": sum(_reps(c) for c in cases) * len(specs),
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    FREEZE_JSON.write_text(json.dumps(freeze, indent=2), encoding="utf-8")
    return freeze


def aggregate(rows: list[dict], cases: list[EngineCase]) -> dict:
    by_id = {c.id: c for c in cases}
    n = len(rows) or 1
    capture = sum(1 for r in rows if r.get("useful_capture"))
    safe = sum(1 for r in rows if r.get("safe_handled"))
    valid = sum(1 for r in rows if r.get("proposal_valid"))
    useful_prop = sum(1 for r in rows if r.get("semantically_useful"))
    exec_ready = sum(1 for r in rows if r.get("execution_ready"))
    zero = sum(1 for r in rows if r.get("zero_materializable"))
    first_valid = sum(1 for r in rows if r.get("proposal_valid") and int(r.get("attempts") or 1) == 1)
    retry_rec = sum(1 for r in rows if r.get("retry_recovered"))
    retry_ex = sum(1 for r in rows if r.get("retry_exhausted"))
    lat = [float(r["latency_ms"]) for r in rows if r.get("latency_ms") is not None]
    prec_vals = [r["completeness_precision"] for r in rows if r.get("completeness_precision") is not None]
    rec_vals = [r["completeness_recall"] for r in rows if r.get("completeness_recall") is not None]
    reasons = Counter()
    for r in rows:
        for reason in r.get("incompleteness_reasons") or []:
            reasons[reason] += 1
    fam = defaultdict(Counter)
    for r in rows:
        cat = r.get("family") or r.get("category")
        fam[cat][r.get("family_status") or "n/a"] += 1
    post_s3 = sum(1 for r in rows if (r.get("post_score") or {}).get("severity") == "S3")
    post_s4 = sum(1 for r in rows if (r.get("post_score") or {}).get("severity") == "S4")
    mp1 = [r for r in rows if r.get("mp_anchor") == "MP1"]
    mp_stats = {}
    for label in ("MP1", "MP2", "MP3", "MP4", "MP5"):
        subset = [r for r in rows if r.get("mp_anchor") == label]
        if not subset:
            continue
        if label == "MP5":
            mp_stats[label] = {
                "runs": len(subset),
                "false_event": sum(1 for r in subset if r.get("event_present")),
                "capture": sum(1 for r in subset if r.get("useful_capture")) / len(subset),
            }
        else:
            mp_stats[label] = {
                "runs": len(subset),
                "capture": sum(1 for r in subset if r.get("useful_capture")) / len(subset),
                "event_present": sum(1 for r in subset if r.get("event_present")),
                "measurement_present": sum(1 for r in subset if r.get("measurement_present")),
            }

    by_case: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_case[r["case_id"]].append(r)
    variance = Counter()
    capture_stab = Counter()
    from tests.engine_v1_live_characterization.scoring import RunScore

    for cid, cro in by_case.items():
        scores = []
        for r in cro:
            ps = r.get("post_score")
            if ps:
                try:
                    scores.append(RunScore(**{k: ps[k] for k in RunScore.__dataclass_fields__ if k in ps}))
                except Exception:
                    continue
        if scores:
            variance[classify_case_variance(scores)] += 1
        caps = [bool(r.get("useful_capture")) for r in cro]
        if all(caps):
            capture_stab["ALL_RUNS_CAPTURE"] += 1
        elif any(caps):
            capture_stab["SOME_RUNS_CAPTURE"] += 1
        else:
            capture_stab["NO_RUN_CAPTURE"] += 1

    return {
        "TOTAL_CASES": len({r["case_id"] for r in rows}),
        "TOTAL_RUNS": len(rows),
        "SAFE_HANDLED_INTERACTION_RATE": safe / n,
        "USEFUL_KNOWLEDGE_CAPTURE_RATE": capture / n,
        "VALID_SEMANTIC_PROPOSAL_RATE": valid / n,
        "VALID_AND_SEMANTICALLY_USEFUL_PROPOSAL_RATE": useful_prop / n,
        "EXECUTION_READY_PROPOSAL_RATE": exec_ready / n,
        "VALID_ZERO_MATERIALIZABLE_RATE": zero / n,
        "SEMANTIC_COMPLETENESS_PRECISION": (sum(prec_vals) / len(prec_vals)) if prec_vals else None,
        "SEMANTIC_COMPLETENESS_RECALL": (sum(rec_vals) / len(rec_vals)) if rec_vals else None,
        "FIRST_ATTEMPT_VALID_PROPOSAL_RATE": first_valid / n,
        "RETRY_RECOVERED": retry_rec,
        "RETRY_EXHAUSTED": retry_ex,
        "POST_S3": post_s3,
        "POST_S4": post_s4,
        "FALSE_CORRECTION_ACCEPTED": sum(1 for r in rows if r.get("false_correction_accepted")),
        "PARTIAL_EVENT_FALSE_CANONICALIZATION": sum(1 for r in rows if r.get("false_canonicalization")),
        "MISSING_INFORMATION_INVENTED": sum(1 for r in rows if r.get("invented")),
        "RAW_EVENT_PRESENT_POST_EVENT_LOST": sum(
            1 for r in rows if r.get("event_present") and not r.get("event_preserved")
        ),
        "DOMINANT_EXECUTION_INCOMPLETENESS_REASON": (reasons.most_common(1)[0][0] if reasons else None),
        "INCOMPLETENESS_REASONS": dict(reasons),
        "FAMILY": {k: dict(v) for k, v in fam.items()},
        "MP": mp_stats,
        "MP1_RUNS": len(mp1),
        "MP1_EVENT_PRESENT": sum(1 for r in mp1 if r.get("event_present")),
        "MP1_MEASUREMENT_PRESENT": sum(1 for r in mp1 if r.get("measurement_present")),
        "MP1_CORRECT_SUBJECT": sum(1 for r in mp1 if r.get("mp1_subject") == "correct"),
        "MP1_MISSING_SUBJECT": sum(1 for r in mp1 if r.get("mp1_subject") == "missing"),
        "MP1_WRONG_SUBJECT": sum(1 for r in mp1 if r.get("mp1_subject") == "wrong"),
        "MP1_SAFE_HANDLING_RATE": (sum(1 for r in mp1 if r.get("safe_handled")) / len(mp1)) if mp1 else None,
        "MP1_USEFUL_CAPTURE_RATE": (sum(1 for r in mp1 if r.get("useful_capture")) / len(mp1)) if mp1 else None,
        "STABLE_CORRECT": variance.get("STABLE_CORRECT", 0),
        "STABLE_SAFE_ABSTENTION": variance.get("STABLE_SAFE_ABSTENTION", 0),
        "UNSTABLE_BUT_SAFE": variance.get("UNSTABLE_BUT_SAFE", 0),
        "UNSAFE_VARIANCE": variance.get("UNSAFE_VARIANCE", 0),
        "ALL_RUNS_CAPTURE": capture_stab.get("ALL_RUNS_CAPTURE", 0),
        "SOME_RUNS_CAPTURE": capture_stab.get("SOME_RUNS_CAPTURE", 0),
        "NO_RUN_CAPTURE": capture_stab.get("NO_RUN_CAPTURE", 0),
        "p50": _pctile(lat, 50),
        "p95": _pctile(lat, 95),
        "total_tokens": sum(int(r.get("total_tokens") or 0) for r in rows),
        "_n": n,
    }


def verdict_for(baseline: dict | None, cand: dict, thresholds) -> str:
    if cand.get("POST_S4", 0) != 0:
        return "REJECTED_SAFETY"
    if cand.get("FALSE_CORRECTION_ACCEPTED", 0) != 0:
        return "REJECTED_SAFETY"
    if cand.get("PARTIAL_EVENT_FALSE_CANONICALIZATION", 0) != 0:
        return "REJECTED_SAFETY"
    if cand.get("MISSING_INFORMATION_INVENTED", 0) != 0:
        return "REJECTED_SAFETY"
    if cand.get("RAW_EVENT_PRESENT_POST_EVENT_LOST", 0) != 0:
        return "REJECTED_SAFETY"
    if baseline is None:
        return "VIABLE_TRADEOFF"
    delta = cand["USEFUL_KNOWLEDGE_CAPTURE_RATE"] - baseline["USEFUL_KNOWLEDGE_CAPTURE_RATE"]
    if delta >= thresholds.useful_capture_delta_min:
        return "VIABLE_WINNER"
    return "REJECTED_NO_MATERIAL_GAIN"


def run_one(interpreter, case: EngineCase, *, candidate_id: str, run_no: int) -> dict:
    t0 = time.perf_counter()
    error = None
    ir = None
    attempts = 1
    retry_recovered = False
    retry_exhausted = False
    try:
        ir = interpreter.interpret(case.utterance, _ctx())
        attempts = interpreter.last_provider_attempts or 1
        retry_recovered = attempts > 1
    except InterpretationError as exc:
        error = str(exc)
        attempts = interpreter.last_provider_attempts or 1
        retry_exhausted = attempts > 1 and error is not None
    latency_ms = (time.perf_counter() - t0) * 1000
    raw = interpreter.last_raw_content
    proposal = _parse(raw)
    readiness = assess_execution_readiness(resolve_proposal(proposal)) if proposal else None
    outcome = proposal_to_canonical_ir(proposal) if proposal else None
    invented = invented_required_information(case, proposal)
    comp = score_completeness(case, proposal)
    post = None
    if ir is not None:
        post = score_post_engine(case, run=run_no, ir=ir).__dict__
    elif error:
        post = score_post_engine(case, run=run_no, exc=InterpretationError(error)).__dict__
    post_s4 = (post or {}).get("severity") == "S4"
    false_corr_acc = bool(post_s4 and case.expected_intent != "correct" and "correct" in str((post or {}).get("observed_intent")))
    capture = useful_capture(case, ir=ir, outcome=outcome, error=error)
    handled = safe_handled(
        capture=capture,
        error=error,
        post_s4=post_s4,
        invented=bool(invented),
        false_correction_accepted=false_corr_acc,
    )
    event_present = has_explicit_occurrence_evidence(proposal) if proposal else False
    meas_present = has_measurement_evidence(proposal) if proposal else False
    event_preserved = event_semantically_preserved(outcome) if outcome else False
    false_canon = event_false_canonicalization(outcome) if outcome else False
    mp = mp_label(case)
    mp1_subject = None
    if mp == "MP1":
        subj = proposal.subject if proposal else None
        if subj is None or not (subj.text or "").strip():
            mp1_subject = "missing"
        elif "temperatura" in subj.text.casefold():
            mp1_subject = "correct"
        else:
            mp1_subject = "wrong"
    tokens = None
    meta = getattr(interpreter, "last_metadata", None)
    if meta is not None:
        tokens = getattr(meta, "total_tokens", None)

    return {
        "experiment_id": EXPERIMENT_ID,
        "candidate_id": candidate_id,
        "prompt_version": PROMPT_VERSION_V4,
        "case_id": case.id,
        "run": run_no,
        "mp_anchor": mp,
        "utterance": case.utterance,
        "category": case.category,
        "family": case.category,
        "expected_primitive": case.expected_primitive,
        "logical_request_id": str(uuid.uuid4()),
        "attempts": attempts,
        "latency_ms": latency_ms,
        "total_tokens": tokens,
        "raw_content": raw,
        "proposal_dump": proposal.model_dump() if proposal else None,
        "error": error,
        "proposal_valid": proposal is not None,
        "execution_outcome": readiness.outcome.value if readiness else None,
        "execution_ready": execution_ready_flag(readiness) if readiness else False,
        "zero_materializable": bool(readiness.zero_materializable_valid) if readiness else False,
        "incompleteness_reasons": list(readiness.reasons) if readiness else [],
        "materializable_count": readiness.materializable_count if readiness else 0,
        "semantically_useful": bool(readiness and readiness.materializable_count > 0),
        "useful_capture": capture,
        "safe_handled": handled,
        "invented": bool(invented),
        "invented_flags": invented,
        "completeness_precision": comp.precision,
        "completeness_recall": comp.recall,
        "completeness_missing": list(comp.missing),
        "family_status": primitive_family_status(case, proposal, readiness) if readiness else "omitted",
        "event_present": event_present,
        "measurement_present": meas_present,
        "event_preserved": event_preserved,
        "false_canonicalization": false_canon,
        "false_correction_accepted": false_corr_acc,
        "mp1_subject": mp1_subject,
        "retry_recovered": retry_recovered,
        "retry_exhausted": retry_exhausted,
        "post_score": post,
        "outcome_ir": ir is not None,
        "failure_stage": outcome.failure_stage if outcome else None,
    }


def run() -> int:
    load_env_silent()
    print(f"[{EXPERIMENT_ID}] loading catalog…", flush=True)
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    cases = list(I1211_CORPUS)
    limit = int(os.environ.get("PKE_I1211_LIMIT", "0"))
    if limit > 0:
        cases = cases[:limit]
    specs = selectable_candidates()
    print(f"[{EXPERIMENT_ID}] candidates={[s.candidate_id for s in specs]} corpus={len(cases)}", flush=True)
    if not specs:
        print("MODEL_CAPABILITY_EVALUATION_NO_COMPARABLE_CANDIDATES")
        SUMMARY_JSON.write_text(
            json.dumps({"status": "MODEL_CAPABILITY_EVALUATION_NO_COMPARABLE_CANDIDATES"}, indent=2),
            encoding="utf-8",
        )
        return 0
    freeze = write_freeze(cases, specs)
    if len(specs) < 2:
        print("MODEL_CAPABILITY_EVALUATION_NO_COMPARABLE_CANDIDATES")
        SUMMARY_JSON.write_text(
            json.dumps({**freeze, "status": "MODEL_CAPABILITY_EVALUATION_NO_COMPARABLE_CANDIDATES"}, indent=2),
            encoding="utf-8",
        )
        return 0

    done = _done() if os.environ.get("PKE_I1211_RESUME", "1") != "0" else set()
    total = freeze["logical_requests"]
    completed = 0
    t_start = time.perf_counter()
    provider_calls = 0
    retries = 0

    for si, spec in enumerate(specs, 1):
        interpreter = DeepSeekInterpreter(
            build_provider(spec),
            OntologyRegistry.with_core_seeds(),
            prompt_version=PROMPT_VERSION_V4,
        )
        for ci, case in enumerate(cases, 1):
            reps = _reps(case)
            for run_no in range(1, reps + 1):
                if (spec.candidate_id, case.id, run_no) in done:
                    continue
                completed += 1
                elapsed = time.perf_counter() - t_start
                eta = (total - completed) * (elapsed / completed) if completed else 0
                print(
                    f"[{EXPERIMENT_ID}] model {si}/{len(specs)} | case {ci}/{len(cases)} | "
                    f"run {run_no}/{reps} | calls {provider_calls} | retries {retries} | "
                    f"elapsed {elapsed:.0f}s | ETA {eta:.0f}s",
                    flush=True,
                )
                row = run_one(interpreter, case, candidate_id=spec.candidate_id, run_no=run_no)
                provider_calls += int(row.get("attempts") or 1)
                if int(row.get("attempts") or 1) > 1:
                    retries += 1
                with CHECKPOINT.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(
                    f"  -> {spec.candidate_id} {case.id} capture={row['useful_capture']} "
                    f"{row.get('execution_outcome')}",
                    flush=True,
                )

    all_rows = [
        json.loads(l)
        for l in CHECKPOINT.read_text(encoding="utf-8").splitlines()
        if l.strip() and json.loads(l).get("experiment_id") == EXPERIMENT_ID
    ]
    thresholds = frozen_thresholds()
    per: dict[str, dict] = {}
    for spec in specs:
        subset = [r for r in all_rows if r.get("candidate_id") == spec.candidate_id]
        per[spec.candidate_id] = aggregate(subset, cases)
        per[spec.candidate_id]["role"] = spec.role
        per[spec.candidate_id]["model"] = spec.model
        per[spec.candidate_id]["provider"] = spec.provider

    baseline = per.get("baseline_deepseek_chat")
    statuses = {}
    for cid, metrics in per.items():
        if cid == "baseline_deepseek_chat":
            statuses[cid] = "VIABLE_TRADEOFF"
        else:
            statuses[cid] = verdict_for(baseline, metrics, thresholds)
        metrics["CANDIDATE_STATUS"] = statuses[cid]

    winners = [cid for cid, st in statuses.items() if st == "VIABLE_WINNER"]
    best = winners[0] if len(winners) == 1 else ("NONE" if not winners else winners[0])
    if best != "NONE" and best in per:
        # Prefer largest capture among winners
        best = max(winners, key=lambda c: per[c]["USEFUL_KNOWLEDGE_CAPTURE_RATE"])

    summary = {
        **freeze,
        "I12.6": "CLOSED",
        "candidates_evaluated": list(per.keys()),
        "per_candidate": per,
        "BEST_CANDIDATE": best if winners else "NONE",
        "CURRENT_BASELINE_REMAINS": not winners,
        "thresholds": thresholds.__dict__,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    md = ["# I12.11 Model Capability Re-evaluation", "", f"- BEST_CANDIDATE: {summary['BEST_CANDIDATE']}", ""]
    md.append("| Candidate | Safety | Useful capture | Exec-ready | p50 | Verdict |")
    md.append("|---|---|---:|---:|---:|---|")
    for cid, m in per.items():
        safe = "OK" if m.get("POST_S4", 0) == 0 and m.get("MISSING_INFORMATION_INVENTED", 0) == 0 else "FAIL"
        md.append(
            f"| {cid} | {safe} | {m['USEFUL_KNOWLEDGE_CAPTURE_RATE']:.3f} | "
            f"{m['EXECUTION_READY_PROPOSAL_RATE']:.3f} | {m.get('p50')} | {m['CANDIDATE_STATUS']} |"
        )
    SUMMARY_MD.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("BEST_CANDIDATE", "CURRENT_BASELINE_REMAINS", "candidates_evaluated")}, indent=2))
    print(json.dumps({cid: {"capture": m["USEFUL_KNOWLEDGE_CAPTURE_RATE"], "status": m["CANDIDATE_STATUS"], "mp1": m.get("MP1_USEFUL_CAPTURE_RATE")} for cid, m in per.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
