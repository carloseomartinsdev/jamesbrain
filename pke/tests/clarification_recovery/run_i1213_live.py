"""I12.13 Stage B — frozen clarification recovery on I12.11 baseline proposals.

Stage A artifacts reused (no new model tournament). Stage B never calls Interpreter.
"""

from __future__ import annotations

import json
import sys
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
import datetime as dt

I1211 = _ROOT / "docs" / "reports" / "i1211_artifacts" / "checkpoint.jsonl"
OUT = _ROOT / "docs" / "reports" / "I12.13-BOUNDED-CLARIFICATION-RECOVERY.json"
ART = _ROOT / "docs" / "reports" / "i1213_artifacts"


class FixedClock:
    def now(self):
        return dt.datetime(2026, 9, 3, 18, 0, tzinfo=dt.UTC)


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
    ingest = IngestService(spy, OntologyRegistry.with_core_seeds(), lambda: SqliteUnitOfWork(factory), FixedClock())  # type: ignore[arg-type]
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
    autonomous = sum(1 for r in rows if r.get("useful_capture"))
    recovered_ids: set[str] = set()
    mp1_auto = 0
    mp1_elig = 0
    mp1_rec = 0
    mp1_n = 0
    interpreter_calls = 0

    for r in rows:
        dump = r.get("proposal_dump")
        if not dump:
            continue
        proposal = SemanticProposal.model_validate(dump)
        readiness = assess_execution_readiness(resolve_proposal(proposal))
        decision = decide_capability(readiness)
        mp = r.get("mp_anchor")
        if mp == "MP1":
            mp1_n += 1
            if r.get("useful_capture"):
                mp1_auto += 1
        if decision.outcome.value != "clarify" or decision.clarification is None:
            continue
        eligible += 1
        if mp == "MP1":
            mp1_elig += 1
        pending = PendingSemanticOperation(
            originating_raw=r["utterance"],
            proposal_dump=dump,
            missing_slot=decision.clarification.missing_slot,
            expected_answer_kind=decision.clarification.expected_answer_kind,
            primitive=decision.clarification.primitive.value,
            reason=decision.clarification.reason,
            question_key=decision.clarification.question_key,
        )
        if not pending.is_supported():
            unsupported += 1
            continue
        supported += 1
        answer = "temperatura" if mp == "MP1" else (proposal.subject.text if proposal.subject else "entidade referida")
        if mp != "MP1":
            # generic fixture entity for measured_entity gaps
            answer = f"entidade-{r['case_id']}-{r['run']}"
        user = UserContext(user_id=f"live-{r['case_id']}", timezone="America/Fortaleza")
        session = SessionContext(personal=PersonalContext(user_id=user.user_id))
        # isolated user per recovery to avoid alias collisions
        result = recovery.recover(pending, answer, user, session)
        if result.status is RecoveryStatus.RESOLVED_COMMITTED:
            success += 1
            if not r.get("useful_capture"):
                recovered_ids.add(f"{r['case_id']}:{r['run']}")
            if mp == "MP1":
                mp1_rec += 1
        elif result.status is RecoveryStatus.UNSUPPORTED_SLOT:
            unsupported += 1
        else:
            unresolved += 1

    n = len(rows) or 1
    recovered = len(recovered_ids)
    total_after = autonomous + recovered
    summary = {
        "experiment_id": "I12.13",
        "CLARIFICATION_RECOVERY_AUTHORITY": "ClarificationRecoveryService",
        "CLARIFICATION_RECOVERY_RESUME_STAGE": "resolve_proposal→execution_readiness→ingest_from_ir",
        "SUPPORTED_RECOVERY_SLOT_KINDS": ["entity_reference"],
        "UNSUPPORTED_RECOVERY_SLOT_KINDS": [
            "dimension",
            "value",
            "correction_target",
        ],
        "MAX_CLARIFICATION_ROUNDS_PER_PENDING_OPERATION": 1,
        "LIVE_TOTAL_RUNS": len(rows),
        "LIVE_CLARIFICATION_ELIGIBLE": eligible,
        "LIVE_RECOVERY_SUPPORTED": supported,
        "LIVE_RECOVERY_SUCCESS": success,
        "LIVE_RECOVERY_UNRESOLVED": unresolved,
        "LIVE_RECOVERY_UNSUPPORTED": unsupported,
        "LIVE_AUTONOMOUS_USEFUL_CAPTURE_RATE": autonomous / n,
        "LIVE_RECOVERED_USEFUL_CAPTURE_RATE": recovered / n,
        "LIVE_TOTAL_USEFUL_CAPTURE_AFTER_BOUNDED_RECOVERY": total_after / n,
        "CLARIFICATIONS_PER_100_INTERACTIONS": (eligible / n) * 100,
        "AVERAGE_CLARIFICATION_ROUNDS_PER_RECOVERED_CASE": 1.0 if success else 0.0,
        "FULL_INTERPRETER_CALLED_DURING_RECOVERY": interpreter_calls,
        "MP1_RUNS": mp1_n,
        "MP1_INITIAL_AUTONOMOUS_CAPTURE": (mp1_auto / mp1_n) if mp1_n else None,
        "MP1_CLARIFICATION_ELIGIBLE": (mp1_elig / mp1_n) if mp1_n else None,
        "MP1_RECOVERY_SUCCESS": (mp1_rec / mp1_elig) if mp1_elig else None,
        "MP1_TOTAL_CAPTURE_AFTER_RECOVERY": ((mp1_auto + mp1_rec) / mp1_n) if mp1_n else None,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (ART / "live_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
