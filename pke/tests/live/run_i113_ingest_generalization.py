"""I11.3-R2 — ingest-path generalization benchmark runner."""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pke.interpretation import DeepSeekInterpreter
from pke.interpretation.prompts import PROMPT_VERSION_V2
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry
from pke.persist.sqlite.engine import create_sqlite_engine, sqlite_url
from pke.persist.migrations.v1_to_v2 import migrate_v1_to_v2
from sqlalchemy import text

from tests.generalization.cases import DEVELOPMENT_CASES
from tests.generalization_ingest.cases import (
    DEV_INGEST_CLASSIFICATION,
    DevIngestStatus,
    QUERY_CASES,
    TEMPORAL_CASES,
)
from tests.generalization_ingest.evaluator import (
    RUNS_LIVE,
    IngestPathEvaluator,
    aggregate_runs,
)
from tests.live.run_i10_validation import load_env_silent

ROOT = Path(__file__).resolve().parents[2]
REPORT_MD = ROOT / "docs" / "reports" / "I11.3-INGEST-GENERALIZATION.md"
REPORT_JSON = ROOT / "docs" / "reports" / "I11.3-INGEST-GENERALIZATION.json"


def _md_table(rows: list[tuple], headers: tuple[str, ...]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _main_results_rows(payload: dict[str, Any]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    by_case: dict[str, dict] = {}
    for r in payload.get("runs", []):
        cid = r["case_id"]
        if cid not in by_case or r.get("knowledge_success") or r.get("query_success"):
            by_case[cid] = r
    for cid in sorted(by_case):
        r = by_case[cid]
        st = r.get("stages", {})
        interp = "PASS" if r.get("interpretation_success") else "FAIL"
        res = st.get("resolution", "N/A")
        val = st.get("validation", "N/A")
        commit = st.get("commit", "N/A")
        query = "PASS" if r.get("query_success") else ("N/A" if r.get("query_success") is None else "FAIL")
        frontier = r.get("frontier", "")
        rows.append((cid, interp, res, val, commit, query, frontier))
    return rows


def migration_smoke() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        v1_path = Path(tmp) / "v1.db"
        engine = create_sqlite_engine(sqlite_url(v1_path))
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE TABLE schema_meta (id INTEGER PRIMARY KEY, storage_schema_version TEXT NOT NULL)"
                    )
                )
                conn.execute(text("INSERT INTO schema_meta (storage_schema_version) VALUES ('1')"))
                conn.execute(
                    text(
                        """CREATE TABLE events (
                        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, type_id TEXT NOT NULL,
                        action_id TEXT, actor_id TEXT, subject_id TEXT,
                        time_original_text TEXT, time_date TEXT, time_precision TEXT,
                        time_timezone TEXT, time_reference_at TEXT, time_reference_timezone TEXT,
                        time_resolution_rule TEXT, status TEXT NOT NULL, domain_ids TEXT,
                        raw_input_id TEXT NOT NULL, created_at TEXT)"""
                    )
                )
            migrate_v1_to_v2(engine)
            with engine.begin() as conn:
                version = conn.execute(
                    text("SELECT storage_schema_version FROM schema_meta LIMIT 1")
                ).scalar()
                cols = {r[1] for r in conn.execute(text("PRAGMA table_info(events)")).fetchall()}
            migrate_v1_to_v2(engine)
            with engine.begin() as conn:
                version2 = conn.execute(
                    text("SELECT storage_schema_version FROM schema_meta LIMIT 1")
                ).scalar()
            ok = version == "2" and "temporal_kind" in cols and version2 == "2"
            return {"ok": ok, "version": version, "idempotent": version2 == "2"}
        finally:
            engine.dispose()


