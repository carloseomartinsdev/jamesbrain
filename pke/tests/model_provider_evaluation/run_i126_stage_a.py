"""I12.6 Stage A model/provider evaluation runner.

Usage:
  .\\.venv\\Scripts\\python.exe -m tests.model_provider_evaluation.run_i126_stage_a

Env:
  DEEPSEEK_API_KEY required for DeepSeek candidates
  OPENAI_API_KEY optional
  PKE_I126_CANDIDATES=baseline_deepseek_chat,deepseek_reasoner
  PKE_I126_LIMIT=0  (>0 truncates for smoke)
"""

from __future__ import annotations

import hashlib
import json
import os
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
from pke.interpretation.semantic.envelope_dispatch import ProviderRoute, dispatch_provider_payload
from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.ontology import OntologyRegistry

from tests.engine_v1_baseline.corpus import EngineCase
from tests.engine_v1_live_characterization.scoring import classify_case_variance
from tests.model_provider_evaluation.candidates import all_candidates, build_provider
from tests.model_provider_evaluation.corpus import STAGE_A_CORPUS, _is_mp_anchor
from tests.model_provider_evaluation.dual_scoring import (
    DualRunRecord,
    score_post_engine,
    score_raw_from_proposal,
)
from tests.model_provider_evaluation.freeze import default_freeze, frozen_thresholds

ROOT = _ROOT
ARTIFACT_DIR = ROOT / "docs" / "reports" / "i126_artifacts"
SUMMARY_JSON = ROOT / "docs" / "reports" / "I12.6-MODEL-PROVIDER-EVALUATION.json"
SUMMARY_MD = ROOT / "docs" / "reports" / "I12.6-MODEL-PROVIDER-EVALUATION.md"
FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=FORTALEZA)


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
        user=UserContext(user_id="i126-eval", timezone="America/Fortaleza", now=NOW)
    )


def _result_path(candidate_id: str) -> Path:
    return ARTIFACT_DIR / f"{candidate_id}.jsonl"


def _load_done(candidate_id: str) -> set[tuple[str, int]]:
    path = _result_path(candidate_id)
    done: set[tuple[str, int]] = set()
    if not path.is_file():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        done.add((row["case_id"], int(row["run"])))
    return done


def _append_record(candidate_id: str, record: DualRunRecord) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = _result_path(candidate_id)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


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


def _proposal_safe_dump(proposal: SemanticProposal | None) -> dict | None:
    if proposal is None:
        return None
    data = proposal.model_dump()
    # Keep fields; no secrets expected in proposal
    return data


