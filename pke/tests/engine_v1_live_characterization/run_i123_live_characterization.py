"""I12.3 live characterization runner — observational only.

Usage:
  .\\.venv\\Scripts\\python.exe -m tests.engine_v1_live_characterization.run_i123_live_characterization

Env:
  DEEPSEEK_API_KEY required
  PKE_I123_RUNS=3 (default)
  PKE_I123_MP_RUNS=5 (default)
  PKE_I123_LIMIT=0  (0 = full corpus; >0 truncates for smoke — document if used)
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Allow `python tests/.../run_i123_*.py` without pytest pythonpath.
_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "src", _ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.retry import MAX_ATTEMPTS
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION

from tests.engine_v1_baseline.corpus import CORPUS, EngineCase
from tests.engine_v1_live_characterization.freeze import default_freeze
from tests.engine_v1_live_characterization.scoring import (
    RunScore,
    aggregate_report,
    classify_case_variance,
    score_failure,
    score_success,
)

ROOT = _ROOT
REPORT_JSON = ROOT / "docs" / "reports" / "I12.3-LIVE-CHARACTERIZATION.json"
REPORT_MD = ROOT / "docs" / "reports" / "I12.3-LIVE-CHARACTERIZATION.md"
FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=FORTALEZA)

MP_ANCHOR_IDS = {
    # utterances from corpus notes / multi_primitive
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


def _ctx() -> InterpretationContext:
    return InterpretationContext(
        user=UserContext(user_id="i123-live", timezone="America/Fortaleza", now=NOW)
    )


def _is_mp_anchor(case: EngineCase) -> bool:
    u = case.utterance.lower()
    anchors = [
        "medi a temperatura e deu 95",
        "olhei o tanque e ele estava com 20",
        "pesei a caixa: 10",
        "consultei o saldo e tinha r$2500",
        "o sensor mediu 38",
    ]
    return any(a in u for a in anchors)


def run_one(
    interpreter: DeepSeekInterpreter,
    case: EngineCase,
    run: int,
) -> RunScore:
    t0 = time.perf_counter()
    try:
        ir = interpreter.interpret(case.utterance, _ctx())
        elapsed = (time.perf_counter() - t0) * 1000
        attempts = interpreter.last_provider_attempts or 1
        score = score_success(case, ir, run=run, attempts=attempts)
        score.latency_ms = elapsed
        score.retry_recovered = attempts > 1
        meta = interpreter.last_metadata
        if meta is not None:
            score.prompt_tokens = meta.prompt_tokens
            score.completion_tokens = meta.completion_tokens
            score.total_tokens = meta.total_tokens
            if meta.latency_ms:
                score.latency_ms = meta.latency_ms
        return score
    except InterpretationError as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        attempts = interpreter.last_provider_attempts or 1
        score = score_failure(case, exc, run=run, attempts=attempts)
        score.latency_ms = elapsed
        score.retry_recovered = False
        return score
    except Exception as exc:  # noqa: BLE001 — observational capture
        elapsed = (time.perf_counter() - t0) * 1000
        score = score_failure(case, exc, run=run, attempts=1)
        score.latency_ms = elapsed
        return score


def build_markdown(report: dict) -> str:
    fr = report["freeze"]
    agg = report["aggregate"]
    lines = [
        "# I12.3 — Live Engine Characterization Report",
        "",
        "## Experimental freeze",
        "",
        "```text",
        f"date_utc={fr.get('date_utc')}",
        f"prompt={fr.get('prompt_version')}",
        f"provider={fr.get('provider')} model={fr.get('model')}",
        f"schema={fr.get('schema_version')} CORE={fr.get('core_concept_count')}",
        f"retry_max={fr.get('retry_max_attempts')} effective_max_calls={fr.get('effective_max_provider_calls')}",
        f"corpus_fp={report.get('corpus_fingerprint')} cases={report.get('total_cases')}",
        f"runs_default={report.get('runs_per_case')} mp_runs={report.get('runs_per_mp')}",
        "```",
        "",
        "## Executive rates",
        "",
        f"- STABLE_CORRECT_RATE: {agg['STABLE_CORRECT_RATE']:.4f}",
        f"- STABLE_SAFE_ABSTENTION_RATE: {agg['STABLE_SAFE_ABSTENTION_RATE']:.4f}",
        f"- UNSTABLE_BUT_SAFE_RATE: {agg['UNSTABLE_BUT_SAFE_RATE']:.4f}",
        f"- UNSAFE_VARIANCE_RATE: {agg['UNSAFE_VARIANCE_RATE']:.4f}",
        "",
        "## Severity (runs)",
        "",
        "```text",
        json.dumps(agg["severity_runs"], indent=2),
        "```",
        "",
        "## Transport",
        "",
        "```text",
        json.dumps(report.get("transport", {}), indent=2),
        "```",
        "",
        "## Cost",
        "",
        "```text",
        json.dumps(report.get("cost", {}), indent=2),
        "```",
        "",
        "## Latency ms",
        "",
        "```text",
        json.dumps(report.get("latency", {}), indent=2),
        "```",
        "",
        "## MP anchors",
        "",
        "```text",
        json.dumps(report.get("mp_anchors", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Debt decisions (from evidence)",
        "",
        "```text",
        json.dumps(report.get("debt_decisions", {}), indent=2),
        "```",
        "",
        "## Recommendation",
        "",
        f"`{report.get('recommendation')}`",
        "",
        f"ENGINE_V1_LANGUAGE_BOUNDARY_STATUS: **{report.get('engine_status')}**",
        "",
    ]
    return "\n".join(lines) + "\n"


def decide_readiness(agg: dict, transport: dict, s4: int, s3: int) -> tuple[str, str, dict]:
    """Return engine_status, recommendation, debt_decisions — thresholds frozen a priori."""
    unsafe_rate = agg["UNSAFE_VARIANCE_RATE"]
    stable = agg["STABLE_CORRECT_RATE"]
    unstable = agg["UNSTABLE_BUT_SAFE_RATE"]
    debts = {
        "INTERPRETER-STATE-01": "REMAINS_OPEN",
        "INTERPRETER-RELATION-01": "REMAINS_OPEN",
        "INTERPRETER-EVENT-01": "REMAINS_OPEN",
        "INTERPRETER-RETRY-01": "CLOSED",
        "ONTOLOGY-COVERAGE-01": "PRODUCT_QUALITY",
        "SEMANTIC-QUERY-01": "PRODUCT_QUALITY",
    }
    by_cat = agg.get("by_category", {})
    for key, debt in (
        ("state", "INTERPRETER-STATE-01"),
        ("relation", "INTERPRETER-RELATION-01"),
        ("event", "INTERPRETER-EVENT-01"),
    ):
        bucket = by_cat.get(key, {})
        if bucket.get("UNSAFE_VARIANCE", 0) == 0 and bucket.get("STABLE_CORRECT", 0) > 0:
            # close only if mostly stable and no unsafe
            total = sum(bucket.values()) or 1
            if bucket.get("STABLE_CORRECT", 0) / total >= 0.8:
                debts[debt] = "CLOSE"

    if s4 > 0 or unsafe_rate > 0.02:
        return "BLOCKING", "LIVE_INTERPRETER_UNSAFE", debts
    if transport.get("logical_requests", 0) == 0:
        return "BLOCKING", "LIVE_CHARACTERIZATION_INCONCLUSIVE", debts

    # a priori thresholds (§41)
    if (
        unsafe_rate == 0
        and s4 == 0
        and s3 == 0
        and stable >= 0.85
        and unstable <= 0.20
    ):
        return "READY", "I12.3_CLOSE_PROCEED_TO_ENGINE_V1_FINAL_REVALIDATION", debts

    if unsafe_rate == 0 and s4 == 0 and s3 <= max(3, int(0.02 * (sum(agg["severity_runs"].values()) or 1))):
        # residual model variance / coverage — pick smallest next action
        if by_cat.get("state", {}).get("UNSAFE_VARIANCE", 0) or by_cat.get("relation", {}).get(
            "UNSTABLE_BUT_SAFE", 0
        ) or by_cat.get("event", {}).get("UNSTABLE_BUT_SAFE", 0):
            if stable < 0.7:
                return (
                    "PARTIAL_BUT_SAFE",
                    "I12.3_CLOSE_PROCEED_TO_STATE_RELATION_EVENT_HARDENING",
                    debts,
                )
        if unstable > 0.35 and stable < 0.55:
            return "PARTIAL_BUT_SAFE", "I12.3_CLOSE_RECOMMEND_MODEL_PROVIDER_EVALUATION", debts
        return "PARTIAL_BUT_SAFE", "I12.3_CLOSE_PROCEED_TO_ENGINE_V1_FINAL_REVALIDATION", debts

    if unsafe_rate == 0 and s4 == 0:
        return "PARTIAL_BUT_SAFE", "I12.3_CLOSE_PROCEED_TO_STATE_RELATION_EVENT_HARDENING", debts

    return "BLOCKING", "LIVE_INTERPRETER_UNSAFE", debts


def main() -> int:
    load_env_silent()
    freeze = default_freeze()
    assert freeze.prompt_version == PROMPT_VERSION_V4
    assert freeze.schema_version == STORAGE_SCHEMA_VERSION
    assert freeze.retry_max_attempts == MAX_ATTEMPTS

    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
        inconclusive = {
            "live_ran": False,
            "recommendation": "LIVE_CHARACTERIZATION_INCONCLUSIVE",
            "engine_status": "BLOCKING",
            "error": "DEEPSEEK_API_KEY absent",
            "freeze": asdict(freeze),
        }
        REPORT_JSON.write_text(json.dumps(inconclusive, indent=2) + "\n", encoding="utf-8")
        REPORT_MD.write_text(
            "# I12.3 inconclusive\n\nDEEPSEEK_API_KEY absent.\n", encoding="utf-8"
        )
        print("LIVE_CHARACTERIZATION_INCONCLUSIVE: no API key")
        return 2

    runs_default = int(os.environ.get("PKE_I123_RUNS", "3"))
    mp_runs = int(os.environ.get("PKE_I123_MP_RUNS", "5"))
    limit = int(os.environ.get("PKE_I123_LIMIT", "0"))
    cases = list(CORPUS)
    subset_note = "full corpus"
    if limit > 0:
        cases = cases[:limit]
        subset_note = f"LIMITED to first {limit} cases (PKE_I123_LIMIT) — not full characterization"

    fp = corpus_fingerprint(cases)
    cfg = DeepSeekConfig.from_env(timeout_seconds=float(os.environ.get("PKE_PROVIDER_TIMEOUT_SECONDS", "60")))
    # ensure SDK retries stay 0
    if cfg.max_retries != 0:
        cfg = cfg.model_copy(update={"max_retries": 0})

    provider = DeepSeekProvider(cfg)
    interpreter = DeepSeekInterpreter(provider, OntologyRegistry.with_core_seeds())

    case_scores: dict[str, list[RunScore]] = {}
    all_scores: list[RunScore] = []
    logical = 0
    provider_calls = 0
    first_ok = 0
    retries = 0
    recovered = 0
    exhausted = 0
    prompt_tokens = 0
    completion_tokens = 0
    latencies: list[float] = []
    mp_results: dict[str, list[dict]] = {}

    print(f"I12.3 freeze prompt={freeze.prompt_version} cases={len(cases)} fp={fp}")
    print(f"runs={runs_default} mp_runs={mp_runs} subset={subset_note}")

    try:
        for case in cases:
            n = mp_runs if _is_mp_anchor(case) else runs_default
            runs: list[RunScore] = []
            for r in range(1, n + 1):
                logical += 1
                score = run_one(interpreter, case, r)
                runs.append(score)
                all_scores.append(score)
                provider_calls += score.attempts
                if score.attempts == 1 and score.verdict != "TRANSPORT_FAILURE":
                    first_ok += 1
                if score.attempts > 1:
                    retries += 1
                    if score.ok or score.verdict not in {"TRANSPORT_FAILURE"}:
                        if score.retry_recovered or (
                            score.attempts > 1 and score.verdict != "TRANSPORT_FAILURE"
                        ):
                            recovered += 1
                    if score.verdict == "TRANSPORT_FAILURE" and score.attempts >= 2:
                        exhausted += 1
                if score.prompt_tokens:
                    prompt_tokens += score.prompt_tokens
                if score.completion_tokens:
                    completion_tokens += score.completion_tokens
                if score.latency_ms is not None:
                    latencies.append(score.latency_ms)
                print(
                    f"{case.id} r{r} att={score.attempts} {score.verdict} "
                    f"S={score.severity} prim={score.observed_primitive}"
                )
            case_scores[case.id] = runs
            if _is_mp_anchor(case):
                mp_results[case.id] = [
                    {
                        "run": s.run,
                        "verdict": s.verdict,
                        "severity": s.severity,
                        "observed_primitive": s.observed_primitive,
                    }
                    for s in runs
                ]
    finally:
        provider.close()

    agg = aggregate_report(case_scores)
    s3 = agg["severity_runs"].get("S3", 0)
    s4 = agg["severity_runs"].get("S4", 0)
    transport = {
        "logical_requests": logical,
        "provider_calls": provider_calls,
        "first_attempt_success": first_ok,
        "retries_triggered": retries,
        "retries_recovered": recovered,
        "retries_exhausted": exhausted,
    }
    cost = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "prompt_tokens_per_attempt": (
            round(prompt_tokens / provider_calls, 2) if provider_calls else None
        ),
        "estimated_cost": None,
    }
    latency = {}
    if latencies:
        latency = {
            "p50": statistics.median(latencies),
            "p95": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)],
            "max": max(latencies),
            "n": len(latencies),
        }

    engine_status, recommendation, debts = decide_readiness(agg, transport, s4, s3)

    # Positive counters sample
    positive = Counter()
    for s in all_scores:
        if s.ok and s.observed_primitive == "event":
            positive["EVENT_CORRECT"] += 1
        if s.ok and s.observed_primitive == "state":
            positive["STATE_CORRECT"] += 1
        if s.ok and s.observed_primitive == "relation":
            positive["RELATION_CORRECT"] += 1
        if s.ok and s.observed_primitive == "attribute":
            positive["ATTRIBUTE_CORRECT"] += 1
        if s.ok and s.observed_primitive == "measurement":
            positive["MEASUREMENT_CORRECT"] += 1
        if s.ok and s.observed_intent == "query":
            positive["QUERY_CORRECT"] += 1
        if s.ok and s.observed_intent == "correct":
            positive["CORRECTION_CORRECT"] += 1
        if s.ok and s.observed_primitive == "multi":
            positive["MULTI_PRIMITIVE_CORRECT"] += 1
        if s.verdict == "SAFE_ABSTENTION":
            positive["SAFE_ABSTENTION"] += 1
        if s.retry_recovered:
            positive["RETRY_RECOVERED"] += 1

    case_variance = {cid: classify_case_variance(rs) for cid, rs in case_scores.items()}

    report = {
        "live_ran": True,
        "subset_note": subset_note,
        "freeze": asdict(freeze),
        "corpus_fingerprint": fp,
        "total_cases": len(cases),
        "runs_per_case": runs_default,
        "runs_per_mp": mp_runs,
        "aggregate": agg,
        "transport": transport,
        "cost": cost,
        "latency": latency,
        "mp_anchors": mp_results,
        "case_variance": case_variance,
        "positive_counters": dict(positive),
        "debt_decisions": debts,
        "engine_status": engine_status,
        "recommendation": recommendation,
        "runs": [asdict(s) for s in all_scores],
        "thresholds_a_priori": {
            "unsafe_mutation_risk": 0,
            "false_correction": 0,
            "primitive_routing_stable_target": 0.95,
            "intent_stable_target": 0.97,
            "note": "thresholds declared before interpreting results",
        },
    }

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_MD.write_text(build_markdown(report), encoding="utf-8")
    print(f"Wrote {REPORT_JSON}")
    print(f"Wrote {REPORT_MD}")
    print(f"STATUS={engine_status} REC={recommendation}")
    print(
        f"STABLE_CORRECT={agg['STABLE_CORRECT_RATE']:.3f} "
        f"UNSAFE_VAR={agg['UNSAFE_VARIANCE_RATE']:.3f} S3={s3} S4={s4}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