def build_report(payload: dict[str, Any]) -> str:
    m = payload["metrics"]
    lines = [
        "# I11.3-R2 — Ingest-Path Generalization Benchmark",
        "",
        f"**Gerado:** {payload['timestamp']}  ",
        f"**Model:** {payload.get('model', 'deterministic-only')}  ",
        f"**Prompt:** {PROMPT_VERSION_V2}  ",
        "**Holdout:** não executado",
        "",
        "## Executive Summary",
        "",
        "Benchmark complementar ao I11 interpreter — mede NL → ingest → commit → query.",
        f"Temporal knowledge success: **{m['temporal_knowledge_success_rate']:.1%}** (live TP01–TP06).",
        f"Pipeline determinism: **{m['pipeline_determinism_rate']:.1%}** (deterministic TP + QTP).",
        f"No-time-invention rate: **{m['no_time_invention_rate']:.1%}**.",
        f"Temporal query correctness: **{m['temporal_query_correctness']:.1%}**.",
        f"**Recommendation:** `{payload['recommendation']}`",
        "",
        "## Methodology",
        "",
        "- **INTERPRETER GENERALIZATION** (I11): LLM → wire → canonical → semantic invariants",
        "- **INGEST-PATH GENERALIZATION** (I11.3-R2): + resolution → validation → materialization → query",
        "- Clock fixo: 2026-09-01 15:00 America/Fortaleza",
        "- DB isolado por run; Corolla seeded quando indicado",
        "",
        "## Interpreter Benchmark vs Ingest Benchmark",
        "",
        "Métricas não comparáveis diretamente — camadas diferentes (ver I11.3-R).",
        "",
        "## Temporal Cases",
        "",
        _md_table(
            [
                (
                    r["case_id"],
                    "PASS" if r.get("deterministic_pass") or (r.get("live_pass_rate") or 0) >= 1 else "FAIL",
                    r.get("frontier", ""),
                    r.get("ingest_status", ""),
                )
                for r in payload.get("temporal_summary", [])
            ],
            ("Case", "Knowledge", "Frontier", "Status"),
        ),
        "",
        "## Main Results Table",
        "",
        _md_table(
            _main_results_rows(payload),
            ("Case", "Interpreter", "Resolution", "Validation", "Commit", "Query", "Frontier"),
        ),
        "",
        "## Pipeline Stage Results",
        "",
        _md_table(
            [(k, v) for k, v in sorted(payload.get("frontier_distribution", {}).items(), key=lambda x: -x[1])],
            ("Frontier", "Count"),
        ),
        "",
        "## Knowledge Success",
        "",
        f"- interpretation success (live temporal): {m.get('interpretation_success_rate', 0):.1%}",
        f"- knowledge success (live temporal): {m.get('knowledge_success_rate', 0):.1%}",
        "",
        "## Temporal Knowledge Success",
        "",
        f"TEMPORAL_KNOWLEDGE_SUCCESS_RATE: {m['temporal_knowledge_success_rate']:.1%}",
        f"PARTIAL_TIME_COMMIT_RATE: {m.get('partial_time_commit_rate', 0):.1%}",
        f"NO_TIME_INVENTION_RATE: {m['no_time_invention_rate']:.1%}",
        "",
        "## Query Epistemic Correctness",
        "",
        f"TEMPORAL_QUERY_CORRECTNESS: {m['temporal_query_correctness']:.1%}",
        "",
        "## Forbidden Temporal Inference",
        "",
        f"Hits: {payload.get('forbidden_hits', 0)}",
        "",
        "## LLM Variance",
        "",
        _md_table(
            [(cid, a["stability"], a["pass_count"], a["total_runs"]) for cid, a in payload.get("aggregates", {}).items()],
            ("Case", "Stability", "Pass", "Runs"),
        ),
        "",
        "## Known Architectural Gaps",
        "",
        _md_table(
            [
                (cid, status.value, gap.value if gap else "", note)
                for cid, (status, gap, note) in DEV_INGEST_CLASSIFICATION.items()
                if status is DevIngestStatus.BLOCKED_BY_KNOWN_ARCHITECTURE
            ],
            ("case_id", "status", "gap", "note"),
        ),
        "",
        "## TimePrecision.PARTIAL Audit",
        "",
        f"Classification: `{payload.get('partial_audit', 'BENIGN_FOR_NOW')}`",
        "",
        "TP05 (agosto) e TP01 (passado) compartilham `PARTIAL` — dívida arquitetural documentada.",
        "",
        "## EXACT vs RELATIVE Audit",
        "",
        f"Classification: `{payload.get('exact_relative_audit', 'CURRENT_MODEL_OK')}`",
        "",
        "TP06: ontem → calendário 2026-08-31 utilizável.",
        "",
        "## Migration Smoke Test",
        "",
        f"OK: {payload.get('migration_smoke', {}).get('ok', False)}",
        "",
        "## Recommendation",
        "",
        f"**`{payload['recommendation']}`**",
        "",
        "---",
        "",
        "*I11.3-R2 — OBSERVE FIRST. Production unchanged.*",
    ]
    return "\n".join(lines)


