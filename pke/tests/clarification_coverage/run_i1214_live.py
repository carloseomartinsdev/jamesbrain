"""I12.14 Stage B — clarification coverage on I12.11 baseline proposals.

Reuses frozen proposals (no provider recall). Clarification answers are fixtures.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pke.application.clarification_recovery import ClarificationRecoveryService, RecoveryStatus
from pke.application.ingest import IngestService
from pke.application.pending_operation import PendingSemanticOperation
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.capability_strategy import decide_capability
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.semantic.pipeline import resolve_proposal
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.sqlite.engine import create_sqlite_engine, init_database, session_factory
from pke.persist.sqlite.uow import SqliteUnitOfWork
from pke.resolution import PersonalContext

I1211 = _ROOT / "docs" / "reports" / "i1211_artifacts" / "checkpoint.jsonl"
OUT = _ROOT / "docs" / "reports" / "I12.14-CLARIFICATION-COVERAGE-EXPANSION.json"
ART = _ROOT / "docs" / "reports" / "i1214_artifacts"

# Frozen clarification answers (fixtures) — not reinterpretation of original utterance.
ANSWER_FIXTURES: dict[str, str] = {
    "measured_entity": "entidade-medida",
    "relation_subject": "Alice",
    "relation_object": "Acme",
    "state_entity": "porta-principal",
    "attribute_entity": "corolla",
    "measurement_dimension": "temperatura",
    "attribute_dimension": "cor",
    "state_value": "fechado",
}


class FixedClock:
    def now(self):
        return dt.datetime(2026, 9, 3, 19, 0, tzinfo=dt.UTC)


def _answer_for(slot: str, case_id: str, run: int, mp: str | None) -> str:
    if mp == "MP1" and slot in {"measured_entity", "state_entity", "attribute_entity"}:
        return "O tanque do Corolla."
    if slot in ANSWER_FIXTURES:
        base = ANSWER_FIXTURES[slot]
        if slot.endswith("_entity") or slot in {"relation_subject", "relation_object", "measured_entity"}:
            return f"{base}-{case_id}-{run}"
        return base
    return f"fixture-{slot}"


def run() -> int:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    ART.mkdir(parents=True, exist_ok=True)
    db = ART / "recovery_live.db"
    if db.exists():
        db.unlink()
    engine = create_sqlite_engine(f"sqlite:///{db}")
    init_database(engine)
    factory = session_factory(engine)
    spy = FakeInterpreter({})
    ingest = IngestService(
        spy,  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: SqliteUnitOfWork(factory),
        FixedClock(),
    )
    recovery = ClarificationRecoveryService(ingest)

    rows = []
    for line in I1211.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("candidate_id") != "baseline_deepseek_chat":
            continue
        rows.append(r)

    eligible = 0
    supported = 0
    success = 0
    unresolved = 0
    unsupported = 0
    invalid = 0
    autonomous = sum(1 for r in rows if r.get("useful_capture"))
    recovered_ids: set[str] = set()
    slot_counts: Counter[str] = Counter()
    slot_success: Counter[str] = Counter()
    slot_unsupported: Counter[str] = Counter()
    by_cat: dict[str, Counter[str]] = defaultdict(Counter)
    mp1_auto = 0
    mp1_elig = 0
    mp1_rec = 0
    mp1_n = 0
    safety = Counter()
    i1213_unsupported_now_covered = 0

    for r in rows:
        dump = r.get("proposal_dump")
        if not dump:
            continue
        proposal = SemanticProposal.model_validate(dump)
        readiness = assess_execution_readiness(resolve_proposal(proposal))
        decision = decide_capability(readiness)
        mp = r.get("mp_anchor")
        cat = r.get("category") or "unknown"
        if mp == "MP1":
            mp1_n += 1
            if r.get("useful_capture"):
                mp1_auto += 1
        if decision.outcome.value != "clarify" or decision.clarification is None:
            if r.get("useful_capture"):
                by_cat[cat]["autonomous_success"] += 1
            continue
        eligible += 1
        slot = decision.clarification.missing_slot
        kind = decision.clarification.expected_answer_kind
        slot_counts[slot] += 1
        if mp == "MP1":
            mp1_elig += 1
        pending = PendingSemanticOperation(
            originating_raw=r["utterance"],
            proposal_dump=dump,
            missing_slot=slot,
            expected_answer_kind=kind,
            primitive=decision.clarification.primitive.value,
            reason=decision.clarification.reason,
            question_key=decision.clarification.question_key,
        )
        if not pending.is_supported():
            unsupported += 1
            slot_unsupported[slot] += 1
            by_cat[cat]["recoverable_unsupported"] += 1
            continue
        supported += 1
        # Was unsupported in I12.13 (non-entity)?
        if kind != "entity_reference":
            i1213_unsupported_now_covered += 1
        answer = _answer_for(slot, r["case_id"], r["run"], mp)
        user = UserContext(user_id=f"live14-{r['case_id']}-{r['run']}", timezone="America/Fortaleza")
        session = SessionContext(personal=PersonalContext(user_id=user.user_id))
        result = recovery.recover(pending, answer, user, session)
        for key, flag in (
            ("ORIGINAL_RAW_TEXT_REINTERPRETED", result.trace.original_raw_reinterpreted),
            ("FULL_INTERPRETER_CALLED_DURING_RECOVERY", result.trace.interpreter_called),
            ("NON_TARGET_SLOT_MUTATED", result.trace.non_target_slot_mutated),
            ("UNRELATED_PRIMITIVE_ADDED", result.trace.unrelated_primitive_added),
            ("MISSING_INFORMATION_INVENTED", result.trace.missing_information_invented),
            ("RECOVERY_DUPLICATE_TARGET_COMMIT", result.trace.duplicate_target_commit),
            ("RECOVERY_DUPLICATE_SIBLING_COMMIT", result.trace.duplicate_sibling_commit),
        ):
            if flag:
                safety[key] += 1
        if result.status is RecoveryStatus.RESOLVED_COMMITTED:
            success += 1
            slot_success[slot] += 1
            by_cat[cat]["recoverable_supported_success"] += 1
            if not r.get("useful_capture"):
                recovered_ids.add(f"{r['case_id']}:{r['run']}")
            if mp == "MP1":
                mp1_rec += 1
        elif result.status is RecoveryStatus.UNSUPPORTED_SLOT:
            unsupported += 1
            slot_unsupported[slot] += 1
            by_cat[cat]["recoverable_unsupported"] += 1
        elif result.status is RecoveryStatus.INVALID_ANSWER:
            invalid += 1
            unresolved += 1
            by_cat[cat]["recoverable_supported_unresolved"] += 1
        else:
            unresolved += 1
            by_cat[cat]["recoverable_supported_unresolved"] += 1

    n = len(rows) or 1
    recovered = len(recovered_ids)
    total_after = autonomous + recovered
    supported_coverage = supported / eligible if eligible else 0.0
    recovery_success_rate = success / supported if supported else 0.0
    effective = supported_coverage * recovery_success_rate

    summary = {
        "experiment_id": "I12.14",
        "CLARIFICATION_RECOVERY_AUTHORITY": "ClarificationRecoveryService",
        "SUPPORTED_RECOVERY_SLOT_KINDS": ["entity_reference", "dimension", "value"],
        "UNSUPPORTED_RECOVERY_SLOT_KINDS": ["correction_target", "temporal", "state_dimension", "measurement_value"],
        "MAX_CLARIFICATION_ROUNDS_PER_PENDING_OPERATION": 1,
        "LIVE_TOTAL_RUNS": len(rows),
        "LIVE_CLARIFICATION_ELIGIBLE": eligible,
        "LIVE_CLARIFICATION_ELIGIBLE_RATE": eligible / n,
        "LIVE_RECOVERY_SLOT_SUPPORTED": supported,
        "LIVE_SUPPORTED_CLARIFICATION_COVERAGE_RATE": supported_coverage,
        "LIVE_RECOVERY_SUCCESS": success,
        "LIVE_SUPPORTED_RECOVERY_SUCCESS_RATE": recovery_success_rate,
        "LIVE_RECOVERY_UNRESOLVED": unresolved,
        "LIVE_RECOVERY_UNSUPPORTED": unsupported,
        "LIVE_RECOVERY_INVALID": invalid,
        "LIVE_EFFECTIVE_CLARIFICATION_RECOVERY_RATE": effective,
        "LIVE_AUTONOMOUS_USEFUL_CAPTURE_RATE": autonomous / n,
        "LIVE_RECOVERED_USEFUL_CAPTURE_RATE": recovered / n,
        "LIVE_TOTAL_USEFUL_CAPTURE_AFTER_BOUNDED_RECOVERY": total_after / n,
        "CLARIFICATIONS_PER_100_INTERACTIONS": (eligible / n) * 100,
        "UNSUPPORTED_CLARIFICATIONS_PER_100_INTERACTIONS": (unsupported / n) * 100,
        "I12_13_UNSUPPORTED_NOW_SLOT_SUPPORTED": i1213_unsupported_now_covered,
        "I12_13_UNSUPPORTED_BASELINE": 66,
        "HOW_MANY_OF_THE_I12_13_UNSUPPORTED_GAPS_ARE_NOW_COVERED": f"{i1213_unsupported_now_covered}/66",
        "SLOT_COUNTS": dict(slot_counts),
        "SLOT_SUCCESS": dict(slot_success),
        "SLOT_UNSUPPORTED": dict(slot_unsupported),
        "BY_CATEGORY": {k: dict(v) for k, v in by_cat.items()},
        "SAFETY": dict(safety),
        "MP1_RUNS": mp1_n,
        "MP1_INITIAL_AUTONOMOUS_CAPTURE": (mp1_auto / mp1_n) if mp1_n else None,
        "MP1_CLARIFICATION_ELIGIBLE": (mp1_elig / mp1_n) if mp1_elig else None,
        "MP1_RECOVERY_SUCCESS": (mp1_rec / mp1_elig) if mp1_elig else None,
        "MP1_TOTAL_CAPTURE_AFTER_RECOVERY": ((mp1_auto + mp1_rec) / mp1_n) if mp1_n else None,
        "MP1_ORIGINAL_RAW_REINTERPRETED": safety.get("ORIGINAL_RAW_TEXT_REINTERPRETED", 0),
        "FULL_INTERPRETER_CALLED_DURING_RECOVERY": safety.get(
            "FULL_INTERPRETER_CALLED_DURING_RECOVERY", 0
        ),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "Knowledge_Core_v1": "FROZEN",
        "schema": "v10",
        "CORE": 67,
        "prompt": "v4",
        "model": "deepseek-chat (baseline reuse)",
    }
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (ART / "live_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
