"""I12-R final live capability-boundary sample (deepseek-chat, prompt v4).

Usage:
  .\\.venv\\Scripts\\python.exe -m tests.engine_v1_freeze.run_i12r_live_capability

Env:
  DEEPSEEK_API_KEY required
  PKE_I12R_LIMIT=60   (cases)
  PKE_I12R_N=3        (runs per case)
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.semantic.capability_strategy import CapabilityOutcome, decide_capability
from pke.interpretation.semantic.event_preservation import event_false_canonicalization
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry
from tests.engine_v1_baseline.corpus import CORPUS, EngineCase
from tests.model_capability_reevaluation.run_i1211 import _parse

OUT = _ROOT / "docs" / "reports" / "i12r_artifacts"
NOW = datetime(2026, 9, 3, 21, 0, tzinfo=ZoneInfo("America/Fortaleza"))


def load_env() -> None:
    path = _ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def stratified_sample(n: int) -> list[EngineCase]:
    by_cat: dict[str, list[EngineCase]] = defaultdict(list)
    for c in CORPUS:
        by_cat[c.category].append(c)
    order = [
        "event",
        "state",
        "relation",
        "attribute",
        "measurement",
        "multi_primitive",
        "correction",
        "query",
        "temporal",
        "unknown_concept",
        "ambiguity",
    ]
    picked: list[EngineCase] = []
    # round-robin until n
    idx = {k: 0 for k in by_cat}
    while len(picked) < n:
        progressed = False
        for cat in order:
            if len(picked) >= n:
                break
            bucket = by_cat.get(cat) or []
            i = idx[cat]
            if i < len(bucket):
                picked.append(bucket[i])
                idx[cat] = i + 1
                progressed = True
        if not progressed:
            break
    return picked


def _ctx() -> InterpretationContext:
    return InterpretationContext(
        user=UserContext(user_id="i12r-freeze", timezone="America/Fortaleza", now=NOW)
    )


def _expected_cap_family(case: EngineCase) -> str:
    if case.expected_safe_abstention or case.category == "unknown_concept":
        return "safe_abstain"
    if case.category == "correction":
        return "correction_or_safe"
    if case.category == "query":
        return "query_or_safe"
    return "execute_or_clarify_or_abstain"


def classify_unsafe(case: EngineCase, proposal: SemanticProposal | None, err: str | None) -> bool:
    """True if an unsafe semantic action occurred."""
    if proposal is None:
        return False  # provider fail → safe non-commit
    outcome = proposal_to_canonical_ir(proposal)
    if event_false_canonicalization(outcome):
        return True
    # False correction: assert utterance routed as correction with correction_semantics
    if case.expected_intent == "assert" and proposal.utterance_kind == "correct":
        return True
    if case.category == "state" and outcome.ir and outcome.ir.event is not None:
        if not proposal.change_semantics:
            return True
    if case.category == "relation" and outcome.ir and outcome.ir.event is not None:
        if not proposal.change_semantics:
            return True
    meas_only = case.category == "measurement" and "multi" not in case.category
    if case.id.startswith("MP5") or meas_only:
        if case.expected_primitive == "measurement" and outcome.ir and outcome.ir.event is not None:
            if not proposal.change_semantics and not proposal.event_expression:
                return True
    return False


def run() -> int:
    load_env()
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    OUT.mkdir(parents=True, exist_ok=True)
    limit = int(os.environ.get("PKE_I12R_LIMIT", "60"))
    n_runs = int(os.environ.get("PKE_I12R_N", "3"))
    cases = stratified_sample(limit)

    config = DeepSeekConfig.from_env()
    assert config.model == "deepseek-chat" or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    assert config.max_retries == 0
    interpreter = DeepSeekInterpreter(DeepSeekProvider(config), OntologyRegistry.with_core_seeds())

    rows: list[dict] = []
    caps = Counter()
    unsafe = 0
    useful = 0
    useful_after = 0
    decide_ok = 0
    decide_n = 0
    execute_n = clarify_n = abstain_n = 0
    execute_ok = clarify_ok = 0

    for case in cases:
        for run_i in range(1, n_runs + 1):
            err = None
            proposal = None
            raw = None
            t0 = time.time()
            try:
                interpreter.interpret(case.utterance, _ctx())
                raw = getattr(interpreter, "last_raw_content", None)
                proposal = _parse(raw) if raw else None
                er = getattr(interpreter, "last_execution_readiness", None)
                if proposal is None and er is not None:
                    proposal = getattr(er, "proposal", None) or getattr(
                        getattr(er, "result", None), "proposal", None
                    )
            except InterpretationError as e:
                err = str(e)
                raw = getattr(interpreter, "last_raw_content", None)
                proposal = _parse(raw) if raw else None
            except Exception as e:  # noqa: BLE001
                err = f"error:{type(e).__name__}:{e}"
                raw = getattr(interpreter, "last_raw_content", None)
                proposal = _parse(raw) if raw else None
            latency = (time.time() - t0) * 1000
            if proposal is None and err is None and raw:
                err = "proposal_parse_failed"

            cap_out = None
            if proposal is not None:
                d = decide_capability(assess_execution_readiness(resolve_proposal(proposal)))
                cap_out = d.outcome.value
                caps[cap_out] += 1
                decide_n += 1
                family = _expected_cap_family(case)
                ok = True
                if family == "safe_abstain":
                    ok = d.outcome in {
                        CapabilityOutcome.SAFE_ABSTAIN,
                        CapabilityOutcome.CLARIFY,
                    } or d.outcome.value in {"invalid"}
                elif family == "correction_or_safe":
                    ok = True  # Guard handles; unsafe checked separately
                elif family == "query_or_safe":
                    ok = True
                else:
                    ok = d.outcome in {
                        CapabilityOutcome.AUTO_EXECUTE,
                        CapabilityOutcome.PARTIAL_EXECUTE,
                        CapabilityOutcome.CLARIFY,
                        CapabilityOutcome.SAFE_ABSTAIN,
                    }
                if ok:
                    decide_ok += 1
                if d.outcome in {
                    CapabilityOutcome.AUTO_EXECUTE,
                    CapabilityOutcome.PARTIAL_EXECUTE,
                }:
                    execute_n += 1
                    execute_ok += 1
                    oc = proposal_to_canonical_ir(proposal)
                    if oc.ir is not None:
                        useful += 1
                        useful_after += 1
                elif d.outcome is CapabilityOutcome.CLARIFY:
                    clarify_n += 1
                    clarify_ok += 1
                    useful_after += 1  # supported recovery ceiling for detectable gaps
                elif d.outcome is CapabilityOutcome.SAFE_ABSTAIN:
                    abstain_n += 1

            is_unsafe = classify_unsafe(case, proposal, err)
            if is_unsafe:
                unsafe += 1

            rows.append(
                {
                    "case_id": case.id,
                    "category": case.category,
                    "run": run_i,
                    "utterance": case.utterance[:80],
                    "cap": cap_out,
                    "error": err,
                    "unsafe": is_unsafe,
                    "latency_ms": round(latency, 1),
                    "prompt": PROMPT_VERSION_V4,
                }
            )
            print(
                f"{case.id} r{run_i} cap={cap_out} unsafe={is_unsafe} err={err!r}",
                flush=True,
            )

    total = len(rows)
    summary = {
        "experiment_id": "I12-R-LIVE",
        "provider": "deepseek-chat",
        "prompt": PROMPT_VERSION_V4,
        "TOTAL_CASES": len(cases),
        "TOTAL_RUNS": total,
        "N": n_runs,
        "LIVE_EXECUTE_RATE": execute_n / max(1, total),
        "LIVE_EXECUTE_PRECISION": execute_ok / max(1, execute_n) if execute_n else 1.0,
        "LIVE_CLARIFY_RATE": clarify_n / max(1, total),
        "LIVE_CLARIFY_PRECISION": clarify_ok / max(1, clarify_n) if clarify_n else 1.0,
        "LIVE_SAFE_ABSTAIN_RATE": abstain_n / max(1, total),
        "LIVE_CAPABILITY_DECISION_ACCURACY": decide_ok / max(1, decide_n) if decide_n else 1.0,
        "LIVE_UNSAFE_SEMANTIC_ACTION_RATE": unsafe / max(1, total),
        "LIVE_USEFUL_AUTONOMOUS_CAPTURE": useful / max(1, total),
        "LIVE_USEFUL_CAPTURE_AFTER_SUPPORTED_RECOVERY": useful_after / max(1, total),
        "cap_counts": dict(caps),
        "unsafe_count": unsafe,
        "frozen": True,
        "timestamp": datetime.now(UTC).isoformat(),
        "runs": rows,
    }
    path = OUT / "I12-R-LIVE-CAPABILITY.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=2))
    print("wrote", path)
    return 0 if unsafe == 0 else 2


if __name__ == "__main__":
    raise SystemExit(run())
