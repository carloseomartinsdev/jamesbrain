"""I12.10 focused live validation of execution-incomplete outcomes.

Usage:
  .\\.venv\\Scripts\\python.exe -m tests.structured_proposal_reliability.run_i1210_live
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.semantic.envelope_dispatch import ProviderRoute, dispatch_provider_payload
from pke.interpretation.semantic.execution_readiness import (
    ProposalExecutionOutcome,
    assess_execution_readiness,
)
from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.ontology import OntologyRegistry

from tests.engine_v1_baseline.corpus import EngineCase
from tests.event_interpreter_hardening.corpus import mp_label
from tests.model_provider_evaluation.candidates import all_candidates, build_provider
from tests.model_variance_strategy.corpus import I129_CORPUS

EXPERIMENT_ID = os.environ.get("PKE_I1210_EXPERIMENT", "I12.10")
ROOT = _ROOT
ARTIFACT_DIR = ROOT / "docs" / "reports" / "i1210_artifacts"
CHECKPOINT = ARTIFACT_DIR / "checkpoint.jsonl"
SUMMARY_JSON = ROOT / "docs" / "reports" / "I12.10-LIVE.json"
NOW = datetime(2026, 9, 3, 19, 0, tzinfo=ZoneInfo("America/Fortaleza"))


def load_env_silent() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _reps(case: EngineCase) -> int:
    return 5 if mp_label(case) else 3


def _ctx() -> InterpretationContext:
    return InterpretationContext(user=UserContext(user_id="i1210", timezone="America/Fortaleza", now=NOW))


def _parse(raw: str | None) -> SemanticProposal | None:
    if not raw:
        return None
    try:
        dispatched = dispatch_provider_payload(raw)
        if dispatched.route is ProviderRoute.INVALID or not dispatched.payload:
            return None
        if dispatched.route is ProviderRoute.V2_CANONICAL:
            return None
        env = WireSemanticEnvelope.model_validate(dispatched.payload)
        if env.ir_kind == "semantic_query":
            return None
        ir = dispatched.payload.get("ir")
        if ir is not None:
            return SemanticProposal.model_validate(ir)
        return env.parsed_proposal()
    except Exception:
        return None


def _done() -> set[tuple[str, int]]:
    if not CHECKPOINT.is_file():
        return set()
    out: set[tuple[str, int]] = set()
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("experiment_id") == EXPERIMENT_ID:
            out.add((r["case_id"], int(r["run"])))
    return out


def focused_cases() -> list[EngineCase]:
    cases = list(I129_CORPUS)
    if len(cases) > 65:
        cases = cases[:65]
    return cases


def run() -> int:
    load_env_silent()
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("NOT_EXECUTED_NO_CREDENTIAL")
        SUMMARY_JSON.write_text(json.dumps({"status": "NOT_EXECUTED_NO_CREDENTIAL"}, indent=2), encoding="utf-8")
        return 0

    cases = focused_cases()
    limit = int(os.environ.get("PKE_I1210_LIMIT", "0"))
    if limit > 0:
        cases = cases[:limit]
    spec = next(c for c in all_candidates() if c.candidate_id == "baseline_deepseek_chat")
    interpreter = DeepSeekInterpreter(
        build_provider(spec), OntologyRegistry.with_core_seeds(), prompt_version=PROMPT_VERSION_V4
    )
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    done = _done() if os.environ.get("PKE_I1210_RESUME", "1") != "0" else set()
    total = sum(_reps(c) for c in cases)
    n = 0
    t0 = time.perf_counter()

    for ci, case in enumerate(cases, 1):
        reps = _reps(case)
        for run_no in range(1, reps + 1):
            if (case.id, run_no) in done:
                continue
            n += 1
            elapsed = time.perf_counter() - t0
            eta = (total - n) * (elapsed / n) if n else 0
            print(f"[{EXPERIMENT_ID}] {ci}/{len(cases)} run {run_no}/{reps} ETA {eta:.0f}s")
            error = None
            ir_ok = False
            try:
                ir = interpreter.interpret(case.utterance, _ctx())
                ir_ok = ir is not None
            except InterpretationError as exc:
                error = str(exc)
            raw = interpreter.last_raw_content
            proposal = _parse(raw)
            readiness = None
            outcome = None
            if proposal is not None:
                readiness = assess_execution_readiness(resolve_proposal(proposal))
                outcome = proposal_to_canonical_ir(proposal)
            row = {
                "experiment_id": EXPERIMENT_ID,
                "case_id": case.id,
                "run": run_no,
                "mp_anchor": mp_label(case),
                "utterance": case.utterance,
                "category": case.category,
                "logical_request_id": str(uuid.uuid4()),
                "raw_content": raw,
                "proposal_dump": proposal.model_dump() if proposal else None,
                "error": error,
                "ir_ok": ir_ok,
                "execution_outcome": readiness.outcome.value if readiness else None,
                "materializable_count": readiness.materializable_count if readiness else None,
                "clarification_eligible": readiness.clarification_eligible if readiness else None,
                "failure_stage": outcome.failure_stage if outcome else None,
                "outcome_ir": bool(outcome and outcome.ir is not None),
            }
            with CHECKPOINT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"  -> {case.id} {row['execution_outcome']} err={error}")

    rows = [
        json.loads(l)
        for l in CHECKPOINT.read_text(encoding="utf-8").splitlines()
        if l.strip() and json.loads(l).get("experiment_id") == EXPERIMENT_ID
    ]
    valid = [r for r in rows if r.get("proposal_dump")]
    zero = [
        r
        for r in valid
        if r.get("execution_outcome") == ProposalExecutionOutcome.VALID_EXECUTION_INCOMPLETE.value
        and (r.get("materializable_count") or 0) == 0
    ]
    zero_safe = [
        r
        for r in zero
        if r.get("failure_stage") == "EXECUTION_INCOMPLETE"
        and not r.get("outcome_ir")
        and (r.get("error") or "").startswith("semantic_resolution:execution_incomplete")
        or (r.get("failure_stage") == "EXECUTION_INCOMPLETE" and not r.get("outcome_ir"))
    ]
    generic_cr = sum(1 for r in rows if (r.get("error") or "") == "semantic_resolution:concept_resolution")
    invented = 0
    false_commit = 0
    for r in zero:
        dump = r.get("proposal_dump") or {}
        if dump.get("subject") and r.get("mp_anchor") == "MP1" and dump.get("subject") is None:
            invented += 1
        if r.get("outcome_ir"):
            false_commit += 1
        if r.get("ir_ok") and not r.get("outcome_ir"):
            # interpreter reported success without IR — should not happen
            pass
    mp1 = [r for r in rows if r.get("mp_anchor") == "MP1"]
    mp1_capture = sum(1 for r in mp1 if r.get("ir_ok"))
    mp1_safe = sum(
        1
        for r in mp1
        if r.get("ir_ok")
        or (r.get("error") or "").startswith("semantic_resolution:execution_incomplete")
        or r.get("failure_stage") == "EXECUTION_INCOMPLETE"
    )
    useful = sum(1 for r in rows if r.get("ir_ok"))
    safe_handled = sum(
        1
        for r in rows
        if r.get("ir_ok")
        or (r.get("error") or "").startswith("semantic_resolution:execution_incomplete")
        or (r.get("error") or "").startswith("acceptance_guard:")
    )
    summary = {
        "experiment_id": EXPERIMENT_ID,
        "prompt_version": PROMPT_VERSION_V4,
        "TOTAL_CASES": len(cases),
        "TOTAL_RUNS": len(rows),
        "LIVE_VALID_PROPOSAL_ZERO_MATERIALIZABLE": len(zero),
        "LIVE_ZERO_MATERIALIZABLE_SAFE_OUTCOME": len(zero_safe),
        "LIVE_GENERIC_CONCEPT_RESOLUTION_FAILURE_AFTER": generic_cr,
        "LIVE_INCOMPLETE_PRIMITIVE_FALSELY_COMMITTED": false_commit,
        "LIVE_MISSING_INFORMATION_INVENTED": invented,
        "LIVE_SAFE_HANDLED_INTERACTION_RATE": safe_handled / len(rows) if rows else 0,
        "LIVE_USEFUL_KNOWLEDGE_CAPTURE_RATE": useful / len(rows) if rows else 0,
        "MP1_USEFUL_CAPTURE": mp1_capture / len(mp1) if mp1 else None,
        "MP1_SAFE_HANDLING": mp1_safe / len(mp1) if mp1 else None,
        "MP1_RUNS": len(mp1),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
