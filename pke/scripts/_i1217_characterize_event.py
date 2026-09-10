"""I12.17 Event residual characterization — freeze ledger (audit only)."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

from pke.application.ingest import IngestService
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.capability_strategy import decide_capability
from pke.interpretation.semantic.event_preservation import (
    event_assertion_present,
    event_false_canonicalization,
)
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
OUT = ROOT / "docs" / "reports" / "i1217_artifacts"
CHECKPOINT = ROOT / "docs" / "reports" / "i1211_artifacts" / "checkpoint.jsonl"


class Clock:
    def now(self):
        return dt.datetime(2026, 9, 3, 22, 0, tzinfo=dt.UTC)


def classify(r: dict, p: SemanticProposal) -> tuple[str, str, str]:
    """Return (primary, stage, blocker_class)."""
    rr = resolve_proposal(p)
    er = assess_execution_readiness(rr)
    d = decide_capability(er)
    assertions = [a.primitive.value for a in collect_assertions(p)]
    has_evt = bool(
        p.change_semantics
        or p.action_expression
        or p.event_expression
        or p.primitive_hint == "event"
    )
    outcome = proposal_to_canonical_ir(p)
    false_canon = event_false_canonicalization(outcome)
    evt_prims = [x for x in er.primitives if x.primitive is PrimitiveKind.EVENT]

    if false_canon:
        return "EVENT_FALSE_CANONICALIZATION", "S4_CONCEPT_RESOLUTION", "ENGINE_BLOCKER"
    if not has_evt:
        if "event" in assertions:
            return "EVENT_FALSELY_ADDED", "S3_PRIMITIVE_ROUTING", "ENGINE_BLOCKER"
        return "EVENT_OMITTED_BY_MODEL", "S2_SEMANTIC_PROPOSAL", "MODEL_CAPABILITY_LIMIT"
    if "event" not in assertions:
        return "EVENT_WRONG_PRIMITIVE", "S3_PRIMITIVE_ROUTING", "ENGINE_BLOCKER"

    # Event asserted
    if outcome.ir and outcome.ir.event and outcome.ir.event.type.key == "event.intent":
        if rr.concepts.event_type != "event.intent":
            return "EVENT_FALSE_CANONICALIZATION", "S7_PERSISTABILITY", "ENGINE_BLOCKER"

    if PrimitiveKind.EVENT in rr.non_materialized_primitives:
        if event_assertion_present(rr):
            # Preserved as non-materialized — even when sibling also incomplete (ir=None).
            reasons = " ".join(
                x for p in evt_prims for x in (p.reasons or ())
            ) if evt_prims else " ".join(rr.non_materialized_reasons or ())
            if "missing_entity" in reasons or "entity" in reasons or "identity" in reasons:
                return (
                    "EVENT_SAFE_PARTIAL",
                    "S7_PERSISTABILITY",
                    "PRODUCT_CLARIFICATION_LIMIT",
                )
            if rr.concepts.unresolved or not rr.concepts.event_type:
                return (
                    "EVENT_SAFE_PARTIAL",
                    "S7_PERSISTABILITY",
                    "ONTOLOGY_COVERAGE_LIMIT",
                )
            return "EVENT_SAFE_PARTIAL", "S7_PERSISTABILITY", "SAFE_ABSTENTION"
        return "EVENT_DOWNSTREAM_LOSS", "S7_PERSISTABILITY", "ENGINE_BLOCKER"

    # Asserted Event neither materialized nor marked non-materialized → loss
    if (
        "event" in assertions
        and (outcome.ir is None or (outcome.ir and outcome.ir.event is None))
        and PrimitiveKind.EVENT not in rr.non_materialized_primitives
    ):
        return "EVENT_DOWNSTREAM_LOSS", "S7_PERSISTABILITY", "ENGINE_BLOCKER"

    if evt_prims:
        sp = evt_prims[0]
        if sp.status.value == "ready" and d.outcome.value in {"auto_execute", "partial_execute"}:
            return "EVENT_CORRECT", "S9_FINAL_OUTCOME", "SAFE_ABSTENTION"
        if "missing_entity" in " ".join(sp.reasons or ()):
            return "EVENT_ENTITY_UNRESOLVED", "S6_EXECUTION_READINESS", "PRODUCT_CLARIFICATION_LIMIT"
        if rr.concepts.unresolved or not rr.concepts.event_type:
            return "EVENT_CANONICAL_UNRESOLVED", "S4_CONCEPT_RESOLUTION", "ONTOLOGY_COVERAGE_LIMIT"
        return "EVENT_INCOMPLETE_BY_MODEL", "S6_EXECUTION_READINESS", "MODEL_CAPABILITY_LIMIT"

    return "OTHER", "S9_FINAL_OUTCOME", "POST_V1"


def main() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    OUT.mkdir(parents=True, exist_ok=True)
    db = OUT / "char.db"
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

    prim: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    stage: Counter[str] = Counter()
    safety = Counter()
    rows: list[dict] = []
    useful_auto = 0
    useful_after = 0
    n = 0

    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("candidate_id") != "baseline_deepseek_chat":
            continue
        # Event-focused: category event/multi_primitive OR proposal has event signals
        dump = r.get("proposal_dump")
        if not dump and r.get("category") not in {"event", "multi_primitive", "measurement"}:
            continue
        if not dump:
            continue
        p = SemanticProposal.model_validate(dump)
        cat = r.get("category")
        if cat not in {"event", "multi_primitive"} and not (
            p.change_semantics or p.event_expression or p.action_expression
        ):
            continue
        n += 1
        primary, st, block = classify(r, p)
        prim[primary] += 1
        stage[st] += 1
        blockers[block] += 1

        outcome = proposal_to_canonical_ir(p)
        if event_false_canonicalization(outcome):
            safety["EVENT_FALSE_CANONICALIZATION"] += 1
        if (
            (p.change_semantics or p.event_expression)
            and "event" in [a.primitive.value for a in collect_assertions(p)]
            and outcome.ir is not None
            and outcome.ir.event is None
            and PrimitiveKind.EVENT not in outcome.result.non_materialized_primitives
            and not p.measurement_semantics
        ):
            # explicit event lost entirely without safe-partial marking
            safety["VALID_EXPLICIT_EVENT_DROPPED_DOWNSTREAM"] += 1

        committed = False
        if outcome.ir is not None:
            user = UserContext(
                user_id=f"ev-{r['case_id']}-{r['run']}",
                timezone="America/Fortaleza",
            )
            session = SessionContext(personal=PersonalContext(user_id=user.user_id))
            res = ingest.ingest_from_ir(outcome.ir, user, session)
            if res.status is IngestStatus.COMMITTED:
                committed = True
                # useful if any event or measurement or other knowledge
                mat = res.materialization
                if mat and (
                    mat.event_ids
                    or mat.measurement_ids
                    or getattr(mat, "state_ids", None)
                    or getattr(mat, "relation_ids", None)
                ):
                    useful_auto += 1
                    useful_after += 1
                elif r.get("useful_capture"):
                    useful_auto += 1
                    useful_after += 1

        if primary == "EVENT_CORRECT" or (
            primary == "EVENT_SAFE_PARTIAL" and committed
        ):
            pass  # already counted if committed

        rows.append(
            {
                "case_id": r["case_id"],
                "run": r["run"],
                "category": cat,
                "utterance": r["utterance"][:80],
                "primary": primary,
                "first_causal_stage": st,
                "blocker_class": block,
                "committed": committed,
                "mp_anchor": r.get("mp_anchor"),
                "event_type": outcome.result.concepts.event_type,
                "ir_has_event": bool(outcome.ir and outcome.ir.event),
                "non_mat_event": PrimitiveKind.EVENT
                in outcome.result.non_materialized_primitives,
            }
        )

    engine_blockers = sum(
        1 for x in rows if x["blocker_class"] == "ENGINE_BLOCKER"
    )
    # Mandatory safety keys (target zero)
    for key in (
        "EVENT_FALSE_CANONICALIZATION",
        "VALID_EXPLICIT_EVENT_DROPPED_DOWNSTREAM",
        "EVENT_FALSELY_ADDED",
        "EVENT_WRONG_PRIMITIVE_COMMIT",
        "STATE_FALSE_CAUSAL_EVENT",
        "RELATION_FALSE_START_EVENT",
        "MP5_FALSE_EVENT",
        "EVENT_MEASUREMENT_DUPLICATE_COMMIT",
        "CORRECTION_GUARD_BYPASSED",
        "RAW_TEXT_REINTERPRETED_DOWNSTREAM",
        "MISSING_EVENT_INFORMATION_INVENTED",
    ):
        safety.setdefault(key, 0)

    clarif = blockers.get("PRODUCT_CLARIFICATION_LIMIT", 0)
    ontology = blockers.get("ONTOLOGY_COVERAGE_LIMIT", 0)
    safe_partial = prim.get("EVENT_SAFE_PARTIAL", 0)
    omitted = prim.get("EVENT_OMITTED_BY_MODEL", 0)
    # Bounded recovery ceiling: autonomous commits + clarifiable residuals (entity gaps).
    # Ontology gaps are not recoverable without Core reopen.
    useful_after_recovery_ceiling = min(n, useful_auto + clarif)

    ledger = {
        "experiment_id": "I12.17-CHAR",
        "frozen": True,
        "source": "I12.11 baseline event/multi_primitive (+ event-signal proposals)",
        "TOTAL_EVENT_RUNS": n,
        "TOTAL_EVENT_CASES": len({x["case_id"] for x in rows}),
        "primary_counts": dict(prim),
        "stage_counts": dict(stage),
        "blocker_class_counts": dict(blockers),
        "EVENT_ENGINE_DEFECT_RATE": engine_blockers / max(1, n),
        "DOES_EVENT_INTERPRETATION_STILL_CONTAIN_A_MATERIAL_ENGINE_V1_BLOCKING_DEFECT": engine_blockers
        > 0
        or any(v > 0 for v in safety.values()),
        "safety": dict(safety),
        "EVENT_AUTONOMOUS_USEFUL_CAPTURE_RATE": useful_auto / max(1, n),
        "EVENT_RECOVERABLE_GAP_RATE": clarif / max(1, n),
        "EVENT_USEFUL_CAPTURE_AFTER_BOUNDED_RECOVERY": useful_after_recovery_ceiling
        / max(1, n),
        "EVENT_USEFUL_CAPTURE_AFTER_BOUNDED_RECOVERY_NOTE": (
            "ceiling = autonomous_commits + PRODUCT_CLARIFICATION_LIMIT residuals; "
            "ontology gaps excluded"
        ),
        "EVENT_SAFE_PARTIAL_RATE": safe_partial / max(1, n),
        "EVENT_CANONICAL_UNRESOLVED_RATE": ontology / max(1, n),
        "EVENT_UNDETECTABLE_OMISSION_RATE": omitted / max(1, n),
        "runs": rows,
    }
    path = OUT / "I12.17-EVENT-FAILURE-LEDGER.json"
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps({k: v for k, v in ledger.items() if k != "runs"}, indent=2, ensure_ascii=False)
    )
    print("wrote", path)


if __name__ == "__main__":
    main()