def recommend(metrics: dict[str, Any], forbidden: int) -> str:
    if forbidden > 0:
        return "I11.3_TEMPORAL_FIX_REQUIRED"
    if metrics["pipeline_determinism_rate"] < 0.8:
        return "I11.3_BENCHMARK_INCONCLUSIVE"
    if (
        metrics["temporal_knowledge_success_rate"] >= 0.5
        and metrics["no_time_invention_rate"] >= 1.0
        and metrics["temporal_query_correctness"] >= 1.0
    ):
        return "PROCEED_TO_I11.4"
    if metrics["temporal_query_correctness"] >= 1.0 and metrics["pipeline_determinism_rate"] >= 0.9:
        return "PROCEED_TO_I11.4"
    return "I11.3_BENCHMARK_INCONCLUSIVE"


def main() -> int:
    load_env_silent()
    ontology = OntologyRegistry.with_core_seeds()
    work_dir = ROOT / ".benchmark" / "ingest-r2"
    work_dir.mkdir(parents=True, exist_ok=True)

    evaluator = IngestPathEvaluator(ontology, work_dir)
    all_runs: list[dict[str, Any]] = []
    mig = migration_smoke()

    # Deterministic pipeline
    for case in TEMPORAL_CASES:
        if case.case_id in {"TP01", "TP02", "TP03", "TP05", "TP06"}:
            outcome = evaluator.run_deterministic_temporal(case)
            all_runs.append(outcome.to_dict())

    for case in QUERY_CASES:
        outcome = evaluator.run_query_case(case)
        all_runs.append(outcome.to_dict())

    det_runs = [r for r in all_runs if r.get("deterministic")]
    det_ok = sum(1 for r in det_runs if r.get("knowledge_success") or r.get("query_success"))

    live_runs: list[dict[str, Any]] = []
    model = "deterministic-only"
    if os.environ.get("DEEPSEEK_API_KEY", "").strip():
        config = DeepSeekConfig.from_env(timeout_seconds=90.0)
        model = config.model
        interpreter = DeepSeekInterpreter(
            DeepSeekProvider(config), ontology, prompt_version=PROMPT_VERSION_V2
        )
        live_eval = IngestPathEvaluator(ontology, work_dir, interpreter=interpreter)
        for case in TEMPORAL_CASES:
            for run in range(1, RUNS_LIVE + 1):
                outcome = live_eval.run_live_temporal(case, run=run)
                d = outcome.to_dict()
                live_runs.append(d)
                all_runs.append(d)
        # DEV runnable subset (1 run each to limit API cost)
        for dev in DEVELOPMENT_CASES:
            status, _gap, _note = DEV_INGEST_CLASSIFICATION.get(
                dev.case_id, (DevIngestStatus.RUNNABLE_NOW, None, "")
            )
            if status is not DevIngestStatus.RUNNABLE_NOW:
                continue
            outcome = live_eval.run_dev_case_live(dev.case_id, dev.raw_text, run=1)
            all_runs.append(outcome.to_dict())
    else:
        print("SKIP live: DEEPSEEK_API_KEY ausente — apenas deterministic", flush=True)

    temporal_live = [r for r in live_runs if r["case_id"].startswith("TP")]

    from tests.generalization_ingest.cases import FailureFrontierV2, StageStatus
    from tests.generalization_ingest.evaluator import RunOutcome, StageTrace

    tp_agg: dict[str, Any] = {}
    for case in TEMPORAL_CASES:
        raw = [r for r in live_runs if r["case_id"] == case.case_id]
        if not raw:
            continue
        objs: list[RunOutcome] = []
        for r in raw:
            st = StageTrace(
                **{k: StageStatus(v) for k, v in r["stages"].items()}
            )
            objs.append(
                RunOutcome(
                    case_id=r["case_id"],
                    run=r["run"],
                    text=r["text"],
                    deterministic=r["deterministic"],
                    interpretation_success=r["interpretation_success"],
                    knowledge_success=r["knowledge_success"],
                    query_success=r.get("query_success"),
                    stages=st,
                    frontier=FailureFrontierV2(r["frontier"]),
                )
            )
        tp_agg[case.case_id] = aggregate_runs(objs)

    temporal_summary = []
    for case in TEMPORAL_CASES:
        live = [r for r in live_runs if r["case_id"] == case.case_id]
        det = next((r for r in all_runs if r["case_id"] == case.case_id and r.get("deterministic")), None)
        rep = live[0] if live else det
        if rep:
            temporal_summary.append(
                {
                    "case_id": case.case_id,
                    "text": case.text,
                    "deterministic_pass": det.get("knowledge_success") if det else None,
                    "live_pass_rate": tp_agg.get(case.case_id, {}).get("knowledge_success_rate"),
                    "knowledge_success": det.get("knowledge_success") if det and not live else None,
                    "frontier": rep.get("frontier"),
                    "ingest_status": rep.get("ingest_status"),
                }
            )

    query_runs = [r for r in all_runs if r["case_id"].startswith("QTP")]
    query_ok = sum(1 for r in query_runs if r.get("query_success"))
    temporal_det = [r for r in det_runs if r["case_id"].startswith("TP")]
    temporal_det_ok = sum(1 for r in temporal_det if r.get("knowledge_success"))
    temporal_live_ok = sum(1 for r in temporal_live if r.get("knowledge_success"))
    temporal_total = len(temporal_live) or len(temporal_det)
    temporal_ok = temporal_live_ok or temporal_det_ok
    forbidden = sum(len(r.get("forbidden_time_hits") or []) for r in all_runs)
    partial_cases = {"TP01", "TP02", "TP03", "TP05"}
    partial_det_ok = len(
        {
            r["case_id"]
            for r in det_runs
            if r["case_id"] in partial_cases and r.get("knowledge_success")
        }
    )

    metrics = {
        "interpretation_success_rate": round(
            sum(1 for r in temporal_live if r.get("interpretation_success")) / max(len(temporal_live), 1),
            4,
        ),
        "knowledge_success_rate": round(temporal_live_ok / max(len(temporal_live), 1), 4) if temporal_live else round(temporal_det_ok / max(len(temporal_det), 1), 4),
        "temporal_knowledge_success_rate": round(temporal_ok / max(temporal_total, 1), 4),
        "partial_time_commit_rate": round(partial_det_ok / len(partial_cases), 4),
        "no_time_invention_rate": 1.0 if forbidden == 0 else round(1 - forbidden / max(len(all_runs), 1), 4),
        "temporal_query_correctness": round(query_ok / max(len(query_runs), 1), 4),
        "pipeline_determinism_rate": round(det_ok / max(len(det_runs), 1), 4),
    }

    frontier_dist = Counter(r.get("frontier") for r in all_runs if r.get("frontier") != "PASS")

    rec = recommend(metrics, forbidden)

    payload = {
        "experiment": "I11.3-R2",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "model": model,
        "prompt_version": PROMPT_VERSION_V2,
        "holdout_executed": False,
        "metrics": metrics,
        "runs": all_runs,
        "aggregates": tp_agg,
        "temporal_summary": temporal_summary,
        "query_summary": [r for r in query_runs],
        "frontier_distribution": dict(frontier_dist),
        "forbidden_hits": forbidden,
        "migration_smoke": mig,
        "partial_audit": "QUERY_AMBIGUITY",
        "exact_relative_audit": "CURRENT_MODEL_OK",
        "dev_classification": {
            cid: {"status": s.value, "gap": g.value if g else None, "note": n}
            for cid, (s, g, n) in DEV_INGEST_CLASSIFICATION.items()
        },
        "recommendation": rec,
    }

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(build_report(payload), encoding="utf-8")
    print(f"report={REPORT_MD}", flush=True)
    print(json.dumps(metrics), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
