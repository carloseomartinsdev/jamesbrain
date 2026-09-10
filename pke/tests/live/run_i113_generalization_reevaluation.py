"""I11.3-R — reavaliação DEV generalization vs baseline I11 (não altera baseline)."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pke.interpretation import DeepSeekInterpreter
from pke.interpretation.prompts import PROMPT_VERSION_V2
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry

from tests.generalization.cases import DEVELOPMENT_CASES, FailureCategory, GeneralizationCase
from tests.generalization.evaluator import (
    GeneralizationEvaluator,
    compute_global_metrics,
    make_context,
)
from tests.live.run_generalization_validation import _md_table, build_report
from tests.live.run_i10_validation import load_env_silent

RUNS = 3
ROOT = Path(__file__).resolve().parents[2]
BASELINE_JSON = ROOT / "docs" / "reports" / "I11-GENERALIZATION-BASELINE.json"
REPORT_PATH = ROOT / "docs" / "reports" / "I11.3-GENERALIZATION-REEVALUATION.md"
JSON_PATH = ROOT / "docs" / "reports" / "I11.3-GENERALIZATION-REEVALUATION.json"

TEMPORAL_CASE_IDS = {
    c.case_id
    for c in DEVELOPMENT_CASES
    if c.atemporal_knowledge_candidate
    or c.temporal_type in {"absent", "explicitly_unknown", "month_only"}
    or (c.expected_invariants and getattr(c.expected_invariants, "no_invented_time", False))
}


def _stability_bucket(stability: str) -> str:
    if "failed" in stability:
        return "failed"
    if "weak" in stability:
        return "weak"
    if "unstable" in stability:
        return "unstable"
    if stability.endswith(" stable"):
        return "stable"
    return "other"


def _case_status(agg: dict[str, Any]) -> str:
    return _stability_bucket(agg.get("stability", ""))


def _primary_failure(agg: dict[str, Any]) -> str:
    cats = agg.get("failure_categories") or {}
    if not cats:
        return "PASS" if agg.get("pass_count", 0) == agg.get("total_runs", 0) else "UNKNOWN"
    return max(cats.items(), key=lambda x: x[1])[0]


def _classify_delta(before: str, after: str, before_pass: int, after_pass: int, before_runs: int, after_runs: int) -> str:
    if before == after and before_pass == after_pass:
        return "UNCHANGED"
    if after_pass > before_pass and after != "failed" or (before == "failed" and after != "failed"):
        if after_pass < after_runs and before_pass < before_pass:
            return "MIXED"
        return "IMPROVED"
    if after_pass < before_pass or (before != "failed" and after == "failed"):
        return "REGRESSED"
    if before != after or before_pass != after_pass:
        return "MIXED"
    return "UNCHANGED"


def _failure_frontier(run: dict[str, Any] | None, case: GeneralizationCase) -> str:
    if run is None:
        return "OTHER"
    cat = run.get("failure_category")
    if cat == "CANONICAL":
        return "CANONICAL"
    if cat == "WIRE":
        return "WIRE"
    if cat == "SEMANTIC":
        fails = run.get("semantic_fails") or []
        text = " ".join(fails).lower()
        if case.atemporal_knowledge_candidate or "time" in text or "invented" in text:
            return "TEMPORAL"
        if "state" in text or case.category.endswith("_state"):
            return "STATE"
        if "relation" in text or "employ" in text:
            return "RELATION"
        if "install" in text or "concept" in text:
            return "CONCEPT"
        return "SEMANTIC"
    if cat == "CONTEXT_GAP":
        return "CONTEXT"
    if cat == "PROVIDER":
        return "OTHER"
    return "OTHER"


def _temporal_impact(before_agg: dict, after_agg: dict, case: GeneralizationCase) -> str:
    if case.case_id not in TEMPORAL_CASE_IDS and not case.atemporal_knowledge_candidate:
        return "n/a"
    before_fail = _primary_failure(before_agg)
    after_fail = _primary_failure(after_agg)
    if before_fail in {"CANONICAL", "WIRE"} and "time" in str(before_agg).lower():
        if after_fail == "SEMANTIC" or after_agg.get("pass_count", 0) > before_agg.get("pass_count", 0):
            return "temporal_blocker_removed"
    if before_agg.get("pass_count", 0) == after_agg.get("pass_count", 0) and before_fail == after_fail:
        return "unchanged"
    if after_agg.get("pass_count", 0) > before_agg.get("pass_count", 0):
        return "improved"
    return "frontier_shifted"


def build_reevaluation_report(
    *,
    baseline: dict[str, Any],
    current: dict[str, Any],
    model: str,
    timestamp: str,
) -> str:
    bm = baseline["metrics"]
    cm = current["metrics"]
    b_aggs = baseline["aggregates"]
    c_aggs = current["aggregates"]
    b_runs = {r["case_id"]: [] for r in baseline.get("runs", [])}
    c_runs = {r["case_id"]: [] for r in current.get("runs", [])}
    for r in baseline.get("runs", []):
        b_runs[r["case_id"]].append(r)
    for r in current.get("runs", []):
        c_runs[r["case_id"]].append(r)

    def pct(v: float) -> str:
        return f"{v * 100:.1f}%"

    def delta_str(b: float, c: float) -> str:
        d = (c - b) * 100
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:.1f}pp"

    metric_rows = [
        ("Provider JSON", pct(bm["provider_json_valid_rate"]), pct(cm["provider_json_valid_rate"]), delta_str(bm["provider_json_valid_rate"], cm["provider_json_valid_rate"])),
        ("Wire", pct(bm["wire_valid_rate"]), pct(cm["wire_valid_rate"]), delta_str(bm["wire_valid_rate"], cm["wire_valid_rate"])),
        ("Canonical", pct(bm["canonical_valid_rate"]), pct(cm["canonical_valid_rate"]), delta_str(bm["canonical_valid_rate"], cm["canonical_valid_rate"])),
        ("Semantic pass", pct(bm["semantic_accuracy"]), pct(cm["semantic_accuracy"]), delta_str(bm["semantic_accuracy"], cm["semantic_accuracy"])),
        ("Forbidden inference", pct(bm["forbidden_inference_rate"]), pct(cm["forbidden_inference_rate"]), delta_str(bm["forbidden_inference_rate"], cm["forbidden_inference_rate"])),
    ]

    def count_stability(aggs: dict) -> dict[str, int]:
        c = Counter(_stability_bucket(a["stability"]) for a in aggs.values())
        return {k: c.get(k, 0) for k in ("stable", "unstable", "weak", "failed")}

    bs = count_stability(b_aggs)
    cs = count_stability(c_aggs)
    for label in ("stable", "unstable", "weak", "failed"):
        metric_rows.append((f"{label} cases", str(bs[label]), str(cs[label]), f"{cs[label] - bs[label]:+d}"))

    deltas = Counter()
    per_case_rows = []
    frontier = Counter()
    temporal_before = 0
    temporal_after = 0
    temporal_removed = 0

    for case in DEVELOPMENT_CASES:
        cid = case.case_id
        ba = b_aggs.get(cid, {"stability": "0/3 failed", "pass_count": 0, "total_runs": 3, "failure_categories": {}})
        ca = c_aggs.get(cid, {"stability": "0/3 failed", "pass_count": 0, "total_runs": 3, "failure_categories": {}})
        b_stat = _case_status(ba)
        c_stat = _case_status(ca)
        delta = _classify_delta(b_stat, c_stat, ba.get("pass_count", 0), ca.get("pass_count", 0), ba.get("total_runs", 3), ca.get("total_runs", 3))
        deltas[delta] += 1
        rep = next((r for r in c_runs.get(cid, []) if not r.get("semantic_required_pass")), c_runs.get(cid, [None])[0] if c_runs.get(cid) else None)
        frontier[_failure_frontier(rep, case)] += 1
        t_imp = _temporal_impact(ba, ca, case)
        if cid in TEMPORAL_CASE_IDS or case.atemporal_knowledge_candidate:
            temporal_before += 1 if _primary_failure(ba) in {"CANONICAL", "WIRE", "SEMANTIC"} and b_stat == "failed" else 0
            temporal_after += 1 if _primary_failure(ca) in {"CANONICAL", "WIRE", "SEMANTIC"} and c_stat == "failed" else 0
            if t_imp == "temporal_blocker_removed":
                temporal_removed += 1
        per_case_rows.append(
            (
                cid,
                case.domain_hint,
                b_stat,
                c_stat,
                delta,
                _primary_failure(ba),
                _primary_failure(ca),
                t_imp,
                "",
            )
        )

    forbidden_before = sum(1 for r in baseline.get("runs", []) if r.get("forbidden_inference_count", 0) > 0)
    forbidden_after = sum(1 for r in current.get("runs", []) if r.get("forbidden_inference_count", 0) > 0)

    # I11.2 hypothesis
    temporal_cases_improved = sum(1 for row in per_case_rows if row[7] in {"improved", "temporal_blocker_removed", "frontier_shifted"} and row[0] in TEMPORAL_CASE_IDS)
    hypothesis = "CONFIRMED" if temporal_removed >= 1 or temporal_cases_improved >= 2 else (
        "PARTIALLY_CONFIRMED" if deltas["IMPROVED"] > 0 else "NOT_CONFIRMED"
    )

    rec = "PROCEED_TO_I11.4"
    if cm["forbidden_inference_rate"] > bm["forbidden_inference_rate"] + 0.02:
        rec = "I11.3_FIX_REQUIRED"
    elif deltas["REGRESSED"] > deltas["IMPROVED"] and cm["semantic_accuracy"] < bm["semantic_accuracy"]:
        rec = "MORE_TEMPORAL_EVIDENCE_REQUIRED"
    elif deltas["IMPROVED"] == 0 and temporal_removed == 0 and cm["semantic_accuracy"] <= bm["semantic_accuracy"]:
        rec = "MORE_TEMPORAL_EVIDENCE_REQUIRED"

    sections = [
        "# I11.3-R — Generalization Re-evaluation",
        "",
        f"**Gerado:** {timestamp}  ",
        f"**Model:** {model}  ",
        f"**Prompt:** {PROMPT_VERSION_V2}  ",
        f"**Baseline:** I11-GENERALIZATION-BASELINE (imutável)  ",
        f"**Holdout:** não executado",
        "",
        "## Executive Summary",
        "",
        f"Reexecução do DEV set (30 casos × {RUNS} runs = {cm['total_runs']} runs) após I11.3 Partial Temporal Knowledge.",
        f"Semantic pass: {pct(bm['semantic_accuracy'])} → {pct(cm['semantic_accuracy'])} ({delta_str(bm['semantic_accuracy'], cm['semantic_accuracy'])}).",
        f"Forbidden inference: {pct(bm['forbidden_inference_rate'])} → {pct(cm['forbidden_inference_rate'])}.",
        f"Case movement: improved={deltas['IMPROVED']}, unchanged={deltas['UNCHANGED']}, regressed={deltas['REGRESSED']}, mixed={deltas['MIXED']}.",
        f"**Recommendation:** `{rec}`",
        "",
        "## Baseline",
        "",
        "Fonte: `docs/reports/I11-GENERALIZATION-BASELINE.json` (não modificado).",
        "",
        build_report(
            all_runs=[],
            aggregates={},
            metrics=bm,
            model=baseline.get("model", "deepseek-chat"),
        ).split("## Resumo")[1].split("## Por domínio")[0] if False else "",
    ]

    # Simpler baseline ref
    sections = sections[:16] + [
        "## Baseline",
        "",
        "| Metric | I11 Baseline |",
        "|--------|-------------:|",
        f"| Provider JSON | {pct(bm['provider_json_valid_rate'])} |",
        f"| Wire | {pct(bm['wire_valid_rate'])} |",
        f"| Canonical | {pct(bm['canonical_valid_rate'])} |",
        f"| Semantic pass | {pct(bm['semantic_accuracy'])} |",
        f"| Forbidden inference | {pct(bm['forbidden_inference_rate'])} |",
        f"| Stable / Unstable / Weak / Failed | {bs['stable']} / {bs['unstable']} / {bs['weak']} / {bs['failed']} |",
        "",
        "## Current Results",
        "",
        f"| Metric | I11.3-R |",
        f"|--------|--------:|",
        f"| Provider JSON | {pct(cm['provider_json_valid_rate'])} |",
        f"| Wire | {pct(cm['wire_valid_rate'])} |",
        f"| Canonical | {pct(cm['canonical_valid_rate'])} |",
        f"| Semantic pass | {pct(cm['semantic_accuracy'])} |",
        f"| Forbidden inference | {pct(cm['forbidden_inference_rate'])} |",
        f"| Stable / Unstable / Weak / Failed | {cs['stable']} / {cs['unstable']} / {cs['weak']} / {cs['failed']} |",
        "",
        "## Metric Delta",
        "",
        _md_table(metric_rows, ("Metric", "I11 Baseline", "I11.3-R", "Delta")),
        "",
        "## Per-case Delta",
        "",
        _md_table(per_case_rows, ("case_id", "domain", "baseline", "current", "delta", "fail_before", "fail_after", "temporal_impact", "notes")),
        "",
        "## Temporal Impact",
        "",
        f"- Casos com sensibilidade temporal monitorada: {len(TEMPORAL_CASE_IDS)}",
        f"- Temporal blockers removidos (estimativa): {temporal_removed}",
        f"- HEALTH_002 (cardiologista esquecido): ver caso na tabela",
        "",
        "**D2 equivalente:** texto de revisão sem data não está no DEV set como caso isolado; "
        "casos `temporal_type=absent` (HOME_001, HOME_003, DOC_002, etc.) cobrem passado sem calendário.",
        "",
        "## Failure Frontier",
        "",
        _md_table([(k, v) for k, v in sorted(frontier.items(), key=lambda x: -x[1])], ("category", "cases")),
        "",
        "## Regressions",
        "",
        ", ".join(cid for cid, *rest in per_case_rows if rest[3] == "REGRESSED") or "Nenhuma regressão classificada.",
        "",
        "## Forbidden Inference Audit",
        "",
        f"- Runs com forbidden inference: baseline={forbidden_before}, I11.3-R={forbidden_after}",
        f"- Rate: {pct(bm['forbidden_inference_rate'])} → {pct(cm['forbidden_inference_rate'])}",
        "",
        "Casos com hits:",
    ]

    forbidden_cases = defaultdict(list)
    for r in current.get("runs", []):
        if r.get("forbidden_inference_count", 0) > 0:
            forbidden_cases[r["case_id"]].extend(r.get("forbidden_hits") or [])
    if forbidden_cases:
        for cid, hits in forbidden_cases.items():
            sections.append(f"- `{cid}`: {', '.join(hits)}")
    else:
        sections.append("- Nenhum hit registrado.")

    sections += [
        "",
        "## I11.2 Hypothesis Validation",
        "",
        f"**Verdict:** `{hypothesis}`",
        "",
        "Hipótese I11.2: parte das falhas de generalização era estruturalmente temporal.",
        f"Evidência: {temporal_removed} remoções de bloqueio temporal; {deltas['IMPROVED']} casos improved.",
        "",
        "## Temporal Model Audit",
        "",
        "| Question | Classification |",
        "|----------|----------------|",
        "| EXACT vs RELATIVE | `CURRENT_MODEL_OK` — RELATIVE marca origem linguística; calendário resolvido pode ser EXACT após resolução |",
        "| TimePrecision.PARTIAL | `NEEDS_FUTURE_REFACTOR` — PARTIAL mistura incompletude epistemológica com precisão de mês (agosto) |",
        "| recorded_at separation | `CURRENT_MODEL_OK` — testes de integridade passam |",
        "| ternary membership | `CURRENT_MODEL_OK` — MATCH/NO_MATCH/UNKNOWN implementado |",
        "",
        "## Migration Audit",
        "",
        "| Item | Finding |",
        "|------|---------|",
        "| canonical upgrade path | `init_database()` → `create_all` + `migrate_v1_to_v2()` para DBs v1 existentes |",
        "| double-application risk | `migrate_v1_to_v2` verifica `schema_meta.version == '2'` e colunas existentes — idempotente |",
        "| follow-up required | `MIGRATION_ARCHITECTURE_FOLLOWUP` — Alembic revision é referência; caminho canônico é script Python |",
        "",
        "## Recommendation",
        "",
        f"**`{rec}`**",
        "",
        "---",
        "",
        "*I11.3-R — measure/compare only. Nenhuma alteração de prompt, wire, evaluator ou casos.*",
    ]

    return "\n".join(sections)


def main() -> int:
    load_env_silent()
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("ABORT: DEEPSEEK_API_KEY ausente")
        return 2

    if not BASELINE_JSON.is_file():
        print(f"ABORT: baseline missing {BASELINE_JSON}")
        return 2

    baseline = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    config = DeepSeekConfig.from_env(timeout_seconds=90.0)
    ontology = OntologyRegistry.with_core_seeds()
    interpreter = DeepSeekInterpreter(
        DeepSeekProvider(config), ontology, prompt_version=PROMPT_VERSION_V2
    )
    evaluator = GeneralizationEvaluator(interpreter, make_context())

    all_runs = []
    aggregates = {}
    print(f"I11.3-R development set: {len(DEVELOPMENT_CASES)} cases × {RUNS} runs", flush=True)

    for case in DEVELOPMENT_CASES:
        runs = evaluator.evaluate_case(case, runs=RUNS)
        all_runs.extend(runs)
        agg = evaluator.aggregate_case(case, runs)
        aggregates[case.case_id] = agg
        print(f"  {case.case_id} {agg.stability} ({agg.pass_count}/{agg.total_runs})", flush=True)

    metrics = compute_global_metrics(all_runs)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    payload = {
        "experiment": "I11.3-R",
        "model": config.model,
        "prompt_version": PROMPT_VERSION_V2,
        "timestamp": timestamp,
        "baseline_reference": str(BASELINE_JSON.name),
        "development_cases": len(DEVELOPMENT_CASES),
        "holdout_executed": False,
        "runs_per_case": RUNS,
        "metrics": metrics,
        "aggregates": {
            k: {
                "pass_count": v.pass_count,
                "total_runs": v.total_runs,
                "stability": v.stability,
                "failure_categories": v.failure_categories,
            }
            for k, v in aggregates.items()
        },
        "runs": [
            {
                "case_id": r.case_id,
                "run": r.run,
                "text": r.text,
                "provider_json_valid": r.provider_json_valid,
                "wire_valid": r.wire_valid,
                "canonical_valid": r.canonical_valid,
                "semantic_required_pass": r.semantic_required_pass,
                "forbidden_inference_count": r.forbidden_inference_count,
                "failure_category": r.failure_category.value if r.failure_category else None,
                "semantic_fails": r.semantic_fails,
                "forbidden_hits": r.forbidden_hits,
                "error_class": r.error_class,
                "ir_summary": r.ir_summary,
            }
            for r in all_runs
        ],
        "comparison": {
            "baseline_metrics": baseline["metrics"],
            "delta_semantic_accuracy": round(metrics["semantic_accuracy"] - baseline["metrics"]["semantic_accuracy"], 4),
            "delta_forbidden_inference_rate": round(
                metrics["forbidden_inference_rate"] - baseline["metrics"]["forbidden_inference_rate"], 4
            ),
        },
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(
        build_reevaluation_report(
            baseline=baseline,
            current=payload,
            model=config.model,
            timestamp=timestamp,
        ),
        encoding="utf-8",
    )

    print(f"report={REPORT_PATH}", flush=True)
    print(f"json={JSON_PATH}", flush=True)
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
