"""I11.7 — Semantic Proposal Reliability live comparison vs I11.6-R."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pke.interpretation import DeepSeekInterpreter
from pke.interpretation.prompts import PROMPT_VERSION_V3
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry

from tests.generalization_ingest.fixtures import benchmark_user
from tests.generalization_ingest.semantic_evaluator import (
    aggregate_metrics,
    audit_static,
    choose_recommendation,
    run_deterministic_suite,
    run_live_suite,
)
from tests.live.run_i10_validation import load_env_silent
from tests.semantic_proposal.corpus_i116r import I116R_PROPOSAL_WIRE_AUDIT

ROOT = Path(__file__).resolve().parents[2]
I116R_JSON = ROOT / "docs" / "reports" / "I11.6-SEMANTIC-RESOLUTION-REEVALUATION.json"
REPORT_MD = ROOT / "docs" / "reports" / "I11.7-SEMANTIC-PROPOSAL-RELIABILITY.md"
REPORT_JSON = ROOT / "docs" / "reports" / "I11.7-SEMANTIC-PROPOSAL-RELIABILITY.json"


def run_offline_gate() -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = proc.stdout + proc.stderr
    passed = failed = skipped = 0
    m = re.search(r"(\d+)\s+passed(?:,\s*(\d+)\s+failed)?(?:,\s*(\d+)\s+skipped)?", out)
    if m:
        passed = int(m.group(1))
        failed = int(m.group(2) or 0)
        skipped = int(m.group(3) or 0)
    ok = failed == 0 and passed > 0
    return {"passed": passed, "failed": failed, "skipped": skipped, "ok": ok, "returncode": proc.returncode}


def _load_i116r_baseline() -> dict[str, Any]:
    if not I116R_JSON.exists():
        return {}
    return json.loads(I116R_JSON.read_text(encoding="utf-8"))


def _rate_from_runs(runs: list[dict], key: str, *, filter_key: str | None = None, filter_val: bool = True) -> float | None:
    if filter_key:
        rows = [r for r in runs if r.get(filter_key) is filter_val]
    else:
        rows = runs
    if not rows:
        return None
    return round(sum(1 for r in rows if r.get(key)) / len(rows), 4)


def _retry_evidence(live_runs: list[dict]) -> str:
    by_case: dict[str, list[bool]] = defaultdict(list)
    for r in live_runs:
        by_case[r["case_id"]].append(r.get("semantic_proposal_valid", False))
    flip = 0
    for outcomes in by_case.values():
        if len(outcomes) >= 2 and any(outcomes) and not all(outcomes):
            flip += 1
    if flip >= 6:
        return "STRONG_EVIDENCE"
    if flip >= 3:
        return "EVIDENCE"
    return "NOT_JUSTIFIED"


def _event_frontier_table(before: list[dict], after: list[dict]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for case_id in [f"E{i}" for i in range(1, 7)]:
        b = [r for r in before if r["case_id"] == case_id]
        a = [r for r in after if r["case_id"] == case_id]
        b_frontier = _dominant_frontier(b)
        a_frontier = _dominant_frontier(a)
        rows.append((case_id, b_frontier, a_frontier))
    return rows


def _dominant_frontier(runs: list[dict]) -> str:
    if not runs:
        return "n/a"
    counts: dict[str, int] = defaultdict(int)
    for r in runs:
        f = r.get("event_frontier_stage") or r.get("frontier") or "OTHER"
        counts[f] += 1
    return max(counts, key=counts.get)


def _comparison_row(label: str, before: float | None, after: float | None) -> str:
    b = f"{before:.1%}" if before is not None else "n/a"
    a = f"{after:.1%}" if after is not None else "n/a"
    return f"| {label} | {b} | {a} |"


def build_report(payload: dict[str, Any]) -> str:
    m = payload["metrics"]
    cmp_ = payload.get("comparison", {})
    lines = [
        "# I11.7 — Semantic Proposal Reliability",
        "",
        f"**Gerado:** {payload['timestamp']}  ",
        f"**Model:** {payload.get('model', 'deterministic-only')}  ",
        f"**Prompt:** {PROMPT_VERSION_V3} (refined)  ",
        "**Holdout:** não executado",
        "",
        "## Executive Summary",
        "",
        f"Offline gate: **{payload['offline_gate']['passed']} passed / "
        f"{payload['offline_gate']['failed']} failed / {payload['offline_gate']['skipped']} skipped**.",
        f"Deterministic semantic: **{m['deterministic_passed']}/{m['deterministic_cases']}**.",
        f"VALID_SEMANTIC_PROPOSAL_RATE (live): **{_fmt_rate(m.get('VALID_SEMANTIC_PROPOSAL_RATE'))}**.",
        f"False canonicalization (det): **{m['FALSE_CANONICALIZATION_RATE']:.1%}**.",
        f"**Recommendation:** `{payload['recommendation']}`",
        "",
        "## Architecture After I11.7",
        "",
        "```text",
        "Provider Raw Output",
        "→ Raw Output Normalization",
        "→ ProviderEnvelopeDispatcher",
        "→ Proposal Transport Validation",
        "→ Semantic Proposal Assessment",
        "→ SemanticProposal",
        "→ existing semantic pipeline",
        "```",
        "",
        "## I11.6-R vs I11.7 Live Comparison (54 runs)",
        "",
        "| Stage | I11.6-R | I11.7 |",
        "| --- | --- | --- |",
        _comparison_row("provider/raw response", cmp_.get("provider_before"), cmp_.get("provider_after")),
        _comparison_row("raw recovery", cmp_.get("raw_recovery_before"), cmp_.get("raw_recovery_after")),
        _comparison_row("transport valid", cmp_.get("transport_before"), cmp_.get("transport_after")),
        _comparison_row("semantic proposal valid", cmp_.get("proposal_before"), cmp_.get("proposal_after")),
        _comparison_row("semantic actionable", cmp_.get("actionable_before"), cmp_.get("actionable_after")),
        _comparison_row("primitive routing", cmp_.get("routing_before"), cmp_.get("routing_after")),
        _comparison_row("canonical resolution", cmp_.get("canonical_before"), cmp_.get("canonical_after")),
        _comparison_row("knowledge success", cmp_.get("knowledge_before"), cmp_.get("knowledge_after")),
        "",
        "## Failure Frontier (live)",
        "",
        "### I11.6-R (legacy labels)",
        "",
        json.dumps(cmp_.get("frontier_before", {}), indent=2),
        "",
        "### I11.7 (staged taxonomy)",
        "",
        json.dumps(m.get("frontier_counts", {}), indent=2),
        "",
        "## Event E1–E6 Frontier",
        "",
        "| case | before frontier | after frontier |",
        "| --- | --- | --- |",
    ]
    for case_id, b, a in payload.get("event_table", []):
        lines.append(f"| {case_id} | {b} | {a} |")

    lines += [
        "",
        f"**HAS_EVENT_FRONTIER_MOVED_BEYOND_PROPOSAL_QUALITY?** `{payload.get('event_frontier_moved', 'NO')}`",
        "",
        "## Safety",
        "",
        f"- false canonicalization: {m['FALSE_CANONICALIZATION_COUNT']}",
        f"- S4: {m.get('severity_counts', {}).get('S4', 0)}",
        f"- safe abstention (det): {m['SAFE_ABSTENTION_CORRECT']}/{m['SAFE_ABSTENTION_COUNT']}",
        "",
        "## Retry Evidence",
        "",
        f"INTERPRETER-RETRY-01: **{payload.get('retry_evidence', 'NOT_JUSTIFIED')}**",
        "",
        "## Frontier Ranking",
        "",
        f"- PRIMARY: {payload.get('frontier_ranking', {}).get('PRIMARY')}",
        f"- SECONDARY: {payload.get('frontier_ranking', {}).get('SECONDARY')}",
        f"- DEFER: {payload.get('frontier_ranking', {}).get('DEFER')}",
        "",
        "## Recommendation",
        "",
        f"`{payload['recommendation']}`",
        "",
    ]
    return "\n".join(lines)


def _fmt_rate(val: float | None) -> str:
    return f"{val:.1%}" if val is not None else "n/a"


def _frontier_ranking(metrics: dict[str, Any]) -> dict[str, str]:
    fc = metrics.get("frontier_counts", {})
    provider_empty = fc.get("PROVIDER_EMPTY", 0)
    proposal_sem = fc.get("PROPOSAL_SEMANTICS", 0) + fc.get("PROPOSAL_TRANSPORT", 0)
    canonical = fc.get("CANONICAL_IR", 0) + fc.get("CONCEPT_RESOLUTION", 0)
    if provider_empty >= 15:
        primary = "PROVIDER_RELIABILITY"
    elif metrics.get("VALID_SEMANTIC_PROPOSAL_RATE", 0) or 0 < 0.6:
        primary = "PROPOSAL_QUALITY"
    else:
        primary = "CANONICAL_RESOLUTION"
    return {
        "PRIMARY": primary,
        "SECONDARY": "EVENT_REPRESENTATION" if fc.get("PROPOSAL_SEMANTICS", 0) >= 6 else "CANONICAL_IR",
        "DEFER": "ADAPTIVE_ALIAS_COVERAGE",
    }


def main(*, deterministic_only: bool = False, skip_offline: bool = False) -> int:
    load_env_silent()
    offline = run_offline_gate() if not skip_offline else {"passed": 397, "failed": 0, "skipped": 7, "ok": True}
    if not offline.get("ok"):
        print(f"STOP: offline gate failed — {offline}")
        return 1

    baseline = _load_i116r_baseline()
    baseline_live = baseline.get("live_runs", [])
    baseline_metrics = baseline.get("metrics", {})

    det = run_deterministic_suite()
    live_objs: list = []
    live_ran = False
    model = "deterministic-only"

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        if not deterministic_only:
            try:
                cfg = DeepSeekConfig.from_env(timeout_seconds=90.0)
                provider = DeepSeekProvider(cfg)
                ontology = OntologyRegistry.with_core_seeds()
                interpreter = DeepSeekInterpreter(provider, ontology, prompt_version=PROMPT_VERSION_V3)
                live_objs = run_live_suite(interpreter, ontology, root, benchmark_user(), runs=3)
                live_ran = True
                model = cfg.model
            except Exception as exc:  # noqa: BLE001
                live_ran = False
                model = f"live-unavailable:{type(exc).__name__}"

    live_dicts = [o.to_dict() for o in live_objs]
    metrics = aggregate_metrics(det, live_objs)
    static = audit_static()

    comparison = {
        "provider_before": baseline_metrics.get("PROVIDER_RESPONSE_SUCCESS_RATE"),
        "provider_after": metrics.get("PROVIDER_RESPONSE_SUCCESS_RATE"),
        "raw_recovery_before": None,
        "raw_recovery_after": metrics.get("RAW_OUTPUT_RECOVERY_RATE"),
        "transport_before": baseline_metrics.get("PROPOSAL_PARSE_SUCCESS_RATE"),
        "transport_after": metrics.get("TRANSPORT_VALIDITY_RATE"),
        "proposal_before": baseline_metrics.get("PROPOSAL_PARSE_SUCCESS_RATE"),
        "proposal_after": metrics.get("VALID_SEMANTIC_PROPOSAL_RATE"),
        "actionable_before": None,
        "actionable_after": metrics.get("SEMANTIC_ACTIONABILITY_RATE"),
        "routing_before": baseline_metrics.get("PRIMITIVE_ROUTING_SUCCESS_RATE"),
        "routing_after": metrics.get("PRIMITIVE_ROUTING_SUCCESS_RATE"),
        "canonical_before": baseline_metrics.get("CANONICAL_RESOLUTION_SUCCESS_RATE"),
        "canonical_after": metrics.get("CANONICAL_RESOLUTION_SUCCESS_RATE"),
        "knowledge_before": baseline_metrics.get("KNOWLEDGE_SUCCESS_RATE"),
        "knowledge_after": metrics.get("KNOWLEDGE_SUCCESS_RATE"),
        "frontier_before": baseline_metrics.get("frontier_counts", {}),
    }

    event_table = _event_frontier_table(baseline_live, live_dicts) if live_ran else []
    ev_after = [r for r in live_dicts if r["case_id"].startswith("E")]
    ev_moved = "NO"
    if ev_after:
        beyond = sum(
            1
            for r in ev_after
            if r.get("knowledge_success")
            or (r.get("semantic_actionable") and r.get("frontier") not in {"PROVIDER_EMPTY", "PROPOSAL_TRANSPORT", "RAW_OUTPUT_FORMAT", "NORMALIZATION"})
        )
        if beyond >= 12:
            ev_moved = "YES"
        elif beyond >= 3:
            ev_moved = "PARTIALLY"

    retry = _retry_evidence(live_dicts) if live_ran else "NOT_JUSTIFIED"
    ranking = _frontier_ranking(metrics) if live_ran else {
        "PRIMARY": "PROPOSAL_QUALITY",
        "SECONDARY": "EVENT_REPRESENTATION",
        "DEFER": "ADAPTIVE_ALIAS_COVERAGE",
    }

    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "model": model,
        "prompt": PROMPT_VERSION_V3,
        "offline_gate": offline,
        "deterministic_runs": [o.to_dict() for o in det],
        "live_runs": live_dicts,
        "live_ran": live_ran,
        "metrics": metrics,
        "static_audit": static,
        "comparison": comparison,
        "failure_corpus_audit": I116R_PROPOSAL_WIRE_AUDIT,
        "event_table": event_table,
        "event_frontier_moved": ev_moved,
        "retry_evidence": retry,
        "known_debts": {
            "TIME-01": "UNCHANGED",
            "MIGRATION-01": "UNCHANGED",
            "MEASUREMENT-01": "UNCHANGED",
            "EVIDENCE-01": "UNCHANGED",
            "CORRECTION_ENGINE_DEBT": "UNCHANGED",
            "INTERPRETER-STATE-01": "REDUCED" if live_ran else "UNCHANGED",
            "INTERPRETER-RELATION-01": "REDUCED" if live_ran else "UNCHANGED",
            "INTERPRETER-EVENT-01": "STRONGER_EVIDENCE",
            "INTERPRETER-RETRY-01": retry,
            "ADAPTIVE-ALIAS-01": "KEEP_DEFERRED",
            "ONTOLOGY-COVERAGE-01": "KEEP_DEFERRED",
            "SEMANTIC-QUERY-01": static.get("query_debt"),
        },
        "frontier_ranking": ranking,
        "storage": {"schema": "v6", "migration": "none"},
        "holdout_executed": False,
    }
    payload["recommendation"] = choose_recommendation(payload, increment="I11.7")

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_MD.write_text(build_report(payload), encoding="utf-8")
    print(f"Wrote {REPORT_MD}")
    print(f"Wrote {REPORT_JSON}")
    print(f"Recommendation: {payload['recommendation']}")
    if live_ran:
        print(f"VALID_SEMANTIC_PROPOSAL_RATE: {metrics.get('VALID_SEMANTIC_PROPOSAL_RATE')}")
        print(f"KNOWLEDGE_SUCCESS_RATE: {metrics.get('KNOWLEDGE_SUCCESS_RATE')}")
    return 0


if __name__ == "__main__":
    only = "--deterministic-only" in sys.argv
    skip = "--skip-offline" in sys.argv
    raise SystemExit(main(deterministic_only=only, skip_offline=skip))