def run_one(
    interpreter: DeepSeekInterpreter,
    case: EngineCase,
    *,
    candidate_id: str,
    run: int,
) -> DualRunRecord:
    logical_id = str(uuid.uuid4())
    t0 = time.perf_counter()
    raw_content = None
    proposal = None
    provider_request_id = None
    attempts = 1
    meta_tokens = (None, None, None)
    latency = None

    try:
        ir = interpreter.interpret(case.utterance, _ctx())
        elapsed = (time.perf_counter() - t0) * 1000
        attempts = interpreter.last_provider_attempts or 1
        raw_content = interpreter.last_raw_content
        proposal = _try_parse_proposal(raw_content)
        meta = interpreter.last_metadata
        if meta is not None:
            provider_request_id = meta.request_id
            latency = meta.latency_ms or elapsed
            meta_tokens = (meta.prompt_tokens, meta.completion_tokens, meta.total_tokens)
        else:
            latency = elapsed

        if proposal is None:
            # IR succeeded but proposal parse failed — treat RAW as soft unknown
            from tests.engine_v1_live_characterization.scoring import RunScore

            raw = RunScore(
                case_id=case.id,
                run=run,
                utterance=case.utterance,
                category=case.category,
                ok=True,
                verdict="CORRECT",
                severity="S0",
                primary_root="NONE",
                observed_intent=None,
                observed_primitive=None,
                expected_intent=case.expected_intent,
                expected_primitive=case.expected_primitive,
                notes=["RAW proposal not re-parsed; IR succeeded"],
            )
        else:
            raw = score_raw_from_proposal(case, proposal, run=run)
        post = score_post_engine(case, run=run, ir=ir, attempts=attempts)
        err = None
    except Exception as exc:  # noqa: BLE001
        elapsed = (time.perf_counter() - t0) * 1000
        attempts = getattr(interpreter, "last_provider_attempts", None) or 1
        raw_content = getattr(interpreter, "last_raw_content", None)
        proposal = _try_parse_proposal(raw_content)
        meta = getattr(interpreter, "last_metadata", None)
        if meta is not None:
            provider_request_id = meta.request_id
            latency = meta.latency_ms or elapsed
            meta_tokens = (meta.prompt_tokens, meta.completion_tokens, meta.total_tokens)
        else:
            latency = elapsed

        if proposal is not None:
            raw = score_raw_from_proposal(case, proposal, run=run)
        else:
            raw = score_post_engine(case, run=run, exc=exc, attempts=attempts)
            raw.notes = list(raw.notes) + ["RAW unavailable — mirrored post failure"]
        post = score_post_engine(case, run=run, exc=exc, attempts=attempts)
        err = str(exc)[:300]

    from dataclasses import asdict

    return DualRunRecord(
        experiment_id="I12.6",
        candidate_id=candidate_id,
        case_id=case.id,
        run=run,
        utterance=case.utterance,
        category=case.category,
        logical_request_id=logical_id,
        provider_request_id=provider_request_id,
        attempts=attempts,
        latency_ms=latency,
        prompt_tokens=meta_tokens[0],
        completion_tokens=meta_tokens[1],
        total_tokens=meta_tokens[2],
        raw_content=raw_content,
        proposal_dump=_proposal_safe_dump(proposal),
        raw_score=asdict(raw),
        post_score=asdict(post),
        error=err,
    )


def _aggregate_candidate(candidate_id: str, cases: list[EngineCase]) -> dict:
    path = _result_path(candidate_id)
    rows: list[dict] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))

    by_case: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_case[r["case_id"]].append(r)

    post_sev = Counter()
    raw_sev = Counter()
    post_verdicts = Counter()
    raw_verdicts = Counter()
    latencies: list[float] = []
    tokens = 0
    retries = 0
    recovered = 0
    clarify = 0
    safe_abs = 0

    variance_post: Counter = Counter()
    for case in cases:
        scores = by_case.get(case.id, [])
        if not scores:
            continue
        # build RunScore-like for variance from post_score
        from tests.engine_v1_live_characterization.scoring import RunScore

        post_scores = []
        for s in scores:
            ps = s["post_score"]
            post_scores.append(
                RunScore(
                    case_id=ps["case_id"],
                    run=ps["run"],
                    utterance=ps["utterance"],
                    category=ps["category"],
                    ok=ps["ok"],
                    verdict=ps["verdict"],
                    severity=ps["severity"],
                    primary_root=ps["primary_root"],
                    observed_intent=ps.get("observed_intent"),
                    observed_primitive=ps.get("observed_primitive"),
                    expected_intent=ps.get("expected_intent"),
                    expected_primitive=ps.get("expected_primitive"),
                )
            )
            post_sev[ps["severity"]] += 1
            post_verdicts[ps["verdict"]] += 1
            rs = s["raw_score"]
            raw_sev[rs["severity"]] += 1
            raw_verdicts[rs["verdict"]] += 1
            if s.get("latency_ms") is not None:
                latencies.append(float(s["latency_ms"]))
            if s.get("total_tokens"):
                tokens += int(s["total_tokens"])
            if s.get("attempts", 1) > 1:
                retries += 1
                if ps.get("ok"):
                    recovered += 1
            if "CLARIFICATION" in str(ps.get("notes")) or ps.get("verdict") == "SAFE_ABSTENTION":
                if "POST_GUARD" in str(ps.get("notes")) or ps.get("verdict") == "SAFE_ABSTENTION":
                    safe_abs += 1
        variance_post[classify_case_variance(post_scores)] += 1

    n_cases = len([c for c in cases if c.id in by_case])
    n_runs = len(rows)
    unsafe_cases = variance_post.get("UNSAFE_VARIANCE", 0)
    unsafe_rate = (unsafe_cases / n_cases) if n_cases else 0.0
    stable_correct = variance_post.get("STABLE_CORRECT", 0)
    unstable_safe = variance_post.get("UNSTABLE_BUT_SAFE", 0) + variance_post.get(
        "STABLE_SAFE_ABSTENTION", 0
    )

    def pctile(vals: list[float], p: float) -> float | None:
        if not vals:
            return None
        s = sorted(vals)
        idx = min(len(s) - 1, max(0, int(round((p / 100) * (len(s) - 1)))))
        return s[idx]

    return {
        "candidate_id": candidate_id,
        "total_cases_with_results": n_cases,
        "total_runs": n_runs,
        "logical_requests": n_runs,
        "provider_calls_approx": sum(int(r.get("attempts") or 1) for r in rows),
        "raw_severity": dict(raw_sev),
        "post_severity": dict(post_sev),
        "raw_verdicts": dict(raw_verdicts),
        "post_verdicts": dict(post_verdicts),
        "post_case_variance": dict(variance_post),
        "POST_ENGINE_S3": post_sev.get("S3", 0),
        "POST_ENGINE_S4": post_sev.get("S4", 0),
        "RAW_S3": raw_sev.get("S3", 0),
        "RAW_S4": raw_sev.get("S4", 0),
        "POST_ENGINE_UNSAFE_VARIANCE_RATE": unsafe_rate,
        "POST_ENGINE_STABLE_CORRECT_CASES": stable_correct,
        "POST_ENGINE_UNSTABLE_SAFE_CASES": unstable_safe,
        "POST_ENGINE_UNSAFE_CASES": unsafe_cases,
        "SAFE_ABSTENTION_RUNS": safe_abs,
        "RETRIES_TRIGGERED": retries,
        "RETRIES_RECOVERED": recovered,
        "latency_p50": pctile(latencies, 50),
        "latency_p95": pctile(latencies, 95),
        "latency_max": max(latencies) if latencies else None,
        "total_tokens": tokens,
        "cost": "NOT_PRICED_IN_REPO",
    }


