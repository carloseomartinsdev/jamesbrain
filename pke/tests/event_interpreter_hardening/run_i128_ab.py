"""I12.8 A/B live evaluation: prompt v4 (control) vs v5-event (candidate).

Usage:
  .\\.venv\\Scripts\\python.exe -m tests.event_interpreter_hardening.run_i128_ab

Env:
  DEEPSEEK_API_KEY required
  PKE_I128_LIMIT=0 (>0 truncates cases)
  PKE_I128_RESUME=1 (default)
  PKE_I128_VARIANTS=v4,v5-event (default both)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from collections import defaultdict
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
from pke.interpretation.prompts import PROMPT_VERSION_V4, PROMPT_VERSION_V5_EVENT
from pke.interpretation.semantic.envelope_dispatch import ProviderRoute, dispatch_provider_payload
from pke.interpretation.semantic.event_preservation import (
    event_false_canonicalization,
    event_semantically_preserved,
)
from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.semantic.multi_primitive_evidence import (
    has_explicit_occurrence_evidence,
    has_measurement_evidence,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION

from tests.engine_v1_baseline.corpus import EngineCase
from tests.engine_v1_live_characterization.scoring import RunScore, classify_case_variance
from tests.event_interpreter_hardening.corpus import I128_CORPUS, mp_label
from tests.event_interpreter_hardening.scoring import (
    VariantAggregate,
    accumulate_raw,
    raw_has_event,
)
from tests.model_provider_evaluation.candidates import all_candidates, build_provider
from tests.model_provider_evaluation.dual_scoring import score_post_engine, score_raw_from_proposal

EXPERIMENT_ID = os.environ.get("PKE_I128_EXPERIMENT", "I12.8")
ROOT = _ROOT
ARTIFACT_DIR = ROOT / "docs" / "reports" / "i128_artifacts"
CHECKPOINT = ARTIFACT_DIR / "checkpoint.jsonl"
FREEZE_JSON = ARTIFACT_DIR / "FREEZE.json"
SUMMARY_JSON = ROOT / "docs" / "reports" / "I12.8-TARGETED-EVENT-INTERPRETER-HARDENING.json"
SUMMARY_MD = ROOT / "docs" / "reports" / "I12.8-TARGETED-EVENT-INTERPRETER-HARDENING.md"
FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = datetime(2026, 9, 3, 16, 0, tzinfo=FORTALEZA)

VARIANTS: dict[str, str] = {
    "v4": PROMPT_VERSION_V4,
    "v5-event": PROMPT_VERSION_V5_EVENT,
}


def load_env_silent() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def corpus_fingerprint(cases: list[EngineCase]) -> str:
    blob = "\n".join(f"{c.id}\t{c.utterance}\t{c.category}" for c in cases)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _git_commit() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return None


def _reps_for(case: EngineCase) -> int:
    return 5 if mp_label(case) else 3


def _ctx() -> InterpretationContext:
    return InterpretationContext(
        user=UserContext(user_id="i128-ab", timezone="America/Fortaleza", now=NOW)
    )


def _try_parse_proposal(raw: str | None) -> SemanticProposal | None:
    if not raw:
        return None
    try:
        dispatched = dispatch_provider_payload(raw)
        if dispatched.route is ProviderRoute.INVALID or dispatched.payload is None:
            return None
        if dispatched.route is ProviderRoute.V2_CANONICAL:
            return None
        env = WireSemanticEnvelope.model_validate(dispatched.payload)
        if env.ir_kind == "semantic_query":
            return None
        return env.parsed_proposal()
    except Exception:  # noqa: BLE001
        return None


def _completed_keys() -> set[tuple[str, str, str, int]]:
    if not CHECKPOINT.is_file():
        return set()
    done: set[tuple[str, str, str, int]] = set()
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("experiment_id") == EXPERIMENT_ID:
            done.add(
                (
                    row["prompt_variant"],
                    row["case_id"],
                    row.get("utterance", ""),
                    int(row["run"]),
                )
            )
    return done


def write_freeze(cases: list[EngineCase], spec_model: str, variants: list[str]) -> dict:
    freeze = {
        "experiment_id": EXPERIMENT_ID,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "control_prompt": PROMPT_VERSION_V4,
        "candidate_prompt": PROMPT_VERSION_V5_EVENT,
        "prompt_variants": variants,
        "provider": "deepseek",
        "model": spec_model,
        "retry_policy": "Interpreter RetryPolicy unchanged (I12.2)",
        "semantic_proposal": "unchanged",
        "wire": "unchanged",
        "schema": STORAGE_SCHEMA_VERSION,
        "core_version": 65,
        "corpus_fingerprint": corpus_fingerprint(cases),
        "corpus_size": len(cases),
        "logical_requests": sum(_reps_for(c) for c in cases) * len(variants),
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    FREEZE_JSON.write_text(json.dumps(freeze, indent=2), encoding="utf-8")
    return freeze


def _aggregate(rows: list[dict], variant: str) -> VariantAggregate:
    agg = VariantAggregate(prompt_variant=variant)
    by_case: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("prompt_variant") != variant:
            continue
        case = EngineCase(
            id=r["case_id"],
            utterance=r["utterance"],
            category=r["category"],
            expected_intent=r.get("expected_intent"),
            expected_primitive=r.get("expected_primitive"),
        )
        proposal = None
        if r.get("proposal_dump"):
            try:
                proposal = SemanticProposal.model_validate(r["proposal_dump"])
            except Exception:
                proposal = None
        accumulate_raw(agg.metrics, case, proposal, raw_score=r.get("raw_score"))

        post = r.get("post_score") or {}
        sev = post.get("severity")
        if sev == "S3":
            agg.post_s3 += 1
        elif sev == "S4":
            agg.post_s4 += 1

        if r.get("PROPOSAL_EVENT_PRESENT") and not r.get("FINAL_EVENT_SEMANTIC"):
            agg.raw_event_present_post_event_lost += 1
        if r.get("FALSE_CANONICALIZATION"):
            agg.partial_event_false_canonicalization += 1

        mp = r.get("mp_anchor")
        if mp:
            agg.mp_runs[mp] = agg.mp_runs.get(mp, 0) + 1
            if r.get("PROPOSAL_EVENT_PRESENT"):
                agg.mp_event_hits[mp] = agg.mp_event_hits.get(mp, 0) + 1

        by_case[r["case_id"]].append(r)

    for case_rows in by_case.values():
        scores = [RunScore(**r["post_score"]) for r in case_rows if r.get("post_score")]
        if not scores:
            continue
        v = classify_case_variance(scores)
        if v == "STABLE_CORRECT":
            agg.stable_correct += 1
        elif v == "STABLE_SAFE_ABSTENTION":
            agg.stable_safe_abstention += 1
        elif v == "UNSTABLE_BUT_SAFE":
            agg.unstable_but_safe += 1
        else:
            agg.unsafe_variance += 1

    return agg


def evaluate_acceptance(v4: VariantAggregate, v5: VariantAggregate) -> dict:
    mp1_v4 = v4.mp_event_hits.get("MP1", 0)
    mp1_v5 = v5.mp_event_hits.get("MP1", 0)
    mp1_runs = v5.mp_runs.get("MP1", 5)
    mp5_false_v5 = v5.mp_event_hits.get("MP5", 0)

    recall_v4 = v4.metrics.explicit_event_recall or 0.0
    recall_v5 = v5.metrics.explicit_event_recall or 0.0
    recall_delta = recall_v5 - recall_v4

    gates = {
        "POST_S4_ZERO": v5.post_s4 == 0 and v4.post_s4 == 0,
        "FALSE_EXTRA_EVENT_ZERO_CANDIDATE": v5.metrics.false_extra_event == 0,
        "NO_FALSE_EXTRA_REGRESSION": v5.metrics.false_extra_event <= v4.metrics.false_extra_event,
        "RECALL_MATERIAL_IMPROVEMENT": recall_delta >= 0.08 or recall_v5 >= recall_v4 + 0.05,
        "MP1_TARGET": mp1_v5 >= 4,
        "MP5_MEASUREMENT_ONLY": mp5_false_v5 == 0,
        "POST_EVENT_LOST_ZERO": v5.raw_event_present_post_event_lost == 0,
        "FALSE_CANON_ZERO": v5.partial_event_false_canonicalization == 0,
    }
    accepted = all(gates.values())
    return {
        "gates": gates,
        "CANDIDATE_STATUS": "ACCEPTED" if accepted else "REJECTED",
        "MP1_v4": mp1_v4,
        "MP1_v5": mp1_v5,
        "MP1_runs": mp1_runs,
        "recall_v4": recall_v4,
        "recall_v5": recall_v5,
        "recall_delta": recall_delta,
    }


def run() -> int:
    load_env_silent()
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("NOT_EXECUTED_NO_CREDENTIAL")
        SUMMARY_JSON.write_text(
            json.dumps({"status": "NOT_EXECUTED_NO_CREDENTIAL"}, indent=2),
            encoding="utf-8",
        )
        return 0

    cases = list(I128_CORPUS)
    limit = int(os.environ.get("PKE_I128_LIMIT", "0"))
    if limit > 0:
        cases = cases[:limit]

    variant_names = os.environ.get("PKE_I128_VARIANTS", "v4,v5-event").split(",")
    variant_names = [v.strip() for v in variant_names if v.strip() in VARIANTS]

    spec = next(c for c in all_candidates() if c.candidate_id == "baseline_deepseek_chat")
    freeze = write_freeze(cases, spec.model, variant_names)
    done = _completed_keys() if os.environ.get("PKE_I128_RESUME", "1") != "0" else set()

    total_logical = sum(_reps_for(c) for c in cases) * len(variant_names)
    completed = len(done)
    t_start = time.perf_counter()
    provider_calls = 0

    for ci, case in enumerate(cases, start=1):
        reps = _reps_for(case)
        mp = mp_label(case)
        for variant_name in variant_names:
            prompt_version = VARIANTS[variant_name]
            provider = build_provider(spec)
            interpreter = DeepSeekInterpreter(
                provider,
                OntologyRegistry.with_core_seeds(),
                prompt_version=prompt_version,
            )
            for run_no in range(1, reps + 1):
                key = (variant_name, case.id, case.utterance, run_no)
                if key in done:
                    continue
                logical_done = completed + 1
                elapsed = time.perf_counter() - t_start
                rate = logical_done / elapsed if elapsed > 0 else 0
                remaining = total_logical - logical_done
                eta_s = remaining / rate if rate > 0 else 0
                print(
                    f"[{EXPERIMENT_ID}] {variant_name} case {ci}/{len(cases)} "
                    f"run {run_no}/{reps} | logical {logical_done}/{total_logical} | "
                    f"ETA {eta_s:.0f}s"
                )

                logical_id = str(uuid.uuid4())
                t0 = time.perf_counter()
                raw_content = None
                proposal = None
                ir = None
                error = None
                attempts = 1
                try:
                    ir = interpreter.interpret(case.utterance, _ctx())
                    attempts = interpreter.last_provider_attempts or 1
                    provider_calls += attempts
                    raw_content = interpreter.last_raw_content
                    proposal = _try_parse_proposal(raw_content)
                except InterpretationError as exc:
                    error = str(exc)
                    provider_calls += interpreter.last_provider_attempts or 1

                latency_ms = (time.perf_counter() - t0) * 1000
                prop_e = raw_has_event(proposal)
                prop_m = has_measurement_evidence(proposal) if proposal else False

                outcome = proposal_to_canonical_ir(proposal) if proposal else None
                final_e_sem = event_semantically_preserved(outcome) if outcome else False
                final_m = bool(outcome and outcome.ir and outcome.ir.measurement is not None)
                false_canon = event_false_canonicalization(outcome) if outcome else False

                raw_score = None
                post_score = None
                if proposal:
                    raw_sc = score_raw_from_proposal(case, proposal, run=run_no)
                    raw_score = raw_sc.__dict__
                if ir is not None:
                    post_sc = score_post_engine(case, run=run_no, ir=ir)
                    post_score = post_sc.__dict__
                elif error:
                    post_sc = score_post_engine(case, run=run_no, exc=InterpretationError(error))
                    post_score = post_sc.__dict__

                row = {
                    "experiment_id": EXPERIMENT_ID,
                    "prompt_variant": variant_name,
                    "prompt_version": prompt_version,
                    "case_id": case.id,
                    "mp_anchor": mp,
                    "run": run_no,
                    "utterance": case.utterance,
                    "category": case.category,
                    "expected_intent": case.expected_intent,
                    "expected_primitive": case.expected_primitive,
                    "logical_request_id": logical_id,
                    "attempts": attempts,
                    "latency_ms": latency_ms,
                    "raw_content": raw_content,
                    "proposal_dump": proposal.model_dump() if proposal else None,
                    "PROPOSAL_EVENT_PRESENT": prop_e,
                    "PROPOSAL_MEASUREMENT_PRESENT": prop_m,
                    "FINAL_EVENT_SEMANTIC": final_e_sem,
                    "FINAL_MEASUREMENT_PRESENT": final_m,
                    "FALSE_CANONICALIZATION": false_canon,
                    "raw_score": raw_score,
                    "post_score": post_score,
                    "error": error,
                }
                with CHECKPOINT.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                completed += 1
                print(
                    f"  -> {variant_name} {case.id} mp={mp} prop_E={prop_e} prop_M={prop_m} err={error is not None}"
                )

    rows = []
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("experiment_id") == EXPERIMENT_ID:
                rows.append(r)

    aggregates = {v: _aggregate(rows, v) for v in variant_names}
    v4_agg = aggregates.get("v4", VariantAggregate("v4"))
    v5_agg = aggregates.get("v5-event", VariantAggregate("v5-event"))
    acceptance = evaluate_acceptance(v4_agg, v5_agg) if "v4" in aggregates and "v5-event" in aggregates else {}

    from pke.interpretation import prompts_v4, prompts_v5

    prompt_sizes = {
        "PROMPT_V4_CHARS": len(prompts_v4.SYSTEM_PROMPT),
        "PROMPT_CANDIDATE_CHARS": len(prompts_v5.SYSTEM_PROMPT),
        "DELTA_CHARS": len(prompts_v5.SYSTEM_PROMPT) - len(prompts_v4.SYSTEM_PROMPT),
        "DELTA_PERCENT": 100.0
        * (len(prompts_v5.SYSTEM_PROMPT) - len(prompts_v4.SYSTEM_PROMPT))
        / len(prompts_v4.SYSTEM_PROMPT),
    }

    summary = {
        **freeze,
        **prompt_sizes,
        "TOTAL_CASES": len(cases),
        "TOTAL_RUNS": len(rows),
        "PROVIDER_CALLS": provider_calls,
        "variants": {k: v.to_dict() for k, v in aggregates.items()},
        "acceptance": acceptance,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md_lines = [
        "# I12.8 Targeted Event Interpreter Hardening",
        "",
        f"- Experiment: {EXPERIMENT_ID}",
        f"- Candidate status: {acceptance.get('CANDIDATE_STATUS', 'INCONCLUSIVE')}",
        "",
        "## Prompt sizes",
        f"- v4: {prompt_sizes['PROMPT_V4_CHARS']} chars",
        f"- v5-event: {prompt_sizes['PROMPT_CANDIDATE_CHARS']} chars",
        f"- delta: {prompt_sizes['DELTA_CHARS']} ({prompt_sizes['DELTA_PERCENT']:.2f}%)",
        "",
        "## Comparison",
        "| Metric | v4 | v5-event |",
        "|---|---:|---:|",
    ]
    if "v4" in aggregates and "v5-event" in aggregates:
        m4 = aggregates["v4"].metrics
        m5 = aggregates["v5-event"].metrics
        md_lines.extend(
            [
                f"| Raw Event recall | {m4.recall} | {m5.recall} |",
                f"| Raw missing Event | {m4.missing_event} | {m5.missing_event} |",
                f"| False extra Event | {m4.false_extra_event} | {m5.false_extra_event} |",
                f"| E+M complete | {m4.em_complete}/{m4.em_expected} | {m5.em_complete}/{m5.em_expected} |",
                f"| POST S4 | {aggregates['v4'].post_s4} | {aggregates['v5-event'].post_s4} |",
            ]
        )
    SUMMARY_MD.write_text("\n".join(md_lines), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
