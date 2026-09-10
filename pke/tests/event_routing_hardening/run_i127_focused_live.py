"""I12.7-R focused live validation — Event preservation + fallback audit.

Usage:
  .\\.venv\\Scripts\\python.exe -m tests.event_routing_hardening.run_i127_focused_live

Env:
  DEEPSEEK_API_KEY required
  PKE_I127_LIMIT=0 (>0 truncates)
  PKE_I127_RESUME=1 (default)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "src", _ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.semantic.envelope_dispatch import ProviderRoute, dispatch_provider_payload
from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.event_preservation import (
    event_false_canonicalization,
    event_semantically_preserved,
)
from pke.interpretation.semantic.multi_primitive_evidence import (
    has_explicit_occurrence_evidence,
    has_measurement_evidence,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.router import collect_assertions
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION

from tests.engine_v1_baseline.corpus import CORPUS, EngineCase
from tests.event_routing_hardening.stage_trace import trace_event_routing
from tests.model_provider_evaluation.candidates import all_candidates, build_provider

EXPERIMENT_ID = os.environ.get("PKE_I127_EXPERIMENT", "I12.7-R")
ROOT = _ROOT
ARTIFACT_DIR = ROOT / "docs" / "reports" / "i127_artifacts"
CHECKPOINT = ARTIFACT_DIR / "checkpoint.jsonl"
FREEZE_JSON = ARTIFACT_DIR / "FREEZE.json"
SUMMARY_JSON = ROOT / "docs" / "reports" / "I12.7-R-FOCUSED-LIVE.json"
SUMMARY_MD = ROOT / "docs" / "reports" / "I12.7-R-FOCUSED-LIVE.md"
FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = datetime(2026, 9, 3, 15, 0, tzinfo=FORTALEZA)

# MP anchors by utterance prefix (baseline corpus uses MS## ids)
MP5_PREFIX = "o sensor mediu 38"
MP_PREFIXES: tuple[tuple[str, str], ...] = (
    ("MP1", "medi a temperatura e deu 95"),
    ("MP2", "olhei o tanque e ele estava com 20 litros"),
    ("MS18", "olhei o tanque e ele estava com 20 litros"),
    ("MP3", "pesei a caixa"),
    ("MP4", "consultei o saldo"),
    ("MP5", MP5_PREFIX),
)


def load_env_silent() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def focused_corpus(*, mp_only: bool = False) -> list[EngineCase]:
    mp_first: list[EngineCase] = []
    rest: list[EngineCase] = []
    seen_mp: set[str] = set()
    for case in CORPUS:
        label = _mp_label(case)
        if label and label not in seen_mp:
            mp_first.append(case)
            seen_mp.add(label)
            continue
        if mp_only:
            continue
        if case.category in {"multi_primitive", "measurement", "event"}:
            rest.append(case)
        elif case.category in {"state", "relation"} and case.severity_if_wrong in {"S2", "S3"}:
            rest.append(case)
    if mp_only:
        return mp_first
    by_id: dict[str, EngineCase] = {}
    for case in mp_first + rest:
        by_id.setdefault(case.id, case)
    ordered = list(by_id.values())
    # MP anchors always included; cap remainder at ~65 total
    if len(ordered) > 65:
        mp_ids = {c.id for c in mp_first}
        tail = [c for c in ordered if c.id not in mp_ids][: max(0, 65 - len(mp_first))]
        ordered = mp_first + tail
    return ordered


def _mp_label(case: EngineCase) -> str | None:
    u = case.utterance.casefold()
    for label, prefix in MP_PREFIXES:
        if u.startswith(prefix.casefold()):
            return label
    return None


def _reps_for(case: EngineCase) -> int:
    return 5 if _mp_label(case) else 3


def corpus_fingerprint(cases: list[EngineCase]) -> str:
    blob = "\n".join(f"{c.id}\t{c.utterance}\t{c.category}" for c in cases)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _git_commit() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return None


def write_freeze(cases: list[EngineCase], spec_model: str) -> dict:
    freeze = {
        "experiment_id": EXPERIMENT_ID,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "prompt_version": PROMPT_VERSION_V4,
        "provider": "deepseek",
        "model": spec_model,
        "temperature": None,
        "top_p": None,
        "max_tokens": None,
        "retry_policy": "Interpreter RetryPolicy unchanged (I12.2)",
        "semantic_proposal": "unchanged",
        "wire": "unchanged",
        "schema": STORAGE_SCHEMA_VERSION,
        "core_version": 65,
        "corpus_fingerprint": corpus_fingerprint(cases),
        "corpus_size": len(cases),
        "logical_requests": sum(_reps_for(c) for c in cases),
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    FREEZE_JSON.write_text(json.dumps(freeze, indent=2), encoding="utf-8")
    return freeze


def _ctx() -> InterpretationContext:
    return InterpretationContext(
        user=UserContext(user_id="i127r-live", timezone="America/Fortaleza", now=NOW)
    )


def _try_parse_proposal(raw: str | None) -> SemanticProposal | None:
    if not raw:
        return None
    try:
        dispatched = dispatch_provider_payload(raw)
        if dispatched.route is ProviderRoute.INVALID or dispatched.payload is None:
            return None
        if dispatched.route is ProviderRoute.V2_CANONICAL:
            return None
        env = WireSemanticEnvelope.model_validate(dispatched.payload)
        if env.ir_kind == "semantic_query":
            return None
        return env.parsed_proposal()
    except Exception:  # noqa: BLE001
        return None


def _proposal_event(proposal: SemanticProposal) -> bool:
    return has_explicit_occurrence_evidence(proposal)


def _assertion_event(proposal: SemanticProposal) -> bool:
    return any(f.primitive is PrimitiveKind.EVENT for f in collect_assertions(proposal))


def _audit_event_intent(outcome, trace) -> dict:
    if outcome is None:
        return {}
    assigned = None
    if outcome.ir and outcome.ir.event is not None:
        assigned = outcome.ir.event.type.key if outcome.ir.event.type else None
    non_mat = PrimitiveKind.EVENT in outcome.result.non_materialized_primitives
    false_canon = event_false_canonicalization(outcome)
    return {
        "EVENT_TYPE_ASSIGNED": assigned,
        "NON_MATERIALIZED_EVENT": non_mat,
        "SEMANTICALLY_PRESERVED": event_semantically_preserved(outcome),
        "FALSE_CANONICALIZATION": false_canon,
    }


def _completed_keys() -> set[tuple[str, int]]:
    if not CHECKPOINT.is_file():
        return set()
    done: set[tuple[str, int]] = set()
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("experiment_id") == EXPERIMENT_ID:
            done.add((row["case_id"], int(row["run"])))
    return done


def _ledger_dict(ledger) -> dict:
    return {
        "primitive": ledger.primitive,
        "action": ledger.action,
        "entity_object": ledger.entity_object,
        "measurement_dimension": ledger.measurement_dimension,
        "materializable": ledger.materializable,
        "event_present": ledger.event_present,
        "measurement_present": ledger.measurement_present,
        "non_materialized": ledger.non_materialized,
        "notes": list(ledger.notes),
    }


def run() -> int:
    load_env_silent()
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("NOT_EXECUTED_NO_CREDENTIAL")
        SUMMARY_JSON.write_text(
            json.dumps({"status": "NOT_EXECUTED_NO_CREDENTIAL"}, indent=2),
            encoding="utf-8",
        )
        return 0

    cases = focused_corpus(mp_only=os.environ.get("PKE_I127_MP_ONLY", "0") == "1")
    limit = int(os.environ.get("PKE_I127_LIMIT", "0"))
    if limit > 0:
        cases = cases[:limit]

    spec = next(c for c in all_candidates() if c.candidate_id == "baseline_deepseek_chat")
    freeze = write_freeze(cases, spec.model)
    provider = build_provider(spec)
    interpreter = DeepSeekInterpreter(provider, OntologyRegistry.with_core_seeds())
    done = _completed_keys() if os.environ.get("PKE_I127_RESUME", "1") != "0" else set()

    total_logical = sum(_reps_for(c) for c in cases)
    completed = len(done)
    t_start = time.perf_counter()
    provider_calls = 0
    retries = 0
    metrics: Counter[str] = Counter()

    for ci, case in enumerate(cases, start=1):
        reps = _reps_for(case)
        mp = _mp_label(case)
        for run in range(1, reps + 1):
            if (case.id, run) in done:
                continue
            logical_done = completed + 1
            elapsed = time.perf_counter() - t_start
            rate = logical_done / elapsed if elapsed > 0 else 0
            remaining = total_logical - logical_done
            eta_s = remaining / rate if rate > 0 else 0
            print(
                f"[{EXPERIMENT_ID}] case {ci}/{len(cases)} | run {run}/{reps} | "
                f"logical {logical_done}/{total_logical} | calls {provider_calls} | "
                f"retries {retries} | elapsed {elapsed:.0f}s | ETA {eta_s:.0f}s"
            )

            logical_id = str(uuid.uuid4())
            t0 = time.perf_counter()
            raw_content = None
            proposal = None
            error = None
            attempts = 1
            try:
                interpreter.interpret(case.utterance, _ctx())
                attempts = interpreter.last_provider_attempts or 1
                provider_calls += attempts
                raw_content = interpreter.last_raw_content
                proposal = _try_parse_proposal(raw_content)
            except InterpretationError as exc:
                error = str(exc)
                retries += 1

            latency_ms = (time.perf_counter() - t0) * 1000
            prop_e = _proposal_event(proposal) if proposal else False
            asrt_e = _assertion_event(proposal) if proposal else False

            trace = trace_event_routing(proposal, case_id=case.id) if proposal else None
            outcome = proposal_to_canonical_ir(proposal) if proposal else None

            res_e = trace.resolution_event_present if trace else False
            mat_e = trace.materialization_event_present if trace else False
            final_e = trace.final_event_present if trace else False
            prop_m = has_measurement_evidence(proposal) if proposal else False
            final_m = bool(outcome and outcome.ir and outcome.ir.measurement is not None)

            if prop_e and not final_e:
                metrics["RAW_EVENT_PRESENT_POST_EVENT_LOST"] += 1
            if prop_e and final_e:
                metrics["POST_EVENT_CORRECT"] += 1
            if prop_e:
                metrics["RAW_MODEL_EVENT_CORRECT"] += 1
            elif proposal and case.expected_primitive in {"multi", "event"}:
                metrics["RAW_MODEL_EVENT_OMISSION"] += 1
            if not prop_e and final_e:
                metrics["RAW_MODEL_FALSE_EXTRA_EVENT"] += 1
            if prop_m and not final_m:
                metrics["MEASUREMENT_LOST"] += 1
            if prop_m and final_m:
                metrics["MEASUREMENT_PRESERVED"] += 1

            audit = _audit_event_intent(outcome, trace) if proposal else {}
            if audit.get("FALSE_CANONICALIZATION"):
                metrics["EVENT_PARTIAL_FALSE_CANONICALIZATION"] += 1
            if audit.get("NON_MATERIALIZED_EVENT") and prop_e:
                metrics["LIVE_PARTIAL_EVENT_PRESERVED_NON_MATERIALIZED"] += 1
            if prop_m and final_m and audit.get("NON_MATERIALIZED_EVENT"):
                metrics["LIVE_MEASUREMENT_MATERIALIZED_WITH_PARTIAL_EVENT"] += 1

            row = {
                "experiment_id": EXPERIMENT_ID,
                "case_id": case.id,
                "mp_anchor": mp,
                "run": run,
                "utterance": case.utterance,
                "category": case.category,
                "logical_request_id": logical_id,
                "attempts": attempts,
                "latency_ms": latency_ms,
                "raw_content": raw_content,
                "proposal_dump": proposal.model_dump() if proposal else None,
                "PROPOSAL_EVENT_PRESENT": prop_e,
                "ASSERTION_EVENT_PRESENT": asrt_e,
                "RESOLUTION_EVENT_PRESENT": res_e,
                "MATERIALIZATION_EVENT_PRESENT": mat_e,
                "FINAL_EVENT_PRESENT": final_e,
                "PROPOSAL_MEASUREMENT_PRESENT": prop_m,
                "FINAL_MEASUREMENT_PRESENT": final_m,
                "canonicalization_audit": audit,
                "stages": {
                    "S4": _ledger_dict(trace.s4_collected_assertions) if trace else None,
                    "S5": _ledger_dict(trace.s5_resolution_result) if trace else None,
                    "S6": _ledger_dict(trace.s6_materialization_input) if trace else None,
                    "S7": _ledger_dict(trace.s7_materialization_result) if trace else None,
                    "S8": _ledger_dict(trace.s8_engine_outcome) if trace else None,
                },
                "error": error,
            }
            with CHECKPOINT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            completed += 1
            print(
                f"  -> {case.id} mp={mp} prop_E={prop_e} post_E={final_e} "
                f"type={audit.get('EVENT_TYPE_ASSIGNED')}"
            )

    # Aggregate from full checkpoint
    rows = []
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("experiment_id") == EXPERIMENT_ID:
                rows.append(r)

    prop_e_rows = [r for r in rows if r.get("PROPOSAL_EVENT_PRESENT")]
    prop_m_rows = [r for r in rows if r.get("PROPOSAL_MEASUREMENT_PRESENT")]
    preserved_e = sum(1 for r in prop_e_rows if r.get("FINAL_EVENT_PRESENT"))
    preserved_m = sum(1 for r in prop_m_rows if r.get("FINAL_MEASUREMENT_PRESENT"))

    summary = {
        **freeze,
        "LIVE_CASES": len(cases),
        "LIVE_LOGICAL_REQUESTS": total_logical,
        "RUNS_COMPLETED": len(rows),
        "PROVIDER_CALLS": provider_calls,
        "RETRIES": retries,
        "RAW_MODEL_EVENT_CORRECT": sum(1 for r in rows if r.get("PROPOSAL_EVENT_PRESENT")),
        "RAW_MODEL_EVENT_OMISSION": metrics["RAW_MODEL_EVENT_OMISSION"],
        "RAW_MODEL_FALSE_EXTRA_EVENT": metrics["RAW_MODEL_FALSE_EXTRA_EVENT"],
        "RAW_EVENT_PRESENT_POST_EVENT_LOST": sum(
            1
            for r in rows
            if r.get("PROPOSAL_EVENT_PRESENT") and not r.get("FINAL_EVENT_PRESENT")
        ),
        "LIVE_EXPLICIT_EVENT_PRESERVATION_RATE": (
            preserved_e / len(prop_e_rows) if prop_e_rows else None
        ),
        "LIVE_EXPLICIT_MEASUREMENT_PRESERVATION_RATE": (
            preserved_m / len(prop_m_rows) if prop_m_rows else None
        ),
        "POST_EVENT_CORRECT": sum(
            1 for r in rows if r.get("PROPOSAL_EVENT_PRESENT") and r.get("FINAL_EVENT_PRESENT")
        ),
        "POST_EVENT_SAFE_PARTIAL": sum(
            1
            for r in rows
            if (r.get("canonicalization_audit") or {}).get("EVENT_TYPE_ASSIGNED")
            == "event.intent"
        ),
        "EVENT_PARTIAL_FALSE_CANONICALIZATION": sum(
            1
            for r in rows
            if (r.get("canonicalization_audit") or {}).get("EVENT_TYPE_ASSIGNED")
            == "event.intent"
        ),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    SUMMARY_MD.write_text(
        "\n".join(
            [
                "# I12.7-R Focused Live Summary",
                "",
                f"- RAW_EVENT_PRESENT_POST_EVENT_LOST: {summary['RAW_EVENT_PRESENT_POST_EVENT_LOST']}",
                f"- LIVE_EXPLICIT_EVENT_PRESERVATION_RATE: {summary['LIVE_EXPLICIT_EVENT_PRESERVATION_RATE']}",
                f"- EVENT_PARTIAL_FALSE_CANONICALIZATION: {summary['EVENT_PARTIAL_FALSE_CANONICALIZATION']}",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