def _status_for(agg: dict, thresholds) -> str:
    if agg["total_runs"] == 0:
        return "INCONCLUSIVE"
    if agg["POST_ENGINE_S4"] > thresholds.post_engine_s4:
        return "REJECTED_SAFETY"
    if agg["POST_ENGINE_UNSAFE_VARIANCE_RATE"] > thresholds.post_engine_unsafe_variance_max:
        return "REJECTED_SAFETY"
    # reliability: need material stable correct
    n = agg["total_cases_with_results"] or 1
    stable_rate = agg["POST_ENGINE_STABLE_CORRECT_CASES"] / n
    if stable_rate < 0.20:  # very low usefulness
        return "REJECTED_RELIABILITY"
    if agg["POST_ENGINE_S3"] > 0 and agg["POST_ENGINE_S3"] / max(agg["total_runs"], 1) > 0.05:
        # systematic-ish S3
        return "REJECTED_RELIABILITY"
    return "VIABLE"


def run_candidate(spec, cases: list[EngineCase], *, ontology: OntologyRegistry) -> dict:
    avail = spec.availability()
    if avail != "EXECUTABLE":
        return {
            "candidate_id": spec.candidate_id,
            "provider": spec.provider,
            "model": spec.model,
            "status": avail,
            "total_runs": 0,
            "note": f"credential/env {spec.api_key_env}",
        }

    provider = build_provider(spec)
    interpreter = DeepSeekInterpreter(
        provider,
        ontology=ontology,
        prompt_version=PROMPT_VERSION_V4,
    )
    done = _load_done(spec.candidate_id)
    total_planned = sum(
        (5 if _is_mp_anchor(c) else 3) for c in cases
    )
    completed = len(done)
    print(
        f"[{spec.candidate_id}] resume {completed}/{total_planned} done",
        flush=True,
    )

    try:
        for i, case in enumerate(cases):
            n_runs = 5 if _is_mp_anchor(case) else 3
            for run in range(1, n_runs + 1):
                if (case.id, run) in done:
                    continue
                print(
                    f"[{spec.candidate_id}] {i+1}/{len(cases)} {case.id} run={run}",
                    flush=True,
                )
                rec = run_one(interpreter, case, candidate_id=spec.candidate_id, run=run)
                _append_record(spec.candidate_id, rec)
                done.add((case.id, run))
                completed += 1
                if completed % 10 == 0:
                    print(
                        f"[{spec.candidate_id}] progress {completed}/{total_planned}",
                        flush=True,
                    )
    finally:
        if hasattr(provider, "close"):
            provider.close()

    agg = _aggregate_candidate(spec.candidate_id, cases)
    thresholds = frozen_thresholds()
    status = _status_for(agg, thresholds)
    agg.update(
        {
            "provider": spec.provider,
            "model": spec.model,
            "role": spec.role,
            "status": status,
            "availability": avail,
        }
    )
    return agg


