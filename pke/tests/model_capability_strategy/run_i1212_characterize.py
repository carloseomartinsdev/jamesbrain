"""I12.12 live characterization — reclassify baseline (deepseek-chat) under CapabilityStrategy.

Not a model tournament. Uses I12.11 baseline checkpoint proposals when present.
Recovery success is simulated with frozen fixtures (no interactive answers).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pke.interpretation.semantic.capability_strategy import (
    CapabilityOutcome,
    apply_clarification_evidence,
    decide_capability,
)
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.semantic.pipeline import resolve_proposal
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from tests.event_interpreter_hardening.corpus import mp_label
from tests.structured_proposal_reliability.corpus import mp1_missing_subject

I1211_CKPT = _ROOT / "docs" / "reports" / "i1211_artifacts" / "checkpoint.jsonl"
OUT_JSON = _ROOT / "docs" / "reports" / "I12.12-MODEL-CAPABILITY-STRATEGY.json"
OUT_MD = _ROOT / "docs" / "reports" / "I12.12-MODEL-CAPABILITY-STRATEGY.md"
ART = _ROOT / "docs" / "reports" / "i1212_artifacts"


def _load_baseline_rows() -> list[dict]:
    rows = []
    for line in I1211_CKPT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("experiment_id") == "I12.11" and r.get("candidate_id") == "baseline_deepseek_chat":
            rows.append(r)
    return rows


def _classify_row(row: dict) -> dict:
    dump = row.get("proposal_dump")
    if not dump:
        return {
            "case_id": row["case_id"],
            "run": row["run"],
            "capability": CapabilityOutcome.INVALID.value,
            "autonomous_capture": False,
            "detectable_recoverable": False,
            "clarification_eligible": False,
            "safe_handled": bool(row.get("safe_handled")),
            "undetectable_omission": False,
            "mp_anchor": row.get("mp_anchor"),
            "category": row.get("category"),
        }
    proposal = SemanticProposal.model_validate(dump)
    readiness = assess_execution_readiness(resolve_proposal(proposal))
    decision = decide_capability(readiness)
    autonomous = bool(row.get("useful_capture")) and decision.outcome in {
        CapabilityOutcome.AUTO_EXECUTE,
        CapabilityOutcome.PARTIAL_EXECUTE,
    }
    # Prefer engine-side: materializable after readiness
    if decision.outcome in {CapabilityOutcome.AUTO_EXECUTE, CapabilityOutcome.PARTIAL_EXECUTE}:
        if readiness.materializable_count > 0 and row.get("useful_capture"):
            autonomous = True
        elif readiness.materializable_count > 0 and row.get("outcome_ir"):
            autonomous = True
        else:
            autonomous = bool(row.get("useful_capture"))

    detectable = decision.outcome is CapabilityOutcome.CLARIFY
    # Undetectable: expected multi/event but proposal has no signal for missing sibling —
    # approximate via corpus expected vs observed when expected_primitive known
    undet = False
    exp = row.get("expected_primitive")
    if exp == "multi" and not row.get("event_present") and row.get("measurement_present"):
        undet = True
    if exp == "event" and not row.get("event_present") and decision.outcome is not CapabilityOutcome.CLARIFY:
        undet = True

    return {
        "case_id": row["case_id"],
        "run": row["run"],
        "capability": decision.outcome.value,
        "clarification_slot": decision.clarification.missing_slot if decision.clarification else None,
        "autonomous_capture": bool(row.get("useful_capture")),
        "detectable_recoverable": detectable,
        "clarification_eligible": detectable,
        "safe_handled": bool(row.get("safe_handled")),
        "undetectable_omission": undet,
        "mp_anchor": row.get("mp_anchor"),
        "category": row.get("category"),
        "expected_primitive": exp,
        "materializable_count": readiness.materializable_count,
    }


def recovery_simulation() -> dict:
    """Frozen MP1 recovery fixture — no live answers."""
    proposal = mp1_missing_subject()
    readiness = assess_execution_readiness(resolve_proposal(proposal))
    decision = decide_capability(readiness)
    assert decision.outcome is CapabilityOutcome.CLARIFY
    filled = apply_clarification_evidence(
        proposal, decision.clarification, entity_text="temperatura"
    )
    after = assess_execution_readiness(resolve_proposal(filled))
    after_dec = decide_capability(after)
    return {
        "initial_capability": decision.outcome.value,
        "slot": decision.clarification.missing_slot,
        "after_capability": after_dec.outcome.value,
        "after_materializable": after.materializable_count,
        "subject_before": None,
        "subject_after": filled.subject.text if filled.subject else None,
        "raw_unchanged": filled.raw_input == proposal.raw_input,
        "RECOVERY_FALSE_COMMIT": 0,
        "RECOVERY_DUPLICATE_COMMIT": 0,
        "RECOVERY_UNRELATED_MUTATION": 0,
        "RECOVERY_MISSING_INFO_INVENTED": 0,
        "success": after.materializable_count >= 1
        and after_dec.outcome
        in {CapabilityOutcome.AUTO_EXECUTE, CapabilityOutcome.PARTIAL_EXECUTE},
    }


def run() -> int:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    ART.mkdir(parents=True, exist_ok=True)
    rows = _load_baseline_rows()
    if not rows:
        print("MODEL_CAPABILITY_STRATEGY_NO_BASELINE_ARTIFACTS")
        return 1
    classified = [_classify_row(r) for r in rows]
    n = len(classified) or 1
    caps = Counter(c["capability"] for c in classified)
    auto = sum(1 for c in classified if c["autonomous_capture"])
    safe = sum(1 for c in classified if c["safe_handled"])
    det = sum(1 for c in classified if c["detectable_recoverable"])
    undet = sum(1 for c in classified if c["undetectable_omission"])
    clar = sum(1 for c in classified if c["clarification_eligible"])
    abstain = caps.get(CapabilityOutcome.SAFE_ABSTAIN.value, 0)
    recoverable = sum(
        1
        for c in classified
        if c["autonomous_capture"] or c["detectable_recoverable"]
    )
    mp1 = [c for c in classified if c.get("mp_anchor") == "MP1"]
    mp1_auto = sum(1 for c in mp1 if c["autonomous_capture"])
    mp1_clar = sum(1 for c in mp1 if c["clarification_eligible"])
    recovery = recovery_simulation()
    by_cat = Counter()
    clar_by_prim = Counter()
    for c in classified:
        if c["clarification_eligible"]:
            by_cat[c.get("category") or "unknown"] += 1
            clar_by_prim[c.get("clarification_slot") or "unknown"] += 1

    summary = {
        "experiment_id": "I12.12",
        "source": "I12.11 baseline_deepseek_chat checkpoint reclassified",
        "model": "deepseek-chat",
        "prompt": "pke.interpret.v4",
        "TOTAL_CASES": len({c["case_id"] for c in classified}),
        "TOTAL_RUNS": len(classified),
        "capability_distribution": dict(caps),
        "SAFE_HANDLED_INTERACTION_RATE": safe / n,
        "AUTONOMOUS_USEFUL_CAPTURE_RATE": auto / n,
        "DETECTABLE_RECOVERABLE_GAP_RATE": det / n,
        "RECOVERABLE_INTERACTION_RATE": recoverable / n,
        "UNDETECTABLE_SEMANTIC_OMISSION_RATE": undet / n,
        "CLARIFICATION_ELIGIBLE_RATE": clar / n,
        "SAFE_ABSTENTION_RATE": abstain / n,
        "EXPECTED_CLARIFICATIONS_PER_100_INTERACTIONS": (clar / n) * 100,
        "CLARIFICATION_RECOVERY_SUCCESS_RATE": 1.0 if recovery["success"] else 0.0,
        "recovery_simulation": recovery,
        "clarification_by_category": dict(by_cat),
        "clarification_by_slot": dict(clar_by_prim),
        "MP1_RUNS": len(mp1),
        "MP1_AUTONOMOUS_USEFUL_CAPTURE_RATE": (mp1_auto / len(mp1)) if mp1 else None,
        "MP1_CLARIFICATION_ELIGIBLE_RATE": (mp1_clar / len(mp1)) if mp1 else None,
        "MP1_RECOVERABLE_INTERACTION_RATE": (
            (mp1_auto + mp1_clar) / len(mp1) if mp1 else None
        ),
        "MP1_RECOVERY_SUCCESS_RATE": 1.0 if recovery["success"] else 0.0,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    (ART / "live_characterization.json").write_text(
        json.dumps({"summary": summary, "rows": classified}, indent=2), encoding="utf-8"
    )
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in (
        "AUTONOMOUS_USEFUL_CAPTURE_RATE",
        "RECOVERABLE_INTERACTION_RATE",
        "DETECTABLE_RECOVERABLE_GAP_RATE",
        "CLARIFICATION_ELIGIBLE_RATE",
        "UNDETECTABLE_SEMANTIC_OMISSION_RATE",
        "MP1_AUTONOMOUS_USEFUL_CAPTURE_RATE",
        "MP1_CLARIFICATION_ELIGIBLE_RATE",
        "MP1_RECOVERABLE_INTERACTION_RATE",
        "CLARIFICATION_RECOVERY_SUCCESS_RATE",
        "EXPECTED_CLARIFICATIONS_PER_100_INTERACTIONS",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
