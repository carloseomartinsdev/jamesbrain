"""I12.16 characterization — freeze Relation failure ledger (no production hardening)."""

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
OUT_DIR = ROOT / "docs" / "reports" / "i1216_artifacts"
CHECKPOINT = ROOT / "docs" / "reports" / "i1211_artifacts" / "checkpoint.jsonl"


class Clock:
    def now(self):
        return dt.datetime(2026, 9, 3, 21, 0, tzinfo=dt.UTC)


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

    prim: Counter[str] = Counter()
    stage: Counter[str] = Counter()
    recover: Counter[str] = Counter()
    rows: list[dict] = []

    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("candidate_id") != "baseline_deepseek_chat" or r.get("category") != "relation":
            continue
        if not r.get("proposal_dump"):
            continue
        p = SemanticProposal.model_validate(r["proposal_dump"])
        rr = resolve_proposal(p)
        er = assess_execution_readiness(rr)
        d = decide_capability(er)
        assertions = [a.primitive.value for a in collect_assertions(p)]
        has_rel = bool(
            p.link_semantics
            or p.relation_expression
            or p.primitive_hint == "relation"
        )
        rel_prims = [x for x in er.primitives if x.primitive is PrimitiveKind.RELATION]
        committed = False
        recovered = False
        primary = "OTHER"
        st = "S9_FINAL_OUTCOME"

        if not has_rel:
            primary = "VALID_PROPOSAL_RELATION_OMITTED"
            st = "S2_SEMANTIC_PROPOSAL"
        elif "relation" not in assertions or not rel_prims:
            primary = "VALID_PROPOSAL_WRONG_PRIMITIVE"
            st = "S3_PRIMITIVE_ROUTING"
        else:
            sp = rel_prims[0]
            reasons = " ".join(sp.reasons or ())
            if sp.status.value == "ready" and d.outcome.value in {
                "auto_execute",
                "partial_execute",
            }:
                out = proposal_to_canonical_ir(p)
                if out.ir is None:
                    primary = "VALID_RELATION_LOST_DOWNSTREAM"
                    st = "S7_PERSISTABILITY"
                else:
                    user = UserContext(
                        user_id=f"rel-{r['case_id']}-{r['run']}",
                        timezone="America/Fortaleza",
                    )
                    session = SessionContext(personal=PersonalContext(user_id=user.user_id))
                    res = ingest.ingest_from_ir(out.ir, user, session)
                    if res.status is IngestStatus.COMMITTED:
                        committed = True
                        primary = "RELATION_CORRECT"
                        st = "S9_FINAL_OUTCOME"
                    else:
                        primary = "VALID_RELATION_LOST_DOWNSTREAM"
                        st = "S8_MATERIALIZATION"
            elif "missing_relation_subject" in reasons or (
                "subject" in reasons and "object" not in reasons
            ):
                primary = "VALID_RELATION_MISSING_SUBJECT"
                st = "S6_EXECUTION_READINESS"
            elif "missing_relation_object" in reasons:
                primary = "VALID_RELATION_MISSING_OBJECT"
                st = "S6_EXECUTION_READINESS"
            elif (
                p.relation_expression
                and (rr.concepts.unresolved or not rr.concepts.relation_type)
            ) or "missing_relation_identity" in reasons:
                primary = "VALID_RELATION_CANONICAL_UNRESOLVED"
                st = "S4_CONCEPT_RESOLUTION"
            elif "missing_entity" in reasons:
                primary = "VALID_RELATION_ENTITY_UNRESOLVED"
                st = "S6_EXECUTION_READINESS"
            else:
                primary = "VALID_RELATION_REJECTED_BY_READINESS"
                st = "S6_EXECUTION_READINESS"

        false_recoverable = False
        if d.outcome.value == "clarify" and d.clarification:
            # Canonical gap wrongly clarified?
            if primary == "VALID_RELATION_CANONICAL_UNRESOLVED" and d.clarification.missing_slot in {
                "relation_subject",
                "relation_object",
                "state_value",
            }:
                # clarifying endpoints when concept missing may be false recoverable
                if p.subject is not None and p.object is not None:
                    false_recoverable = True
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
            if slot in {"relation_subject", "relation_object", "measured_entity"}:
                ans = f"entidade-{r['case_id']}-{r['run']}"
            else:
                ans = "fixture"
            user = UserContext(
                user_id=f"rcv-rel-{r['case_id']}-{r['run']}",
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
                "relation_expression": p.relation_expression,
                "link_semantics": p.link_semantics,
                "subject": p.subject.text if p.subject else None,
                "object": p.object.text if p.object else None,
                "primary": primary,
                "first_causal_stage": st,
                "committed_autonomous": committed,
                "recovered": recovered,
                "clarify_slot": d.clarification.missing_slot if d.clarification else None,
                "capability_outcome": d.outcome.value,
                "concepts_relation_type": rr.concepts.relation_type,
                "concepts_unresolved": rr.concepts.unresolved,
                "false_recoverable_gap": false_recoverable,
                "reasons": [list(x.reasons) for x in rel_prims],
            }
        )

    n = len(rows) or 1
    auto = sum(1 for x in rows if x["committed_autonomous"])
    after = sum(1 for x in rows if x["committed_autonomous"] or x["recovered"])
    clarify_n = sum(1 for x in rows if x["clarify_slot"])
    false_gap = sum(1 for x in rows if x["false_recoverable_gap"])
    unresolved_exprs = Counter(
        x["relation_expression"]
        for x in rows
        if x["primary"] == "VALID_RELATION_CANONICAL_UNRESOLVED"
    )
    top = max(prim, key=prim.get) if prim else "OTHER"
    if top == "VALID_RELATION_CANONICAL_UNRESOLVED" or prim.get(
        "VALID_RELATION_CANONICAL_UNRESOLVED", 0
    ) >= max(prim.values(), default=0):
        dominant = "CANONICALIZATION_FAILURE"
    elif "MISSING" in top:
        dominant = "RELATION_INCOMPLETENESS"
    elif top == "VALID_PROPOSAL_RELATION_OMITTED":
        dominant = "RELATION_OMISSION"
    elif top == "VALID_PROPOSAL_WRONG_PRIMITIVE":
        dominant = "WRONG_PRIMITIVE_ROUTING"
    elif top == "RELATION_CORRECT":
        dominant = "MIXED" if any(k != "RELATION_CORRECT" for k in prim) else "OTHER"
    else:
        dominant = "MIXED"

    ledger = {
        "experiment_id": "I12.16-CHAR",
        "frozen": True,
        "source": "I12.11 baseline_deepseek_chat category=relation; re-evaluated on current Engine",
        "TOTAL_RELATION_RUNS": len(rows),
        "TOTAL_RELATION_CASES": len({x["case_id"] for x in rows}),
        "primary_failure_counts": dict(prim),
        "first_causal_stage_counts": dict(stage),
        "RELATION_AUTONOMOUS_CAPTURE_RATE": auto / n,
        "RELATION_RECOVERABLE_GAP_RATE": clarify_n / n,
        "RELATION_USEFUL_CAPTURE_AFTER_BOUNDED_RECOVERY": after / n,
        "RELATION_FALSE_RECOVERABLE_GAP": false_gap,
        "recovery": dict(recover),
        "WHAT_IS_THE_DOMINANT_CAUSE_OF_REMAINING_RELATION_FAILURES": dominant,
        "deterministic_downstream_defect_found": prim.get("VALID_RELATION_LOST_DOWNSTREAM", 0)
        > 0,
        "unresolved_expression_histogram": dict(unresolved_exprs),
        "CAN_EXISTING_SEMANTICPROPOSAL_EXPRESS_A_COMPLETE_RELATION_ASSERTION": True,
        "runs": rows,
    }
    path = OUT_DIR / "I12.16-RELATION-FAILURE-LEDGER.json"
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in ledger.items() if k != "runs"}, indent=2, ensure_ascii=False))
    print("wrote", path)


if __name__ == "__main__":
    main()