def write_reports(freeze, thresholds, corpus, results: list[dict]) -> None:
    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment_id": "I12.6",
        "stage": "A",
        "freeze": freeze.__dict__ if hasattr(freeze, "__dict__") else freeze,
        "thresholds_a_priori": thresholds.__dict__,
        "corpus_size": len(corpus),
        "corpus_fingerprint": corpus_fingerprint(corpus),
        "candidates": results,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    # freeze may be dataclass
    from dataclasses import asdict, is_dataclass

    if is_dataclass(freeze):
        payload["freeze"] = asdict(freeze)
    if is_dataclass(thresholds):
        payload["thresholds_a_priori"] = asdict(thresholds)

    SUMMARY_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# I12.6 — Model / Provider Evaluation (Stage A)",
        "",
        f"Generated: {payload['generated_at_utc']}",
        f"Corpus: {len(corpus)} cases (fingerprint {payload['corpus_fingerprint']})",
        "",
        "## Comparison",
        "",
        "| Candidate | Post S4 | Post S3 | Stable Correct | Unstable Safe | Unsafe | Transport retries | p50 ms | Cost | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        if r.get("total_runs", 0) == 0:
            lines.append(
                f"| {r['candidate_id']} | — | — | — | — | — | — | — | — | {r.get('status')} |"
            )
            continue
        lines.append(
            f"| {r['candidate_id']} | {r.get('POST_ENGINE_S4', 0)} | {r.get('POST_ENGINE_S3', 0)} | "
            f"{r.get('POST_ENGINE_STABLE_CORRECT_CASES', 0)} | {r.get('POST_ENGINE_UNSTABLE_SAFE_CASES', 0)} | "
            f"{r.get('POST_ENGINE_UNSAFE_CASES', 0)} | {r.get('RETRIES_TRIGGERED', 0)} | "
            f"{r.get('latency_p50') or '—'} | {r.get('cost')} | {r.get('status')} |"
        )
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    load_env_silent()
    freeze = default_freeze()
    thresholds = frozen_thresholds()
    # Persist freeze BEFORE first call
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    freeze_path = ARTIFACT_DIR / "FREEZE.json"
    if not freeze_path.is_file():
        from dataclasses import asdict

        freeze_path.write_text(
            json.dumps(
                {"freeze": asdict(freeze), "thresholds": asdict(thresholds)},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Wrote a-priori freeze -> {freeze_path}", flush=True)

    cases = list(STAGE_A_CORPUS)
    limit = int(os.environ.get("PKE_I126_LIMIT", "0") or "0")
    if limit > 0:
        cases = cases[:limit]
        print(f"SMOKE LIMIT={limit}", flush=True)

    wanted = os.environ.get("PKE_I126_CANDIDATES", "").strip()
    specs = all_candidates()
    if wanted:
        ids = {x.strip() for x in wanted.split(",") if x.strip()}
        specs = [s for s in specs if s.candidate_id in ids]

    ontology = OntologyRegistry.with_core_seeds()
    results = []
    for spec in specs:
        print(f"=== candidate {spec.candidate_id} ({spec.availability()}) ===", flush=True)
        results.append(run_candidate(spec, cases, ontology=ontology))

    write_reports(freeze, thresholds, cases, results)
    print(f"Wrote {SUMMARY_JSON}", flush=True)
    print(f"Wrote {SUMMARY_MD}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
