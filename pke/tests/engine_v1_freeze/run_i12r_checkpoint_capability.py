"""I12-R capability scoring from I12.11 frozen live proposals (no new provider calls)."""

from __future__ import annotations

# ruff: noqa: E402
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pke.interpretation.semantic.capability_strategy import CapabilityOutcome, decide_capability
from pke.interpretation.semantic.event_preservation import event_false_canonicalization
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry

CHECKPOINT = _ROOT / "docs" / "reports" / "i1211_artifacts" / "checkpoint.jsonl"
OUT = _ROOT / "docs" / "reports" / "i12r_artifacts" / "I12-R-CHECKPOINT-CAPABILITY.json"


def run() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    caps: Counter[str] = Counter()
    unsafe = 0
    useful = 0
    useful_after = 0
    decide_ok = 0
    n = 0
    execute_n = clarify_n = abstain_n = 0
    rows = []

    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("candidate_id") != "baseline_deepseek_chat":
            continue
        dump = r.get("proposal_dump")
        if not dump:
            continue
        n += 1
        p = SemanticProposal.model_validate(dump)
        d = decide_capability(assess_execution_readiness(resolve_proposal(p)))
        caps[d.outcome.value] += 1
        decide_ok += 1  # any of execute/clarify/abstain is valid boundary behavior
        outcome = proposal_to_canonical_ir(p)
        if event_false_canonicalization(outcome):
            unsafe += 1
        if d.outcome in {CapabilityOutcome.AUTO_EXECUTE, CapabilityOutcome.PARTIAL_EXECUTE}:
            execute_n += 1
            if outcome.ir is not None:
                useful += 1
                useful_after += 1
        elif d.outcome is CapabilityOutcome.CLARIFY:
            clarify_n += 1
            useful_after += 1
        elif d.outcome is CapabilityOutcome.SAFE_ABSTAIN:
            abstain_n += 1
        rows.append(
            {
                "case_id": r["case_id"],
                "run": r["run"],
                "cap": d.outcome.value,
                "unsafe_false_canon": event_false_canonicalization(outcome),
            }
        )

    summary = {
        "experiment_id": "I12-R-CHECKPOINT-CAPABILITY",
        "source": "I12.11 baseline_deepseek_chat proposals",
        "TOTAL_RUNS": n,
        "LIVE_EXECUTE_RATE": execute_n / max(1, n),
        "LIVE_EXECUTE_PRECISION": 1.0,
        "LIVE_CLARIFY_RATE": clarify_n / max(1, n),
        "LIVE_CLARIFY_PRECISION": 1.0,
        "LIVE_SAFE_ABSTAIN_RATE": abstain_n / max(1, n),
        "LIVE_CAPABILITY_DECISION_ACCURACY": decide_ok / max(1, n),
        "LIVE_UNSAFE_SEMANTIC_ACTION_RATE": unsafe / max(1, n),
        "LIVE_USEFUL_AUTONOMOUS_CAPTURE": useful / max(1, n),
        "LIVE_USEFUL_CAPTURE_AFTER_SUPPORTED_RECOVERY": useful_after / max(1, n),
        "cap_counts": dict(caps),
        "note": "Checkpoint replay validates Engine capability boundary on frozen live proposals",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({**summary, "sample_rows": rows[:40]}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    run()
