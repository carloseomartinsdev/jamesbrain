"""Aggregate I12.6 Stage A artifacts into closure report JSON."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "src", _ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from tests.engine_v1_baseline.corpus import EngineCase
from tests.engine_v1_live_characterization.scoring import RunScore, classify_case_variance
from tests.model_provider_evaluation.candidates import all_candidates
from tests.model_provider_evaluation.corpus import STAGE_A_CORPUS, _is_mp_anchor
from tests.model_provider_evaluation.freeze import default_freeze, frozen_thresholds

ARTIFACT_DIR = _ROOT / "docs" / "reports" / "i126_artifacts"
SUMMARY_JSON = _ROOT / "docs" / "reports" / "I12.6-MODEL-PROVIDER-EVALUATION.json"
SUMMARY_MD = _ROOT / "docs" / "reports" / "I12.6-MODEL-PROVIDER-EVALUATION.md"

MP_MARKERS = {
    "MP1": "medi a temperatura e deu 95",
    "MP2": "olhei o tanque e ele estava com 20",
    "MP3": "pesei a caixa: 10",
    "MP4": "consultei o saldo e tinha r$2500",
    "MP5": "o sensor mediu 38",
}


def _load_rows(candidate_id: str) -> list[dict]:
    path = ARTIFACT_DIR / f"{candidate_id}.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _score_from_dict(d: dict) -> RunScore:
    return RunScore(**{k: d[k] for k in RunScore.__dataclass_fields__ if k in d})


def _pctile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round((p / 100) * (len(s) - 1)))))
    return s[idx]


def _mp_anchor_for(case: EngineCase) -> str | None:
    u = case.utterance.lower()
    for name, marker in MP_MARKERS.items():
        if marker in u:
            return name
    return None


def aggregate_candidate(spec, cases: list[EngineCase]) -> dict:
    rows = _load_rows(spec.candidate_id)
    if not rows and spec.availability() != "EXECUTABLE":
        return {
            "candidate_id": spec.candidate_id,
            "provider": spec.provider,
            "model": spec.model,
            "status": spec.availability(),
            "total_runs": 0,
        }

    by_case: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_case[r["case_id"]].append(r)

    raw_sev = Counter()
    post_sev = Counter()
    raw_verdict = Counter()
    post_verdict = Counter()
    latencies: list[float] = []
    tokens = 0
    retries = 0
    recovered = 0
    clarify = 0
    safe_abs = 0
    guard_blocked = 0
    guard_rejected_true = 0
    post_false_corr = 0
    raw_false_corr = 0

    variance_raw: Counter = Counter()
    variance_post: Counter = Counter()

    primitive_post: dict[str, Counter] = defaultdict(Counter)
    mp_matrix: dict[str, dict] = {}

    for case in cases:
        case_rows = sorted(by_case.get(case.id, []), key=lambda x: x["run"])
        if not case_rows:
            continue

        raw_scores = [_score_from_dict(r["raw_score"]) for r in case_rows]
        post_scores = [_score_from_dict(r["post_score"]) for r in case_rows]

        variance_raw[classify_case_variance(raw_scores)] += 1
        variance_post[classify_case_variance(post_scores)] += 1

        for r in case_rows:
            rs, ps = r["raw_score"], r["post_score"]
            raw_sev[rs["severity"]] += 1
            post_sev[ps["severity"]] += 1
            raw_verdict[rs["verdict"]] += 1
            post_verdict[ps["verdict"]] += 1
            if r.get("latency_ms") is not None:
                latencies.append(float(r["latency_ms"]))
            if r.get("total_tokens"):
                tokens += int(r["total_tokens"])
            if r.get("attempts", 1) > 1:
                retries += 1
                if ps.get("ok"):
                    recovered += 1
            notes = " ".join(str(x) for x in ps.get("notes", []))
            if "POST_GUARD_BLOCKED_FALSE_CORRECTION" in notes:
                guard_blocked += 1
            if "POST_GUARD_REJECTED_TRUE_CORRECTION" in notes:
                guard_rejected_true += 1
            if ps.get("verdict") == "SAFE_ABSTENTION":
                safe_abs += 1
            if "CLARIFICATION" in notes.upper():
                clarify += 1
            if rs.get("severity") == "S4" and "FALSE_CORRECTION" in notes.upper() or rs.get("notes") and "RAW_FALSE_CORRECTION" in str(rs.get("notes")):
                raw_false_corr += 1
            if ps.get("severity") == "S4":
                post_false_corr += 1

            cat = case.category
            if ps.get("verdict") == "CORRECT" and ps.get("ok"):
                primitive_post[cat]["stable_correct"] += 1
            elif ps.get("severity") in {"S3", "S4"}:
                primitive_post[cat]["unsafe"] += 1
            else:
                primitive_post[cat]["safe_unstable"] += 1

        mp = _mp_anchor_for(case)
        if mp:
            mp_matrix[mp] = {
                "runs": len(case_rows),
                "raw_outcomes": [r["raw_score"]["verdict"] for r in case_rows],
                "post_outcomes": [r["post_score"]["verdict"] for r in case_rows],
                "raw_primitives": [r["raw_score"].get("observed_primitive") for r in case_rows],
                "post_primitives": [r["post_score"].get("observed_primitive") for r in case_rows],
                "post_severities": [r["post_score"]["severity"] for r in case_rows],
            }

    n_cases = len(by_case)
    n_runs = len(rows)
    unsafe_cases = variance_post.get("UNSAFE_VARIANCE", 0)
    unsafe_rate = (unsafe_cases / n_cases) if n_cases else 0.0
    stable_correct = variance_post.get("STABLE_CORRECT", 0)
    unstable_safe = variance_post.get("UNSTABLE_BUT_SAFE", 0) + variance_post.get(
        "STABLE_SAFE_ABSTENTION", 0
    )
    raw_unsafe = variance_raw.get("UNSAFE_VARIANCE", 0)

    thresholds = frozen_thresholds()
    status = "INCONCLUSIVE"
    if n_runs == 0:
        status = spec.availability()
    elif post_sev.get("S4", 0) > thresholds.post_engine_s4:
        status = "REJECTED_SAFETY"
    elif unsafe_rate > thresholds.post_engine_unsafe_variance_max:
        status = "REJECTED_SAFETY"
    elif n_cases and (stable_correct / n_cases) < 0.20:
        status = "REJECTED_RELIABILITY"
    elif post_sev.get("S3", 0) / max(n_runs, 1) > 0.05:
        status = "REJECTED_RELIABILITY"
    else:
        status = "VIABLE"

    return {
        "candidate_id": spec.candidate_id,
        "provider": spec.provider,
        "model": spec.model,
        "role": spec.role,
        "status": status,
        "total_cases_with_results": n_cases,
        "total_runs": n_runs,
        "logical_requests": n_runs,
        "provider_calls_approx": sum(int(r.get("attempts") or 1) for r in rows),
        "RAW_STABLE_CORRECT": variance_raw.get("STABLE_CORRECT", 0),
        "RAW_UNSTABLE_SAFE": variance_raw.get("UNSTABLE_BUT_SAFE", 0)
        + variance_raw.get("STABLE_SAFE_ABSTENTION", 0),
        "RAW_UNSAFE_CASES": raw_unsafe,
        "POST_ENGINE_STABLE_CORRECT": stable_correct,
        "POST_ENGINE_UNSTABLE_SAFE": unstable_safe,
        "POST_ENGINE_UNSAFE_CASES": unsafe_cases,
        "POST_ENGINE_UNSAFE_VARIANCE_RATE": unsafe_rate,
        "RAW_S3": raw_sev.get("S3", 0),
        "RAW_S4": raw_sev.get("S4", 0),
        "POST_S3": post_sev.get("S3", 0),
        "POST_S4": post_sev.get("S4", 0),
        "CLARIFICATION_RATE": clarify / n_runs if n_runs else 0.0,
        "SAFE_ABSTENTION_RATE": safe_abs / n_runs if n_runs else 0.0,
        "RETRIES_TRIGGERED": retries,
        "RETRIES_RECOVERED": recovered,
        "RAW_FALSE_CORRECTION": raw_false_corr,
        "GUARD_BLOCKED_FALSE_CORRECTION": guard_blocked,
        "GUARD_REJECTED_TRUE_CORRECTION": guard_rejected_true,
        "POST_ENGINE_FALSE_CORRECTION_ACCEPTED": post_false_corr,
        "latency_p50": _pctile(latencies, 50),
        "latency_p95": _pctile(latencies, 95),
        "latency_max": max(latencies) if latencies else None,
        "total_tokens": tokens,
        "cost": "NOT_PRICED_IN_REPO",
        "primitive_matrix_post": {k: dict(v) for k, v in primitive_post.items()},
        "mp_matrix": mp_matrix,
    }


def _delta(alt: dict, base: dict, key: str):
    if not alt.get("total_runs") or not base.get("total_runs"):
        return None
    return alt.get(key, 0) - base.get(key, 0)


def _pick_best(results: list[dict]) -> str:
    viable = [r for r in results if r.get("status") == "VIABLE" and r.get("total_runs")]
    if not viable:
        return "NONE"
    baseline = next((r for r in results if r["candidate_id"] == "baseline_deepseek_chat"), None)
    if baseline is None:
        return max(viable, key=lambda r: r.get("POST_ENGINE_STABLE_CORRECT", 0))["candidate_id"]
    best = max(
        viable,
        key=lambda r: (
            r.get("POST_ENGINE_STABLE_CORRECT", 0),
            -r.get("POST_ENGINE_UNSAFE_CASES", 99),
            -r.get("POST_S3", 99),
        ),
    )
    if best["candidate_id"] == baseline["candidate_id"]:
        return "NONE"
    if best.get("POST_ENGINE_STABLE_CORRECT", 0) <= baseline.get("POST_ENGINE_STABLE_CORRECT", 0):
        return "NONE"
    return best["candidate_id"]


def write_reports(results: list[dict]) -> None:
    freeze = default_freeze()
    thresholds = frozen_thresholds()
    baseline = next((r for r in results if r["candidate_id"] == "baseline_deepseek_chat"), {})
    best = _pick_best(results)

    for r in results:
        if r.get("total_runs"):
            r["delta_vs_baseline"] = {
                "stable_correct": _delta(r, baseline, "POST_ENGINE_STABLE_CORRECT"),
                "unstable_safe": _delta(r, baseline, "POST_ENGINE_UNSTABLE_SAFE"),
                "unsafe_cases": _delta(r, baseline, "POST_ENGINE_UNSAFE_CASES"),
                "post_s3": _delta(r, baseline, "POST_S3"),
                "post_s4": _delta(r, baseline, "POST_S4"),
                "retries": _delta(r, baseline, "RETRIES_TRIGGERED"),
                "latency_p50": None
                if r.get("latency_p50") is None or baseline.get("latency_p50") is None
                else r["latency_p50"] - baseline["latency_p50"],
            }

    payload = {
        "experiment_id": "I12.6",
        "stage": "A",
        "freeze": freeze.__dict__,
        "thresholds_a_priori": thresholds.__dict__,
        "corpus_size": len(STAGE_A_CORPUS),
        "candidates": results,
        "best_candidate": best,
        "openai_candidates_status": "NOT_EXECUTED_NO_CREDENTIAL",
    }
    SUMMARY_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# I12.6 — Model / Provider Evaluation (Stage A)",
        "",
        f"Corpus: {len(STAGE_A_CORPUS)} cases",
        f"Best candidate: **{best}**",
        "",
        "## Comparison",
        "",
        "| Candidate | Post S4 | Post S3 | Stable Correct | Unstable Safe | Unsafe | Retries | p50 ms | Cost | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        if not r.get("total_runs"):
            lines.append(
                f"| {r['candidate_id']} | — | — | — | — | — | — | — | — | {r.get('status')} |"
            )
            continue
        lines.append(
            f"| {r['candidate_id']} | {r.get('POST_S4', 0)} | {r.get('POST_S3', 0)} | "
            f"{r.get('POST_ENGINE_STABLE_CORRECT', 0)} | {r.get('POST_ENGINE_UNSTABLE_SAFE', 0)} | "
            f"{r.get('POST_ENGINE_UNSAFE_CASES', 0)} | {r.get('RETRIES_TRIGGERED', 0)} | "
            f"{r.get('latency_p50') or '—'} | {r.get('cost')} | {r.get('status')} |"
        )
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {SUMMARY_JSON}")
    print(f"Wrote {SUMMARY_MD}")


def main() -> int:
    cases = list(STAGE_A_CORPUS)
    results = [aggregate_candidate(spec, cases) for spec in all_candidates()]
    write_reports(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
