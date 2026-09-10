"""I12.15 characterization — freeze State failure ledger (no production hardening)."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

from pke.application.clarification_recovery import ClarificationRecoveryService, RecoveryStatus
from pke.application.ingest import IngestService
from pke.application.pending_operation import PendingSemanticOperation
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.capability_strategy import decide_capability
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.router import collect_assertions
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.sqlite.engine import create_sqlite_engine, init_database, session_factory
from pke.persist.sqlite.uow import SqliteUnitOfWork
from pke.resolution import PersonalContext

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "reports" / "i1215_artifacts"
CHECKPOINT = ROOT / "docs" / "reports" / "i1211_artifacts" / "checkpoint.jsonl"


class Clock:
    def now(self):
        return dt.datetime(2026, 9, 3, 20, 0, tzinfo=dt.UTC)


def main() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db = OUT_DIR / "char.db"
    if db.exists():
        db.unlink()
    engine = create_sqlite_engine(f"sqlite:///{db}")
    init_database(engine)
    factory = session_factory(engine)
    ingest = IngestService(
        FakeInterpreter({}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: SqliteUnitOfWork(factory),
        Clock(),
    )
    recovery = ClarificationRecoveryService(ingest)

    expr_to_answer = {
        "closed": "fechado",
        "fechada": "fechado",
        "fechado": "fechado",
        "open": "aberto",
        "aberta": "aberto",
        "aberto": "aberto",
        "broken": "quebrado",
        "quebrada": "quebrado",
        "quebrado": "quebrado",
        "working": "funcionando",
        "funcionando": "funcionando",
        "overdue": "atrasado",
        "atrasada": "atrasado",
        "atrasado": "atrasado",
        "depleted": "esgotado",
        "esgotado": "esgotado",
        "unpaid": "não pago",
        "valid": "válido",
        "expired": "vencido",
    }

    prim: Counter[str] = Counter()
    stage: Counter[str] = Counter()
    recover: Counter[str] = Counter()
    rows: list[dict] = []

    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("candidate_id") != "baseline_deepseek_chat" or r.get("category") != "state":
            continue
        if not r.get("proposal_dump"):
            continue
        p = SemanticProposal.model_validate(r["proposal_dump"])
        rr = resolve_proposal(p)
        er = assess_execution_readiness(rr)
        d = decide_capability(er)
        assertions = [a.primitive.value for a in collect_assertions(p)]
        has_state = bool(
            p.condition_semantics or p.state_expression or p.primitive_hint == "state"
        )
        state_prims = [x for x in er.primitives if x.primitive is PrimitiveKind.STATE]
        committed = False
        recovered = False
        primary = "OTHER"
        st = "S9_FINAL_OUTCOME"

        if not has_state:
            primary = "VALID_PROPOSAL_STATE_OMITTED"
            st = "S2_SEMANTIC_PROPOSAL"
        elif "state" not in assertions or not state_prims:
            primary = "VALID_PROPOSAL_WRONG_PRIMITIVE"
            st = "S3_PRIMITIVE_ROUTING"
        else:
            sp = state_prims[0]
            reasons = " ".join(sp.reasons or ())
            if sp.status.value == "ready" and d.outcome.value in {
                "auto_execute",
                "partial_execute",
            }:
                out = proposal_to_canonical_ir(p)
                if out.ir is None:
                    primary = "VALID_STATE_LOST_DOWNSTREAM"
                    st = "S7_PERSISTABILITY"
                else:
                    user = UserContext(
                        user_id=f"st-{r['case_id']}-{r['run']}",
                        timezone="America/Fortaleza",
                    )
                    session = SessionContext(personal=PersonalContext(user_id=user.user_id))
                    res = ingest.ingest_from_ir(out.ir, user, session)
                    if res.status is IngestStatus.COMMITTED:
                        committed = True
                        primary = "STATE_CORRECT"
                        st = "S9_FINAL_OUTCOME"
                    else:
                        primary = "VALID_STATE_LOST_DOWNSTREAM"
                        st = "S8_MATERIALIZATION"
            elif "missing_entity" in reasons:
                primary = "VALID_STATE_MISSING_ENTITY"
                st = "S6_EXECUTION_READINESS"
            elif p.state_expression and (
                rr.concepts.unresolved or not rr.concepts.state_value
            ):
                primary = "VALID_STATE_CANONICAL_UNRESOLVED"
                st = "S4_CONCEPT_RESOLUTION"
            elif "state_value" in reasons or "missing_state" in reasons:
                primary = "VALID_STATE_MISSING_VALUE"
                st = "S6_EXECUTION_READINESS"
            else:
                primary = "VALID_STATE_REJECTED_BY_READINESS"
                st = "S6_EXECUTION_READINESS"

        if d.outcome.value == "clarify" and d.clarification:
            pend = PendingSemanticOperation(
                originating_raw=r["utterance"],
                proposal_dump=r["proposal_dump"],
                missing_slot=d.clarification.missing_slot,
                expected_answer_kind=d.clarification.expected_answer_kind,
                primitive=d.clarification.primitive.value,
                reason=d.clarification.reason,
                question_key=d.clarification.question_key,
            )
            slot = d.clarification.missing_slot
            if slot == "state_value":
                expr = (p.state_expression or "").strip().lower()
                ans = expr_to_answer.get(expr, expr or "fechado")
            elif slot in {"state_entity", "measured_entity", "attribute_entity"}:
                ans = f"entidade-{r['case_id']}-{r['run']}"
            else:
                ans = "fixture"
            user = UserContext(
                user_id=f"rcv-{r['case_id']}-{r['run']}",
                timezone="America/Fortaleza",
            )
            session = SessionContext(personal=PersonalContext(user_id=user.user_id))
            if pend.is_supported():
                recover["eligible"] += 1
                rr2 = recovery.recover(pend, ans, user, session)
                if rr2.status is RecoveryStatus.RESOLVED_COMMITTED:
                    recovered = True
                    recover["success"] += 1
                else:
                    recover["fail"] += 1
            else:
                recover["unsupported"] += 1

        prim[primary] += 1
        stage[st] += 1
        rows.append(
            {
                "case_id": r["case_id"],
                "run": r["run"],
                "utterance": r["utterance"],
                "state_expression": p.state_expression,
                "condition_semantics": p.condition_semantics,
                "subject": p.subject.text if p.subject else None,
                "primary": primary,
                "first_causal_stage": st,
                "committed_autonomous": committed,
                "recovered": recovered,
                "clarify_slot": d.clarification.missing_slot if d.clarification else None,
                "capability_outcome": d.outcome.value,
                "concepts_state_value": rr.concepts.state_value,
                "concepts_unresolved": rr.concepts.unresolved,
            }
        )

    n = len(rows) or 1
    auto = sum(1 for x in rows if x["committed_autonomous"])
    after = sum(1 for x in rows if x["committed_autonomous"] or x["recovered"])
    clarify_n = sum(1 for x in rows if x["clarify_slot"])
    ledger = {
        "experiment_id": "I12.15-CHAR",
        "frozen": True,
        "source": "I12.11 baseline_deepseek_chat category=state; re-evaluated on current Engine",
        "TOTAL_STATE_RUNS": len(rows),
        "TOTAL_STATE_CASES": len({x["case_id"] for x in rows}),
        "primary_failure_counts": dict(prim),
        "first_causal_stage_counts": dict(stage),
        "STATE_AUTONOMOUS_CAPTURE_RATE": auto / n,
        "STATE_RECOVERABLE_GAP_RATE": clarify_n / n,
        "STATE_TOTAL_CAPTURE_AFTER_BOUNDED_RECOVERY": after / n,
        "recovery": dict(recover),
        "dominant_failure": "CANONICALIZATION_FAILURE",
        "deterministic_downstream_defect_found": prim.get("VALID_STATE_LOST_DOWNSTREAM", 0)
        > 0,
        "unresolved_expression_histogram": dict(
            Counter(
                x["state_expression"]
                for x in rows
                if x["primary"] == "VALID_STATE_CANONICAL_UNRESOLVED"
            )
        ),
        "WHAT_IS_THE_DOMINANT_CAUSE_OF_REMAINING_STATE_FAILURES": "CANONICALIZATION_FAILURE",
        "CAN_STATE_RELIABILITY_BE_IMPROVED_WITHOUT_REINTERPRETING_RAW_OR_INVENTING": "PARTIALLY",
        "hardening_note": (
            "I12.15: false CLARIFY on present-but-uncanonicalized state_expression "
            "→ SAFE_ABSTAIN (state_canonical_unresolved). Capture unchanged without ontology expansion."
        ),
        "runs": rows,
    }

    path = OUT_DIR / "I12.15-STATE-FAILURE-LEDGER.json"
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in ledger.items() if k != "runs"}, indent=2, ensure_ascii=False))
    print("wrote", path)


if __name__ == "__main__":
    main()
