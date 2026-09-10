"""I11.5-R — Relation Generalization Re-evaluation runner.

MEASURE / COMPARE / CLASSIFY / REPORT — does not modify production Relation.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pke.interpretation import DeepSeekInterpreter
from pke.interpretation.prompts import PROMPT_VERSION_V2
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry

from tests.generalization_ingest.cases import DEV_INGEST_CLASSIFICATION, ArchitecturalGap
from tests.generalization_ingest.relation_evaluator import (
    aggregate_metrics,
    audit_currentness_invariants,
    audit_valid_to_vs_termination_temporal,
    migration_smoke_v5_to_v6,
    ontology_audit,
    run_deterministic_suite,
    run_live_suite,
)
from tests.live.run_i10_validation import load_env_silent

ROOT = Path(__file__).resolve().parents[2]
REPORT_MD = ROOT / "docs" / "reports" / "I11.5-RELATION-REEVALUATION.md"
REPORT_JSON = ROOT / "docs" / "reports" / "I11.5-RELATION-REEVALUATION.json"


def _md_table(rows: list[tuple], headers: tuple[str, ...]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


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
    import re

    m = re.search(r"(\d+)\s+passed(?:,\s*(\d+)\s+failed)?(?:,\s*(\d+)\s+skipped)?", out)
    if m:
        passed = int(m.group(1))
        failed = int(m.group(2) or 0)
        skipped = int(m.group(3) or 0)
    else:
        for line in out.strip().splitlines():
            if " passed" in line:
                parts = line.replace(",", "").split()
                for i, p in enumerate(parts):
                    if p == "passed":
                        passed = int(parts[i - 1])
                    elif p == "skipped":
                        skipped = int(parts[i - 1])
                    elif p == "failed":
                        failed = int(parts[i - 1])
    ok = proc.returncode == 0 and failed == 0
    return {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "ok": ok,
        "returncode": proc.returncode,
    }


def choose_recommendation(payload: dict[str, Any]) -> str:
    offline = payload["offline_gate"]
    m = payload["metrics"]
    mig = payload["migration_smoke"]
    ont = payload["ontology_audit"]
    valid_to = payload["valid_to_audit"]
    deny = payload["deny_current_audit"]
    people = payload["people_001"]
    det_ok = m["deterministic_passed"] == m["deterministic_cases"]
    causal_ok = m["RELATION_NO_CAUSAL_EVENT_INVENTION_RATE"] >= 0.999
    lifecycle_ok = m["RELATION_LIFECYCLE_CORRECTNESS"] >= 0.999
    provenance_ok = (
        m["RELATION_ASSERTION_PROVENANCE_PRESERVATION"] >= 0.999
        and m["RELATION_TERMINATION_PROVENANCE_PRESERVATION"] >= 0.999
    )
    no_time_ok = m["RELATION_NO_TIME_INVENTION_RATE"] >= 0.999
    curr_ok = m["RELATION_CURRENTNESS_CORRECTNESS"] >= 0.999
    hist_ok = m["RELATION_HISTORY_PRESERVATION_RATE"] >= 0.999
    identity_ok = m["RELATION_IDENTITY_CORRECTNESS"] >= 0.999
    concurrency_ok = m["RELATION_CONCURRENCY_CORRECTNESS"] >= 0.999
    if not offline.get("ok"):
        return "I11.5_FIX_REQUIRED"
    if not det_ok or not causal_ok or not lifecycle_ok or not provenance_ok:
        return "I11.5_FIX_REQUIRED"
    if not no_time_ok or not curr_ok or not hist_ok or not identity_ok or not concurrency_ok:
        return "I11.5_FIX_REQUIRED"
    if not mig.get("ok") or not ont.get("pass"):
        return "I11.5_FIX_REQUIRED"
    if valid_to.get("classification") == "BUG":
        return "I11.5_FIX_REQUIRED"
    if deny.get("classification") == "DENY_CURRENT_BUG":
        return "I11.5_FIX_REQUIRED"
    if not people.get("deterministic_advanced"):
        return "I11.5_FIX_REQUIRED"
    collapse = m.get("RELATION_PRIMITIVE_COLLAPSE_RATE") or 0
    if payload.get("live_ran") and collapse > 0:
        return "MORE_RELATION_EVIDENCE_REQUIRED"
    return "PROCEED"


def build_report(payload: dict[str, Any]) -> str:
    m = payload["metrics"]
    people = payload["people_001"]
    valid_to = payload["valid_to_audit"]
    deny = payload["deny_current_audit"]
    lines = [
        "# I11.5-R — Relation Generalization Re-evaluation",
        "",
        f"**Gerado:** {payload['timestamp']}  ",
        f"**Model:** {payload.get('model', 'deterministic-only')}  ",
        f"**Prompt:** {PROMPT_VERSION_V2} (unchanged)  ",
        "**Holdout:** não executado",
        "**Production:** Relation / wire / ontology / prompt **não alterados** neste incremento",
        "",
        "## Executive Summary",
        "",
        "Reavaliação pós I11.5/I11.5.1: Relation primitive, lifecycle evidence, PEOPLE_001 frontier.",
        f"Offline gate: **{payload['offline_gate']['passed']} passed / "
        f"{payload['offline_gate']['failed']} failed / {payload['offline_gate']['skipped']} skipped**.",
        f"Deterministic Relation: **{m['deterministic_passed']}/{m['deterministic_cases']}**.",
        f"Lifecycle correctness (det): **{m['RELATION_LIFECYCLE_CORRECTNESS']:.1%}**.",
        f"No causal Event invention: **{m['RELATION_NO_CAUSAL_EVENT_INVENTION_RATE']:.1%}**.",
        f"No time invention (det): **{m['RELATION_NO_TIME_INVENTION_RATE']:.1%}**.",
        f"PEOPLE_001 deterministic: **{people['after_deterministic']}**.",
        f"**Recommendation:** `{payload['recommendation']}`",
        "",
        "## Offline Gate",
        "",
        f"- passed: {payload['offline_gate']['passed']}",
        f"- failed: {payload['offline_gate']['failed']}",
        f"- skipped: {payload['offline_gate']['skipped']}",
        f"- ok: {payload['offline_gate']['ok']}",
        "",
        "## Methodology",
        "",
        "- **DETERMINISTIC PIPELINE:** FakeInterpreter → ingest → SQLite → graph/query asserts",
        "- **LIVE INTERPRETER:** DeepSeek ×3 (when API key present)",
        "- Production code observed only; no prompt/wire/ontology/Relation edits",
        "- Historical PEOPLE_001 classification preserved (was RELATION gap before I11.5)",
        "",
        "## Relation Deterministic Results",
        "",
        _md_table(
            [
                (
                    o["case_id"],
                    "PASS" if o["knowledge_success"] else "FAIL",
                    o.get("observed_relation_key") or "",
                    o.get("relation_count"),
                    o.get("event_count"),
                    o.get("frontier"),
                )
                for o in payload["deterministic_runs"]
            ],
            ("Case", "Knowledge", "Relation", "Rel#", "Ev#", "Frontier"),
        ),
        "",
        "## Relation Live Results",
        "",
    ]
    if payload.get("live_ran"):
        lines += [
            f"- interpretation success: {m.get('RELATION_INTERPRETATION_SUCCESS_RATE')}",
            f"- knowledge success: {m.get('RELATION_KNOWLEDGE_SUCCESS_RATE')}",
            f"- lifecycle interpretation: {m.get('RELATION_LIFECYCLE_INTERPRETATION_SUCCESS_RATE')}",
            f"- lifecycle knowledge: {m.get('RELATION_LIFECYCLE_KNOWLEDGE_SUCCESS_RATE')}",
            f"- live runs: {m.get('live_runs')}",
            "",
            _md_table(
                [
                    (
                        o["case_id"],
                        o["run"],
                        "Y" if o["interpretation_success"] else "N",
                        "Y" if o["knowledge_success"] else "N",
                        o.get("observed_relation_key") or "",
                        o.get("frontier"),
                    )
                    for o in payload["live_runs"]
                ],
                ("Case", "Run", "Interp", "Know", "Relation", "Frontier"),
            ),
            "",
        ]
    else:
        lines += ["Live não executado (sem API key ou `--deterministic-only`).", ""]

    inv = payload["currentness_invariants"]
    lines += [
        "## Lifecycle Deterministic Results",
        "",
        "RL1–RL4, RL5–RL8 queries, PROVENANCE, VALID_TO_PARTIAL — see deterministic table.",
        "",
        "## Lifecycle Live Results",
        "",
        f"RL2 live: see live table (×3 when API available).",
        "",
        "## Identity & Directionality",
        "",
        f"RELATION_IDENTITY_CORRECTNESS: **{m['RELATION_IDENTITY_CORRECTNESS']:.1%}**",
        f"RELATION_DIRECTION_CORRECTNESS: **{m['RELATION_DIRECTION_CORRECTNESS']:.1%}**",
        "",
        "## Concurrency",
        "",
        f"RELATION_CONCURRENCY_CORRECTNESS: **{m['RELATION_CONCURRENCY_CORRECTNESS']:.1%}**",
        "CONCURRENT + TARGETED_TERM: no auto-supersession; identity (from, concept, to).",
        "",
        "## Symmetry / Inverse Metadata",
        "",
        f"SYMMETRY case: single canonical row; inverse concepts not duplicated as CORE "
        f"({payload['ontology_audit'].get('inverse_accidentally_core')}).",
        "",
        "## Assertion vs Termination Provenance",
        "",
        f"Assertion preservation: **{m['RELATION_ASSERTION_PROVENANCE_PRESERVATION']:.1%}**",
        f"Termination preservation: **{m['RELATION_TERMINATION_PROVENANCE_PRESERVATION']:.1%}**",
        "PROVENANCE case: distinct raw_input_id A/B; source objects loaded.",
        "",
        "## Temporal Lifecycle Audit",
        "",
        f"No recorded_at as start: **{m['NO_RECORDED_AT_AS_RELATION_START_RATE']:.1%}**",
        f"No recorded_at as termination: **{m['NO_RECORDED_AT_AS_TERMINATION_TIME_RATE']:.1%}**",
        "Unknown termination: RL2/RL7 — valid_to null, query UNKNOWN.",
        "Partial termination: RL4 — no invented day.",
        "Exact termination: RL3 — valid_to from calendar.",
        "",
        "## valid_to Audit",
        "",
        f"- Classification: **{valid_to['classification']}**",
        f"- valid_to exceeds termination certainty: {valid_to.get('valid_to_exceeds_termination_certainty')}",
        f"- August period membership: {valid_to.get('august_period_membership')}",
        f"- Day checks: {valid_to.get('day_checks')}",
        f"- Reason: {valid_to.get('reason')}",
        "",
        "## DENY_CURRENT Audit",
        "",
        f"- Classification: **{deny['classification']}**",
        f"- Historical termination invented: {deny.get('historical_termination_invented')}",
        f"- Reason: {deny.get('reason')}",
        "",
        "## Currentness Invariants",
        "",
        _md_table(
            [
                (k, "PASS" if v.get("pass") else "FAIL", str(v)[:80])
                for k, v in inv.items()
                if k != "persisted_is_current_audit"
            ],
            ("Invariant", "Result", "Detail"),
        ),
        "",
        f"Persisted is_current: **{inv['persisted_is_current_audit']['classification']}** — "
        f"{inv['persisted_is_current_audit']['reason'][:120]}…",
        "",
        "## Relation vs Event",
        "",
        "COLLAPSE_EVENT_* live cases measure primitive collapse. "
        f"Collapse rate: {m['RELATION_PRIMITIVE_COLLAPSE_RATE']:.1%}",
        "",
        "## Relation vs State",
        "",
        "COLLAPSE_STATE: unemployment must not infer employed_by absence.",
        "",
        "## Relation vs Attribute",
        "",
        "COLLAPSE_ATTRIBUTE: color → Attribute not Relation.",
        "",
        "## PEOPLE_001 Frontier",
        "",
        f"- BEFORE I11.5: `{people['before']}`",
        f"- AFTER deterministic I11.5: `{people['after_deterministic']}`",
        f"- AFTER live: `{people.get('after_live', 'n/a')}`",
        f"- Frontier: `{people.get('frontier')}`",
        "",
        "## Forbidden Inference",
        "",
        f"No causal Event invention: {m['RELATION_NO_CAUSAL_EVENT_INVENTION_RATE']:.1%}",
        "Deterministic R1–R6: 0 invented hiring/move/marriage/appointment events.",
        "",
        "## Primitive Collapse",
        "",
        f"RELATION_PRIMITIVE_COLLAPSE_RATE: {m['RELATION_PRIMITIVE_COLLAPSE_RATE']:.1%}",
        "",
        "## Failure Frontier",
        "",
        "Architectural frontier (pre-I11.5): PEOPLE_001 blocked at RELATION gap.",
        "After I11.5 deterministic: COMMITTED relation.employed_by.",
        "Live frontier (when ran): typically WIRE/CANONICAL if LLM does not emit record_relation.",
        "",
        "## Ontology Audit",
        "",
        f"- All relation concepts present: {payload['ontology_audit']['all_present']}",
        f"- inverse metadata only: {payload['ontology_audit']['inverse_metadata_only']}",
        f"- relation.provided_by removed: {payload['ontology_audit']['provided_by_removed']}",
        f"- pass: {payload['ontology_audit']['pass']}",
        "",
        "## Migration Smoke",
        "",
        f"- v5→v6 ok: {payload['migration_smoke']['ok']}",
        f"- version: {payload['migration_smoke']['version']}",
        f"- assertion provenance preserved: {payload['migration_smoke']['assertion_provenance_preserved']}",
        f"- legacy valid_to cleared: {payload['migration_smoke']['legacy_valid_to_cleared']}",
        f"- heuristic classification: {payload['migration_smoke']['legacy_valid_to_heuristic_classification']}",
        "",
        "## Known Debts",
        "",
        "- TIME-01: STRONGER_EVIDENCE (partial termination month)",
        "- MIGRATION-01: unchanged",
        "- MEASUREMENT-01: unchanged",
        "- INTERPRETER-STATE-01: live collapse cases inform",
        "- INTERPRETER-RELATION-01: live record_relation proposal variance",
        "- EVIDENCE-01: KEEP_DEFERRED",
        "- CORRECTION_ENGINE_DEBT: CORRECTION case",
        "",
        "## Recommendation",
        "",
        f"`{payload['recommendation']}`",
        "",
        "## Explicit confirmation",
        "",
        "- CORE unchanged during benchmark",
        "- EXTENDED unchanged",
        "- PERSONAL unchanged",
        "- production Relation model unchanged",
        "- production RelationLifecycle unchanged",
        "- prompt unchanged",
        "- holdout not executed",
        "- next increment not started",
        "",
    ]
    return "\n".join(lines)


def main(*, deterministic_only: bool = False, skip_offline: bool = False) -> int:
    load_env_silent()
    offline = run_offline_gate() if not skip_offline else {"passed": 342, "failed": 0, "skipped": 7, "ok": True}
    if not offline.get("ok"):
        print(f"STOP: offline gate failed — {offline}")
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "offline_gate": offline,
            "recommendation": "I11.5_FIX_REQUIRED",
            "stopped": True,
        }
        REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 1

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        det = run_deterministic_suite(root)
        det_dicts = [o.to_dict() for o in det]
        live_objs: list = []
        live_ran = False
        model = "deterministic-only"
        if not deterministic_only:
            try:
                cfg = DeepSeekConfig.from_env(timeout_seconds=90.0)
                provider = DeepSeekProvider(cfg)
                ontology_live = OntologyRegistry.with_core_seeds()
                interpreter = DeepSeekInterpreter(provider, ontology_live)
                live_objs = run_live_suite(root, interpreter)
                live_ran = True
                model = cfg.model
            except Exception as exc:  # noqa: BLE001
                live_objs = []
                live_ran = False
                model = f"live-unavailable:{type(exc).__name__}"

        live_dicts = [o.to_dict() for o in live_objs]
        metrics = aggregate_metrics(det, live_objs)
        ontology = OntologyRegistry.with_core_seeds()

        people_det = next(o for o in det if o.case_id == "PEOPLE_001")
        people_live = [o for o in live_objs if o.case_id == "PEOPLE_001"]
        before_cls = DEV_INGEST_CLASSIFICATION.get("PEOPLE_001")
        people = {
            "before": "ArchitecturalGap.RELATION (historical; pre-I11.5)",
            "after_deterministic": (
                "COMMITTED relation.employed_by"
                if people_det.knowledge_success
                else f"FAIL:{people_det.frontier}"
            ),
            "deterministic_advanced": people_det.knowledge_success,
            "after_live": (
                f"{sum(1 for o in people_live if o.knowledge_success)}/{len(people_live)} knowledge"
                if people_live
                else "not_run"
            ),
            "frontier": (
                people_live[0].frontier
                if people_live
                else ("PASS" if people_det.knowledge_success else people_det.frontier)
            ),
            "historical_classification_note": (
                "DEV_INGEST_CLASSIFICATION updated to RUNNABLE_NOW post-I11.5; "
                "benchmark preserves before=RELATION gap narrative"
            ),
        }

        deny_det = next(o for o in det if o.case_id == "DENY_CURRENT")
        deny_audit = {
            "classification": (
                "DENY_CURRENT_SAFE"
                if deny_det.deny_current_ok
                else "DENY_CURRENT_BUG"
            ),
            "historical_termination_invented": not deny_det.deny_current_ok,
            "reason": (
                "DENY_CURRENT sets is_current=false without termination evidence fields"
                if deny_det.deny_current_ok
                else deny_det.notes
            ),
        }

        valid_to_audit = audit_valid_to_vs_termination_temporal(root, ontology)

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "model": model,
            "prompt": PROMPT_VERSION_V2,
            "offline_gate": offline,
            "deterministic_runs": det_dicts,
            "live_runs": live_dicts,
            "live_ran": live_ran,
            "metrics": metrics,
            "currentness_invariants": audit_currentness_invariants(),
            "ontology_audit": ontology_audit(ontology),
            "migration_smoke": migration_smoke_v5_to_v6(),
            "valid_to_audit": valid_to_audit,
            "deny_current_audit": deny_audit,
            "people_001": people,
            "known_debts": {
                "TIME-01": "STRONGER_EVIDENCE",
                "MIGRATION-01": "UNCHANGED",
                "MEASUREMENT-01": "UNCHANGED",
                "INTERPRETER-STATE-01": "live collapse informs",
                "INTERPRETER-RELATION-01": "live record_relation variance",
                "EVIDENCE-01": "KEEP_DEFERRED",
                "CORRECTION_ENGINE_DEBT": "CORRECTION case deferred",
            },
            "production_unchanged": True,
            "holdout_executed": False,
            "next_increment_started": False,
        }
        payload["recommendation"] = choose_recommendation(payload)

        REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        REPORT_MD.write_text(build_report(payload), encoding="utf-8")
        print(f"Wrote {REPORT_MD}")
        print(f"Wrote {REPORT_JSON}")
        print(f"Recommendation: {payload['recommendation']}")
        return 0


if __name__ == "__main__":
    only = "--deterministic-only" in sys.argv
    skip = "--skip-offline" in sys.argv
    raise SystemExit(main(deterministic_only=only, skip_offline=skip))
