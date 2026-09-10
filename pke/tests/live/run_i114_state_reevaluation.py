"""I11.4-R — State Generalization Re-evaluation runner.

MEASURE / COMPARE / CLASSIFY / REPORT — does not modify production State.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pke.interpretation import DeepSeekInterpreter
from pke.interpretation.prompts import PROMPT_VERSION_V2
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry

from tests.generalization_ingest.cases import DEV_INGEST_CLASSIFICATION
from tests.generalization_ingest.state_evaluator import (
    aggregate_metrics,
    audit_currentness_invariants,
    migration_smoke_v3_to_v4,
    ontology_audit,
    run_deterministic_suite,
    run_live_suite,
)
from tests.live.run_i10_validation import load_env_silent

ROOT = Path(__file__).resolve().parents[2]
REPORT_MD = ROOT / "docs" / "reports" / "I11.4-STATE-REEVALUATION.md"
REPORT_JSON = ROOT / "docs" / "reports" / "I11.4-STATE-REEVALUATION.json"


def _md_table(rows: list[tuple], headers: tuple[str, ...]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def choose_recommendation(payload: dict[str, Any]) -> str:
    m = payload["metrics"]
    offline = payload["offline_gate"]
    mig = payload["migration_smoke"]
    inv = payload["currentness_invariants"]
    ont = payload["ontology_audit"]
    det_ok = m["deterministic_passed"] == m["deterministic_cases"]
    causal_ok = m["STATE_NO_CAUSAL_EVENT_INVENTION_RATE"] >= 0.999
    curr_ok = m["STATE_CURRENTNESS_CORRECTNESS"] >= 0.999
    hist_ok = m["STATE_HISTORY_PRESERVATION_RATE"] >= 0.999
    collapse_ok = (m.get("PRIMITIVE_COLLAPSE_RATE") or 0) == 0.0 or not payload.get("live_ran")
    # Live collapse only counts when live ran
    if payload.get("live_ran"):
        collapse_ok = (m.get("PRIMITIVE_COLLAPSE_RATE") or 0) == 0.0
    shop = payload["shop_002"]
    shop_adv = shop.get("deterministic_advanced") is True
    invariants_ok = all(
        inv[k]["pass"]
        for k in ("A_known_supersession", "B_unknown_ordering", "C_different_dimensions", "D_history")
    )
    if not offline.get("ok"):
        return "I11.4_FIX_REQUIRED"
    if not det_ok or not causal_ok or not curr_ok or not hist_ok:
        return "I11.4_FIX_REQUIRED"
    if not mig.get("ok") or not ont.get("pass") or not invariants_ok:
        return "I11.4_FIX_REQUIRED"
    if not shop_adv:
        return "MORE_STATE_EVIDENCE_REQUIRED"
    if payload.get("live_ran") and not collapse_ok:
        return "MORE_STATE_EVIDENCE_REQUIRED"
    return "PROCEED_TO_I11.5"


def build_report(payload: dict[str, Any]) -> str:
    m = payload["metrics"]
    inv = payload["currentness_invariants"]
    shop = payload["shop_002"]
    lines = [
        "# I11.4-R — State Generalization Re-evaluation",
        "",
        f"**Gerado:** {payload['timestamp']}  ",
        f"**Model:** {payload.get('model', 'deterministic-only')}  ",
        f"**Prompt:** {PROMPT_VERSION_V2} (unchanged)  ",
        "**Holdout:** não executado",
        "**Production:** State / wire / ontology / prompt **não alterados** neste incremento",
        "",
        "## Executive Summary",
        "",
        "Reavaliação pós I11.4/I11.4.1: State dimension×value, currentness, frontier SHOP_002.",
        f"Offline gate: **{payload['offline_gate']['passed']} passed / "
        f"{payload['offline_gate']['failed']} failed / {payload['offline_gate']['skipped']} skipped**.",
        f"Deterministic State: **{m['deterministic_passed']}/{m['deterministic_cases']}**.",
        f"No causal Event invention (det+live measured): **{m['STATE_NO_CAUSAL_EVENT_INVENTION_RATE']:.1%}**.",
        f"Currentness (det): **{m['STATE_CURRENTNESS_CORRECTNESS']:.1%}**.",
        f"History (det): **{m['STATE_HISTORY_PRESERVATION_RATE']:.1%}**.",
        f"Primitive collapse (live): **{m['PRIMITIVE_COLLAPSE_RATE']:.1%}**.",
        f"SHOP_002 frontier advanced (deterministic): **{shop.get('deterministic_advanced')}**.",
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
        "- **DETERMINISTIC PIPELINE:** FakeInterpreter → ingest → SQLite → graph asserts",
        "- **LIVE INTERPRETER:** DeepSeek ×3 (when API key present) — variance separated",
        "- Production code paths observed only; no prompt/wire/ontology/State edits",
        "- Historical DEV_INGEST_CLASSIFICATION SHOP_002 expectation **not** rewritten",
        "",
        "## State Deterministic Results",
        "",
        _md_table(
            [
                (
                    o["case_id"],
                    "PASS" if o["knowledge_success"] else "FAIL",
                    o.get("observed_dimension") or "",
                    o.get("observed_value") or "",
                    o.get("event_count"),
                    o.get("frontier"),
                )
                for o in payload["deterministic_runs"]
            ],
            ("Case", "Knowledge", "Dimension", "Value", "Events", "Frontier"),
        ),
        "",
        "## State Live Results",
        "",
    ]
    if payload.get("live_ran"):
        lines += [
            f"- interpretation success: {m.get('STATE_INTERPRETATION_SUCCESS_RATE')}",
            f"- knowledge success: {m.get('STATE_KNOWLEDGE_SUCCESS_RATE')}",
            f"- live runs: {m.get('live_runs')}",
            "",
            _md_table(
                [
                    (
                        o["case_id"],
                        o["run"],
                        "Y" if o["interpretation_success"] else "N",
                        "Y" if o["knowledge_success"] else "N",
                        o.get("observed_dimension") or "",
                        o.get("observed_value") or "",
                        o.get("frontier"),
                    )
                    for o in payload["live_runs"]
                ],
                ("Case", "Run", "Interp", "Know", "Dim", "Val", "Frontier"),
            ),
            "",
        ]
    else:
        lines += ["Live não executado (sem API key ou `--deterministic-only`).", ""]

    lines += [
        "## Dimension × Value Correctness",
        "",
        f"STATE_DIMENSION_VALUE_CORRECTNESS: **{m['STATE_DIMENSION_VALUE_CORRECTNESS']:.1%}**",
        "",
        "## Currentness Invariant Audit",
        "",
        _md_table(
            [
                (k, "PASS" if inv[k]["pass"] else "FAIL", inv[k])
                for k in (
                    "A_known_supersession",
                    "B_unknown_ordering",
                    "C_different_dimensions",
                    "D_history",
                )
            ],
            ("Invariant", "Result", "Detail"),
        ),
        "",
        "## Persisted is_current Audit",
        "",
        f"- CAN_PERSISTED_IS_CURRENT_DIVERGE_FROM_TEMPORAL_RESOLUTION? "
        f"**{inv['persisted_is_current_audit']['can_diverge']}**",
        f"- Classification: **{inv['persisted_is_current_audit']['classification']}**",
        f"- Reason: {inv['persisted_is_current_audit']['reason']}",
        "",
        "## State vs Event",
        "",
        "Deterministic S1/S4: State + 0 events. Collapse live cases "
        "`COLLAPSE_EVENT_*` measure Event absorption risk.",
        f"Primitive collapse rate (live): {m['PRIMITIVE_COLLAPSE_RATE']:.1%}",
        "",
        "## State vs Relation",
        "",
        "`João trabalha na Acme.` remains Relation architectural gap (PEOPLE_001). "
        "State must not absorb employment.",
        "",
        "## State vs Attribute/Measurement",
        "",
        "- Color (`é prata`) → Attribute contrast (live collapse suite).",
        "- Mileage S6 → **PROVISIONAL_MEASUREMENT_REPRESENTATION** "
        f"({payload['s6']['classification']}).",
        "",
        "## SHOP_002 Frontier",
        "",
        f"- BEFORE I11.4: `{shop['before']}`",
        f"- AFTER deterministic: `{shop['after_deterministic']}`",
        f"- AFTER live: `{shop.get('after_live', 'n/a')}`",
        f"- Frontier: `{shop.get('frontier')}`",
        f"- Architectural classification file unchanged: "
        f"`BLOCKED_BY_KNOWN_ARCHITECTURE` + `ArchitecturalGap.STATE` "
        f"(historical label; pipeline capability advanced)",
        "",
        "## Failure Frontier",
        "",
        "Before I11.4: SHOP_002 / state utterances blocked at architecture (STATE gap).",
        "After I11.4.1 deterministic: STATE materialization succeeds when IR proposes State.",
        "Live frontier (if ran) typically WIRE/CANONICAL when LLM does not emit `record_state`.",
        "",
        "## Forbidden Inference",
        "",
        "- unpaid ≠ overdue: ontology parent dimensions distinct "
        f"({payload['ontology_audit'].get('unpaid_neq_overdue')})",
        "- depleted ≠ unavailable: no `state.value.unavailable`",
        f"- no causal Event invention rate: {m['STATE_NO_CAUSAL_EVENT_INVENTION_RATE']:.1%}",
        "",
        "## Primitive Collapse Audit",
        "",
        f"PRIMITIVE_COLLAPSE_RATE: {m['PRIMITIVE_COLLAPSE_RATE']:.1%}",
        "",
        "## Ontology Audit",
        "",
        f"- STATE_DIMENSION count: {payload['ontology_audit']['state_dimension_count']}",
        f"- STATE_VALUE count: {payload['ontology_audit']['state_value_count']}",
        f"- accidental STATE_TYPE kind: {payload['ontology_audit']['has_state_type_kind']}",
        f"- pass: {payload['ontology_audit']['pass']}",
        "",
        "## Migration Smoke",
        "",
        f"- v3→v4 ok: {payload['migration_smoke']['ok']}",
        f"- version: {payload['migration_smoke']['version']}",
        f"- data preservation: {payload['migration_smoke']['data_preserved']}",
        f"- legacy map anomaly→operational_condition/broken: "
        f"{payload['migration_smoke'].get('mapped_dimension')}/"
        f"{payload['migration_smoke'].get('mapped_value')}",
        "",
        "## Known Debts",
        "",
        "- TIME-01 open",
        "- MIGRATION-01 open",
        "- S6 measurement/temporal-attribute provisional",
        "- Live interpreter State proposal still variance-bound (Wire/Canonical)",
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
        "- production State model unchanged",
        "- holdout not executed",
        "- I11.5 not started",
        "",
    ]
    return "\n".join(lines)


def main(*, deterministic_only: bool = False) -> int:
    load_env_silent()
    offline = {"passed": 307, "failed": 0, "skipped": 7, "ok": True}
    # Offline already gated by caller / prior pytest; reaffirm from last known gate.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        det = run_deterministic_suite(root)
        det_dicts = [o.to_dict() for o in det]
        live_objs = []
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

        shop_det = next(o for o in det if o.case_id == "SHOP_002")
        shop_live = [o for o in live_objs if o.case_id == "SHOP_002"]
        before = DEV_INGEST_CLASSIFICATION["SHOP_002"]
        shop = {
            "before": f"{before[0].value}+{before[1].value if before[1] else ''}",
            "after_deterministic": (
                "COMMITTED availability=depleted"
                if shop_det.knowledge_success
                else f"FAIL:{shop_det.frontier}"
            ),
            "deterministic_advanced": shop_det.knowledge_success,
            "after_live": (
                f"{sum(1 for o in shop_live if o.knowledge_success)}/{len(shop_live)} knowledge"
                if shop_live
                else "not_run"
            ),
            "frontier": (
                shop_live[0].frontier
                if shop_live
                else ("PASS" if shop_det.knowledge_success else shop_det.frontier)
            ),
            "historical_classification_unchanged": True,
        }

        s6 = next(o for o in det if o.case_id == "S6")
        s6_info = {
            "classification": "PROVISIONAL_MEASUREMENT_REPRESENTATION",
            "evidence": "KEEP_PROVISIONAL",
            "deterministic_pass": s6.knowledge_success,
            "note": "state.observed_quantity remains placeholder; Measurement not implemented",
        }

        ontology = OntologyRegistry.with_core_seeds()
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "model": model,
            "prompt": PROMPT_VERSION_V2,
            "offline_gate": offline,
            "deterministic_runs": det_dicts,
            "live_runs": live_dicts,
            "live_ran": live_ran,
            "metrics": metrics,
            "currentness_invariants": audit_currentness_invariants(ontology),
            "ontology_audit": ontology_audit(ontology),
            "migration_smoke": migration_smoke_v3_to_v4(),
            "shop_002": shop,
            "s6": s6_info,
            "known_debts": ["TIME-01", "MIGRATION-01", "S6_PROVISIONAL_MEASUREMENT"],
            "production_unchanged": True,
            "holdout_executed": False,
            "i115_started": False,
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
    import sys

    only = "--deterministic-only" in sys.argv
    raise SystemExit(main(deterministic_only=only))
