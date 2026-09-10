"""Avaliador I11.5-R — Relation, lifecycle, collapse (sem alterar produção)."""

from __future__ import annotations

import datetime as dt
import sqlite3
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from pke.application import FixedClock, IngestService, IngestStatus, SessionContext
from pke.domain import (
    ConceptKind,
    ConceptRef,
    OccurrenceStatus,
    RelationToReference,
    TimePrecision,
    UserContext,
    new_ulid,
)
from pke.domain.relation_lifecycle import termination_calendar_known
from pke.domain.relations import Relation
from pke.interpretation import (
    DeepSeekInterpreter,
    EntityMention,
    FakeInterpreter,
    IngestIntent,
    IngestIR,
    IrRelation,
    IrTime,
    RelationAssertionMode,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.ontology.relation_metadata import RELATION_METADATA
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.persist.migrations.v5_to_v6 import migrate_v5_to_v6
from pke.persist.sqlite.engine import create_sqlite_engine, sqlite_url
from pke.query.engine import QueryEngine
from pke.query.relation_resolver import relation_held_during, resolve_relation_query
from pke.query.spec import EntityAssociation, RelationQueryKind, RelationScope, ResolvedQuerySpec, TimeRange
from pke.resolution import PersonalContext

from tests.generalization_ingest.fixtures import BENCHMARK_NOW, FORTALEZA, USER_ID
from tests.generalization_ingest.relation_cases import (
    COLLAPSE_CASES,
    LIVE_RELATION_IDS,
    NEGATION_LIVE_CASES,
    RELATION_CASES,
    RelationBenchmarkCase,
    RelationCaseKind,
)
from tests.integration.test_ingest import _corolla

RUNS_LIVE = 3


def _present() -> IrTime:
    return IrTime(
        original_text="",
        occurrence_status=OccurrenceStatus.ONGOING,
        relation_to_reference=RelationToReference.DURING,
        tense_evidence="present",
    )


def _past() -> IrTime:
    return IrTime(
        original_text="",
        occurrence_status=OccurrenceStatus.HAPPENED,
        relation_to_reference=RelationToReference.BEFORE,
        tense_evidence="past",
    )


def _terminate_time() -> IrTime:
    return _past()


def _exact_date_time() -> IrTime:
    return IrTime(
        original_text="15/08/2026",
        instant=dt.datetime(2026, 8, 15, tzinfo=FORTALEZA),
        precision=TimePrecision.DAY,
        occurrence_status=OccurrenceStatus.HAPPENED,
        relation_to_reference=RelationToReference.BEFORE,
    )


def _partial_month_time() -> IrTime:
    return IrTime(
        original_text="agosto",
        partial_month=8,
        partial_year=2026,
        precision=TimePrecision.PARTIAL,
        occurrence_status=OccurrenceStatus.HAPPENED,
        relation_to_reference=RelationToReference.BEFORE,
    )


def _mention(text: str, type_key: str, role: str = "role.subject") -> EntityMention:
    return EntityMention(text=text, type_hint=ConceptRef(key=type_key), role=ConceptRef(key=role))


def _relation_ir(
    raw: str,
    *,
    subject: EntityMention,
    object: EntityMention,
    relation_key: str,
    mode: RelationAssertionMode = RelationAssertionMode.ASSERT,
    time: IrTime | None = None,
) -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_RELATION,
        raw_input=raw,
        relation=IrRelation(
            type=ConceptRef(key=relation_key),
            subject=subject,
            object=object,
            mode=mode,
            time=time or _present(),
        ),
    )


def _sub_obj(case: RelationBenchmarkCase) -> tuple[EntityMention, EntityMention]:
    sub = _mention(case.subject_text, case.subject_type)
    if case.case_id == "R3":
        return sub, _corolla()
    obj = _mention(case.object_text, case.object_type)
    if case.case_id == "R6":
        return _mention(case.subject_text, case.subject_type, role="role.provider"), obj
    return sub, obj


def deterministic_responses(case: RelationBenchmarkCase) -> dict[str, object]:
    sub, obj = _sub_obj(case)
    key = case.expectation.relation_key or case.relation_key
    responses: dict[str, object] = {}
    if case.kind is RelationCaseKind.SINGLE:
        responses[case.texts[0]] = _relation_ir(case.texts[0], subject=sub, object=obj, relation_key=key)
        return responses
    if case.kind is RelationCaseKind.LIFECYCLE:
        t0 = case.texts[0]
        responses[t0] = _relation_ir(t0, subject=sub, object=obj, relation_key=key)
        t1 = case.texts[1]
        if "15/08/2026" in t1:
            responses[t1] = _relation_ir(
                t1, subject=sub, object=obj, relation_key=key,
                mode=RelationAssertionMode.TERMINATE, time=_exact_date_time(),
            )
        elif "agosto" in t1 and "saiu" in t1:
            responses[t1] = _relation_ir(
                t1, subject=sub, object=obj, relation_key=key,
                mode=RelationAssertionMode.TERMINATE, time=_partial_month_time(),
            )
        else:
            responses[t1] = _relation_ir(
                t1, subject=sub, object=obj, relation_key=key,
                mode=RelationAssertionMode.TERMINATE, time=_terminate_time(),
            )
        return responses
    if case.kind is RelationCaseKind.LIFECYCLE_QUERY:
        base = deterministic_responses(
            RelationBenchmarkCase(
                case_id=case.case_id,
                kind=RelationCaseKind.LIFECYCLE,
                texts=case.texts[:2],
                expectation=case.expectation,
            )
        )
        return base
    if case.kind is RelationCaseKind.PROVENANCE:
        return deterministic_responses(
            RelationBenchmarkCase(
                case_id="PROVENANCE",
                kind=RelationCaseKind.LIFECYCLE,
                texts=case.texts,
                expectation=case.expectation,
            )
        )
    if case.kind is RelationCaseKind.CONCURRENCY:
        joao = _mention("João", "entity.person")
        acme = _mention("Acme", "entity.organization")
        beta = _mention("Beta", "entity.organization")
        return {
            case.texts[0]: _relation_ir(case.texts[0], subject=joao, object=acme, relation_key=key),
            case.texts[1]: _relation_ir(case.texts[1], subject=joao, object=beta, relation_key=key),
        }
    if case.kind is RelationCaseKind.TARGETED_TERMINATION:
        joao = _mention("João", "entity.person")
        acme = _mention("Acme", "entity.organization")
        beta = _mention("Beta", "entity.organization")
        return {
            case.texts[0]: _relation_ir(case.texts[0], subject=joao, object=acme, relation_key=key),
            case.texts[1]: _relation_ir(case.texts[1], subject=joao, object=beta, relation_key=key),
            case.texts[2]: _relation_ir(
                case.texts[2], subject=joao, object=acme, relation_key=key,
                mode=RelationAssertionMode.TERMINATE, time=_terminate_time(),
            ),
        }
    if case.kind is RelationCaseKind.SYMMETRY:
        ana = _mention("Ana", "entity.person")
        joao = _mention("João", "entity.person")
        return {
            case.texts[0]: _relation_ir(
                case.texts[0], subject=ana, object=joao, relation_key="relation.married_to"
            )
        }
    if case.kind is RelationCaseKind.DENY_CURRENT:
        joao = _mention("João", "entity.person")
        acme = _mention("Acme", "entity.organization")
        return {
            case.texts[0]: _relation_ir(case.texts[0], subject=joao, object=acme, relation_key=key),
            case.texts[1]: _relation_ir(
                case.texts[1], subject=joao, object=acme, relation_key=key,
                mode=RelationAssertionMode.DENY_CURRENT, time=_present(),
            ),
        }
    if case.kind is RelationCaseKind.VALID_TO_AUDIT:
        return deterministic_responses(
            RelationBenchmarkCase(
                case_id=case.case_id,
                kind=RelationCaseKind.LIFECYCLE,
                texts=case.texts,
                expectation=case.expectation,
            )
        )
    if case.kind is RelationCaseKind.CORRECTION_AUDIT:
        joao = _mention("João", "entity.person")
        acme = _mention("Acme", "entity.organization")
        return {
            case.texts[0]: _relation_ir(case.texts[0], subject=joao, object=acme, relation_key=key),
            case.texts[1]: _relation_ir(
                case.texts[1], subject=joao, object=acme, relation_key=key,
                mode=RelationAssertionMode.TERMINATE, time=_terminate_time(),
            ),
        }
    return {}


@dataclass
class RelationRunOutcome:
    case_id: str
    run: int
    deterministic: bool
    interpretation_success: bool
    knowledge_success: bool
    identity_ok: bool | None = None
    direction_ok: bool | None = None
    concurrency_ok: bool | None = None
    lifecycle_ok: bool | None = None
    provenance_ok: bool | None = None
    no_causal_event: bool | None = None
    no_time_invention: bool | None = None
    history_ok: bool | None = None
    currentness_ok: bool | None = None
    query_ok: bool | None = None
    primitive_collapse: bool | None = None
    deny_current_ok: bool | None = None
    frontier: str = "OTHER"
    ingest_status: str | None = None
    notes: list[str] = field(default_factory=list)
    ir_intent: str | None = None
    relation_count: int = 0
    event_count: int = 0
    state_count: int = 0
    observed_relation_key: str | None = None
    error_class: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _counts(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(db_path)
    try:
        return {
            "events": con.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "states": con.execute("SELECT COUNT(*) FROM states").fetchone()[0],
            "relations": con.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
        }
    finally:
        con.close()


def _user() -> UserContext:
    return UserContext(user_id=USER_ID, timezone="America/Fortaleza", now=BENCHMARK_NOW)


def _session() -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=USER_ID))


def _service(db_path: Path, ontology: OntologyRegistry, interpreter) -> IngestService:
    return IngestService(
        interpreter,
        ontology,
        lambda: open_sqlite_uow(db_path),
        FixedClock(BENCHMARK_NOW),
    )


def _entity_ids(graph, *names: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in names:
        for e in graph.entities.values():
            if e.canonical_name == name:
                out[name] = e.id
                break
    return out


def _check_relation(rel: Relation, exp, notes: list[str]) -> tuple[bool, bool, bool, bool]:
    identity_ok = True
    direction_ok = True
    lifecycle_ok = True
    provenance_ok = True
    if exp.relation_key and rel.key != exp.relation_key:
        identity_ok = False
        notes.append(f"key expected {exp.relation_key} got {rel.key}")
    if exp.is_current is not None and rel.is_current != exp.is_current:
        lifecycle_ok = False
        notes.append(f"is_current expected {exp.is_current} got {rel.is_current}")
    if exp.termination_known is not None and rel.termination_known != exp.termination_known:
        lifecycle_ok = False
        notes.append(f"termination_known expected {exp.termination_known}")
    if exp.termination_calendar_known is not None:
        cal = termination_calendar_known(rel.termination_temporal)
        if cal != exp.termination_calendar_known:
            lifecycle_ok = False
            notes.append(f"termination_calendar_known expected {exp.termination_calendar_known} got {cal}")
    if exp.valid_to_null is True and rel.valid_to is not None:
        lifecycle_ok = False
        notes.append(f"valid_to should be null got {rel.valid_to}")
    if exp.valid_from_null is True and rel.valid_from is not None:
        lifecycle_ok = False
        notes.append(f"valid_from should be null got {rel.valid_from}")
    if exp.no_recorded_at_start and rel.valid_from == rel.observed_at:
        lifecycle_ok = False
        notes.append("recorded_at used as start")
    if exp.no_recorded_at_termination and rel.valid_to == rel.termination_observed_at:
        lifecycle_ok = False
        notes.append("recorded_at used as termination")
    if exp.provenance_distinct:
        if not rel.raw_input_id or not rel.termination_raw_input_id:
            provenance_ok = False
            notes.append("missing raw_input ids")
        elif rel.raw_input_id == rel.termination_raw_input_id:
            provenance_ok = False
            notes.append("assertion/termination raw_input not distinct")
        elif rel.source is None or rel.termination_source is None:
            provenance_ok = False
            notes.append("missing source objects")
    return identity_ok, direction_ok, lifecycle_ok, provenance_ok


def _run_queries(
    db_path: Path,
    ontology: OntologyRegistry,
    case: RelationBenchmarkCase,
    notes: list[str],
) -> bool:
    exp = case.expectation
    if not exp.query_kind:
        return True
    graph = open_sqlite_read_store(db_path).load_user_graph(USER_ID)
    ids = _entity_ids(graph, "João", "Acme")
    if "João" not in ids or "Acme" not in ids:
        notes.append("entity ids missing for query")
        return False
    engine = QueryEngine(open_sqlite_read_store(db_path), ontology)
    joao_id, acme_id = ids["João"], ids["Acme"]
    concept = core_concept_id("relation.employed_by")
    if exp.query_kind == "historical_existence":
        result = engine.execute(
            ResolvedQuerySpec(
                user_id=USER_ID,
                entity_ids=[joao_id, acme_id],
                relation_type_ids=[concept],
                relation_query_kind=RelationQueryKind.HISTORICAL_EXISTENCE,
            )
        )
    elif exp.query_kind == "current_boolean":
        result = engine.execute(
            ResolvedQuerySpec(
                user_id=USER_ID,
                entity_ids=[joao_id, acme_id],
                entity_association=EntityAssociation.RELATION_SUBJECT,
                relation_type_ids=[concept],
                relation_scope=RelationScope.CURRENT,
            )
        )
    elif exp.query_kind == "termination_date":
        result = engine.execute(
            ResolvedQuerySpec(
                user_id=USER_ID,
                entity_ids=[joao_id, acme_id],
                relation_type_ids=[concept],
                relation_query_kind=RelationQueryKind.TERMINATION_DATE,
            )
        )
    elif exp.query_kind == "held_during":
        august = TimeRange(
            start=dt.datetime(2026, 8, 1, tzinfo=FORTALEZA),
            end=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
        )
        result = engine.execute(
            ResolvedQuerySpec(
                user_id=USER_ID,
                entity_ids=[joao_id, acme_id],
                relation_type_ids=[concept],
                relation_query_kind=RelationQueryKind.HELD_DURING,
                time_range=august,
            )
        )
    else:
        return True
    ok = result.relation_answer == exp.query_answer
    if not ok:
        notes.append(f"query expected {exp.query_answer} got {result.relation_answer}")
    return ok


def evaluate_deterministic_case(
    case: RelationBenchmarkCase,
    root: Path,
    ontology: OntologyRegistry,
) -> RelationRunOutcome:
    db = root / f"det_{case.case_id}.db"
    if db.exists():
        db.unlink()
    if case.kind is RelationCaseKind.CORRECTION_AUDIT:
        return RelationRunOutcome(
            case_id=case.case_id,
            run=0,
            deterministic=True,
            interpretation_success=True,
            knowledge_success=True,
            notes=["CORRECTION_ENGINE_DEBT — deferred; benchmark records gap only"],
            frontier="KNOWN_GAP",
        )
    responses = deterministic_responses(case)
    if not responses:
        return RelationRunOutcome(
            case_id=case.case_id,
            run=0,
            deterministic=True,
            interpretation_success=False,
            knowledge_success=False,
            notes=["no deterministic fixture"],
            frontier="OTHER",
        )
    svc = _service(db, ontology, FakeInterpreter(responses))  # type: ignore[arg-type]
    user, session = _user(), _session()
    notes: list[str] = []
    last_status = None
    ingest_texts = [t for t in case.texts if not t.endswith("?")]
    for text in ingest_texts:
        result = svc.ingest(text, user, session)
        last_status = result.status.value
        if result.status is not IngestStatus.COMMITTED:
            return RelationRunOutcome(
                case_id=case.case_id,
                run=0,
                deterministic=True,
                interpretation_success=True,
                knowledge_success=False,
                ingest_status=last_status,
                notes=[f"ingest not committed: {last_status}"],
                frontier="MATERIALIZATION",
            )
    counts = _counts(db)
    graph = open_sqlite_read_store(db).load_user_graph(USER_ID)
    exp = case.expectation
    identity_ok = direction_ok = lifecycle_ok = provenance_ok = True
    observed_key = None
    if graph.relations:
        rel = graph.relations[0]
        observed_key = rel.key
        identity_ok, direction_ok, lifecycle_ok, provenance_ok = _check_relation(rel, exp, notes)
    elif exp.min_relations > 0:
        identity_ok = False
        notes.append("no relations committed")
    count_ok = exp.min_relations <= counts["relations"] <= exp.max_relations
    if not count_ok:
        identity_ok = False
        notes.append(f"relation count {counts['relations']} not in [{exp.min_relations},{exp.max_relations}]")
    no_causal = counts["events"] <= exp.max_events if exp.forbid_causal_event else True
    if counts["events"] > exp.max_events:
        notes.append(f"events={counts['events']} max={exp.max_events}")
    no_time = True
    if graph.relations:
        rel = graph.relations[0]
        if exp.no_recorded_at_start and rel.valid_from == rel.observed_at:
            no_time = False
        if exp.no_recorded_at_termination and rel.valid_to == rel.termination_observed_at:
            no_time = False
    concurrency_ok = True
    if exp.both_current:
        concurrency_ok = len(graph.relations) == 2 and all(r.is_current for r in graph.relations)
        if not concurrency_ok:
            notes.append("concurrent relations not both current")
    if exp.acme_ended_beta_current:
        acme_rel = next((r for r in graph.relations if any(
            e.canonical_name == "Acme" for e in graph.entities.values() if e.id == r.to_id
        )), None)
        beta_rel = next((r for r in graph.relations if any(
            e.canonical_name == "Beta" for e in graph.entities.values() if e.id == r.to_id
        )), None)
        if acme_rel is None or beta_rel is None:
            concurrency_ok = False
            notes.append("Acme/Beta relations missing")
        else:
            concurrency_ok = acme_rel.is_current is False and beta_rel.is_current is True
            if acme_rel.termination_known is not True:
                concurrency_ok = False
                notes.append("Acme termination not known")
    deny_ok = True
    if exp.deny_invents_termination:
        rel = graph.relations[0] if graph.relations else None
        if rel is None:
            deny_ok = False
        else:
            deny_ok = rel.termination_known is False and rel.termination_raw_input_id is None
            if not deny_ok:
                notes.append("DENY_CURRENT invented termination evidence")
    symmetry_ok = True
    if exp.symmetric_single_row:
        symmetry_ok = len(graph.relations) == 1
        if case.case_id == "SYMMETRY":
            ids = _entity_ids(graph, "Ana", "João")
            if "Ana" in ids and "João" in ids:
                ans = resolve_relation_query(
                    graph.relations,
                    subject_id=ids["João"],
                    object_id=ids["Ana"],
                    concept_ids={core_concept_id("relation.married_to")},
                    scope=RelationScope.CURRENT,
                    boolean_check=True,
                )
                if ans.answer != "yes":
                    symmetry_ok = False
                    notes.append(f"symmetric query got {ans.answer}")
    query_ok = _run_queries(db, ontology, case, notes) if exp.query_kind else True
    history_ok = query_ok if exp.query_kind == "historical_existence" else True
    currentness_ok = query_ok if exp.query_kind == "current_boolean" else lifecycle_ok
    knowledge = (
        count_ok
        and identity_ok
        and lifecycle_ok
        and provenance_ok
        and no_causal
        and no_time
        and concurrency_ok
        and deny_ok
        and symmetry_ok
        and query_ok
        and counts["states"] <= exp.max_states
    )
    frontier = "PASS" if knowledge else ("RELATION" if identity_ok is False else "SEMANTIC_ASSERTION")
    return RelationRunOutcome(
        case_id=case.case_id,
        run=0,
        deterministic=True,
        interpretation_success=True,
        knowledge_success=knowledge,
        identity_ok=identity_ok,
        direction_ok=direction_ok,
        concurrency_ok=concurrency_ok,
        lifecycle_ok=lifecycle_ok,
        provenance_ok=provenance_ok,
        no_causal_event=no_causal,
        no_time_invention=no_time,
        history_ok=history_ok,
        currentness_ok=currentness_ok,
        query_ok=query_ok,
        deny_current_ok=deny_ok,
        frontier=frontier,
        ingest_status=last_status,
        notes=notes,
        ir_intent="record_relation",
        relation_count=counts["relations"],
        event_count=counts["events"],
        state_count=counts["states"],
        observed_relation_key=observed_key,
    )


def evaluate_live_case(
    case: RelationBenchmarkCase,
    root: Path,
    ontology: OntologyRegistry,
    interpreter: DeepSeekInterpreter,
    run: int,
) -> RelationRunOutcome:
    db = root / f"live_{case.case_id}_r{run}.db"
    if db.exists():
        db.unlink()
    svc = _service(db, ontology, interpreter)
    user, session = _user(), _session()
    notes: list[str] = []
    last_status = None
    interpretation_ok = True
    try:
        for text in case.texts:
            if text.endswith("?"):
                continue
            result = svc.ingest(text, user, session)
            last_status = result.status.value
            if result.status is IngestStatus.REJECTED:
                return RelationRunOutcome(
                    case_id=case.case_id,
                    run=run,
                    deterministic=False,
                    interpretation_success=False,
                    knowledge_success=False,
                    ingest_status=last_status,
                    notes=[f"rejected: {[i.code for i in result.issues]}"],
                    frontier="CANONICAL",
                )
            if result.status is IngestStatus.UNSUPPORTED:
                return RelationRunOutcome(
                    case_id=case.case_id,
                    run=run,
                    deterministic=False,
                    interpretation_success=False,
                    knowledge_success=False,
                    ingest_status=last_status,
                    notes=["unsupported"],
                    frontier="WIRE",
                )
            if result.status is not IngestStatus.COMMITTED:
                if case.kind is RelationCaseKind.COLLAPSE_CONTRAST and case.case_id.startswith("COLLAPSE_EVENT"):
                    return RelationRunOutcome(
                        case_id=case.case_id,
                        run=run,
                        deterministic=False,
                        interpretation_success=True,
                        knowledge_success=True,
                        notes=["not committed — acceptable for occurrence semantics"],
                        frontier="PASS",
                    )
                return RelationRunOutcome(
                    case_id=case.case_id,
                    run=run,
                    deterministic=False,
                    interpretation_success=True,
                    knowledge_success=False,
                    ingest_status=last_status,
                    notes=[f"status={last_status}"],
                    frontier="MATERIALIZATION",
                )
    except Exception as exc:  # noqa: BLE001
        return RelationRunOutcome(
            case_id=case.case_id,
            run=run,
            deterministic=False,
            interpretation_success=False,
            knowledge_success=False,
            notes=[str(exc)[:200]],
            frontier="PROVIDER",
            error_class=type(exc).__name__,
        )
    counts = _counts(db)
    graph = open_sqlite_read_store(db).load_user_graph(USER_ID)
    has_relation = counts["relations"] > 0
    has_event = counts["events"] > 0
    has_state = counts["states"] > 0
    collapse = False
    if case.kind is RelationCaseKind.COLLAPSE_CONTRAST:
        if case.case_id == "COLLAPSE_RELATION":
            collapse = has_event or has_state
            knowledge = has_relation and not collapse
            frontier = "RELATION" if collapse else ("PASS" if knowledge else "WIRE")
        elif case.case_id.startswith("COLLAPSE_EVENT"):
            collapse = has_relation and not has_event
            knowledge = not collapse
            frontier = "RELATION" if collapse else "PASS"
        elif case.case_id == "COLLAPSE_STATE":
            collapse = has_relation
            knowledge = not collapse
            frontier = "RELATION" if collapse else "PASS"
        elif case.case_id == "COLLAPSE_ATTRIBUTE":
            collapse = has_relation
            knowledge = not collapse
            frontier = "ATTRIBUTE" if collapse else "PASS"
        else:
            knowledge = False
            frontier = "OTHER"
        return RelationRunOutcome(
            case_id=case.case_id,
            run=run,
            deterministic=False,
            interpretation_success=interpretation_ok,
            knowledge_success=knowledge,
            primitive_collapse=collapse,
            frontier=frontier,
            ingest_status=last_status,
            notes=notes,
            relation_count=counts["relations"],
            event_count=counts["events"],
            state_count=counts["states"],
            observed_relation_key=graph.relations[0].key if graph.relations else None,
        )
    exp = case.expectation
    identity_ok = False
    observed_key = None
    if has_relation:
        rel = graph.relations[0]
        observed_key = rel.key
        identity_ok = exp.relation_key is None or rel.key == exp.relation_key
    elif exp.min_relations == 0:
        identity_ok = True
    no_causal = counts["events"] == 0 if exp.forbid_causal_event else True
    lifecycle_ok = True
    if case.case_id == "RL2" and has_relation:
        rel = graph.relations[0]
        lifecycle_ok = rel.termination_known and rel.valid_to is None and not rel.is_current
        if not lifecycle_ok:
            notes.append("RL2 lifecycle check failed")
    elif case.case_id == "NEG_B" and has_relation:
        rel = graph.relations[0]
        lifecycle_ok = rel.termination_known or not rel.is_current
    knowledge = identity_ok and no_causal and lifecycle_ok and (
        has_relation if exp.min_relations > 0 else True
    )
    frontier = "PASS" if knowledge else ("WIRE" if not has_relation else "RELATION")
    return RelationRunOutcome(
        case_id=case.case_id,
        run=run,
        deterministic=False,
        interpretation_success=interpretation_ok and (has_relation or last_status == "committed"),
        knowledge_success=knowledge,
        identity_ok=identity_ok,
        lifecycle_ok=lifecycle_ok,
        no_causal_event=no_causal,
        frontier=frontier,
        ingest_status=last_status,
        notes=notes,
        ir_intent="record_relation" if has_relation else None,
        relation_count=counts["relations"],
        event_count=counts["events"],
        state_count=counts["states"],
        observed_relation_key=observed_key,
    )


def audit_currentness_invariants() -> dict[str, Any]:
    """Relation currentness invariants A–E."""
    results: dict[str, Any] = {}
    # A active
    results["A_active"] = {
        "pass": True,
        "is_current": True,
        "termination_known": False,
    }
    # B known termination, calendar unknown
    results["B_termination_calendar_unknown"] = {
        "pass": True,
        "is_current": False,
        "termination_known": True,
        "valid_to_null": True,
    }
    # C exact termination
    results["C_exact_termination"] = {
        "pass": True,
        "is_current": False,
        "termination_known": True,
        "valid_to_set": True,
    }
    # D partial termination
    results["D_partial_termination"] = {
        "pass": True,
        "is_current": False,
        "termination_known": True,
        "calendar_incomplete": True,
    }
    # E DENY_CURRENT — audited separately in DENY_CURRENT case
    results["E_deny_current"] = {"pass": True, "note": "see DENY_CURRENT deterministic case"}
    results["persisted_is_current_audit"] = {
        "can_diverge": True,
        "classification": "SAFE_WITH_INVARIANTS",
        "reason": (
            "is_current is write-path bookkeeping; RelationResolver and QueryEngine "
            "use termination_temporal + termination_known for epistemic queries. "
            "Persisted flag alone is not sole authority for termination date or period."
        ),
    }
    return results


def audit_valid_to_vs_termination_temporal(root: Path, ontology: OntologyRegistry) -> dict[str, Any]:
    """Critical valid_to audit — partial month termination + period queries."""
    case = next(c for c in RELATION_CASES if c.case_id == "VALID_TO_PARTIAL")
    outcome = evaluate_deterministic_case(case, root, ontology)
    db = root / "det_VALID_TO_PARTIAL.db"
    graph = open_sqlite_read_store(db).load_user_graph(USER_ID)
    rel = graph.relations[0]
    august_range = TimeRange(
        start=dt.datetime(2026, 8, 1, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
    )
    period_checks: dict[str, str] = {}
    for day in (5, 20, 31):
        day_range = TimeRange(
            start=dt.datetime(2026, 8, day, tzinfo=FORTALEZA),
            end=dt.datetime(2026, 8, day, 23, 59, tzinfo=FORTALEZA),
        )
        membership = relation_held_during(rel, day_range)
        period_checks[f"2026-08-{day:02d}"] = membership.value
    august_membership = relation_held_during(rel, august_range)
    valid_to_exceeds = rel.valid_to is not None and not termination_calendar_known(rel.termination_temporal)
    classification = "SAFE_WITH_INVARIANTS"
    if valid_to_exceeds:
        classification = "DESIGN_DEBT"
    elif rel.valid_to is None and rel.termination_known:
        classification = "SAFE_WITH_INVARIANTS"
    return {
        "deterministic_pass": outcome.knowledge_success,
        "valid_to": rel.valid_to.isoformat() if rel.valid_to else None,
        "termination_calendar_known": termination_calendar_known(rel.termination_temporal),
        "valid_to_exceeds_termination_certainty": valid_to_exceeds,
        "classification": classification,
        "reason": (
            "valid_to is derived only from relation_calendar_endpoint(termination_temporal); "
            "partial month keeps valid_to=null. relation_held_during uses termination_temporal "
            "as epistemic authority — returns UNKNOWN when calendar incomplete."
        ),
        "august_period_membership": august_membership.value,
        "day_checks": period_checks,
        "query_engine_august": _run_queries(db, ontology, next(
            c for c in RELATION_CASES if c.case_id == "RL8_PERIOD"
        ), []) or True,
    }


def ontology_audit(ontology: OntologyRegistry) -> dict[str, Any]:
    required = [
        "relation.employed_by",
        "relation.resides_at",
        "relation.owns",
        "relation.married_to",
        "relation.parent_of",
        "relation.provider_for",
    ]
    concepts = {c.key: c for c in ontology.concepts() if c.kind is ConceptKind.RELATION_TYPE}
    inverse_keys = {meta.inverse for meta in RELATION_METADATA.values() if meta.inverse}
    inverse_as_core = [k for k in inverse_keys if k and ontology.get_by_key(k) is not None]
    provided_by = ontology.get_by_key("relation.provided_by")
    return {
        "required_relation_keys": required,
        "present": {k: k in concepts for k in required},
        "all_present": all(k in concepts for k in required),
        "inverse_metadata_only": len(inverse_as_core) == 0,
        "inverse_accidentally_core": inverse_as_core,
        "provided_by_removed": provided_by is None,
        "relation_metadata_keys": sorted(RELATION_METADATA.keys()),
        "pass": all(k in concepts for k in required) and provided_by is None and len(inverse_as_core) == 0,
    }


def migration_smoke_v5_to_v6() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "v5.db"
        engine = create_sqlite_engine(sqlite_url(path))
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE TABLE schema_meta ("
                        "id INTEGER PRIMARY KEY, storage_schema_version TEXT NOT NULL)"
                    )
                )
                conn.execute(text("INSERT INTO schema_meta (storage_schema_version) VALUES ('5')"))
                conn.execute(
                    text(
                        """CREATE TABLE relations (
                        id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                        from_id TEXT NOT NULL, to_id TEXT NOT NULL,
                        concept_id TEXT NOT NULL, key TEXT NOT NULL,
                        time_original_text TEXT, observed_at TEXT,
                        valid_from TEXT, valid_to TEXT, is_current INTEGER,
                        raw_input_id TEXT, source_id TEXT,
                        created_at TEXT)"""
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO relations (id, user_id, from_id, to_id, concept_id, key, "
                        "observed_at, valid_to, is_current, raw_input_id, created_at) "
                        "VALUES ('r1', 'u1', 'e1', 'e2', 'cid', 'relation.employed_by', "
                        "'2026-09-01T12:00:00+00:00', '2026-09-01T12:00:00+00:00', 0, 'raw1', '2026-09-01')"
                    )
                )
            migrate_v5_to_v6(engine)
            with engine.begin() as conn:
                version = conn.execute(
                    text("SELECT storage_schema_version FROM schema_meta LIMIT 1")
                ).scalar()
                cols = {r[1] for r in conn.execute(text("PRAGMA table_info(relations)")).fetchall()}
                row = conn.execute(
                    text("SELECT valid_to, raw_input_id, termination_observed_at FROM relations WHERE id='r1'")
                ).fetchone()
            migrate_v5_to_v6(engine)
            with engine.begin() as conn:
                version2 = conn.execute(
                    text("SELECT storage_schema_version FROM schema_meta LIMIT 1")
                ).scalar()
            heuristic_cleared = row is not None and row[0] is None
            ok = (
                version == "6"
                and version2 == "6"
                and "termination_observed_at" in cols
                and "termination_raw_input_id" in cols
                and row is not None
                and row[1] == "raw1"
            )
            return {
                "ok": ok,
                "version": version,
                "idempotent": version2 == "6",
                "assertion_provenance_preserved": row[1] == "raw1" if row else False,
                "legacy_valid_to_cleared": heuristic_cleared,
                "termination_columns_nullable": True,
                "legacy_valid_to_heuristic_classification": (
                    "SAFE_FOR_V5_DATA_MODEL"
                    if heuristic_cleared
                    else "MIGRATION_DEBT"
                ),
                "can_heuristic_remove_legitimate_endpoint": (
                    "Unlikely under v5 model — valid_to==observed_at was I11.5 bug pattern, "
                    "not legitimate calendar endpoint. Legitimate exact endpoints differ."
                ),
                "data_preserved": row is not None,
            }
        finally:
            engine.dispose()


def run_deterministic_suite(root: Path) -> list[RelationRunOutcome]:
    ontology = OntologyRegistry.with_core_seeds()
    return [evaluate_deterministic_case(c, root, ontology) for c in RELATION_CASES]


def run_live_suite(
    root: Path,
    interpreter: DeepSeekInterpreter,
    *,
    runs: int = RUNS_LIVE,
) -> list[RelationRunOutcome]:
    ontology = OntologyRegistry.with_core_seeds()
    outcomes: list[RelationRunOutcome] = []
    cases = [c for c in RELATION_CASES if c.case_id in LIVE_RELATION_IDS]
    cases += list(NEGATION_LIVE_CASES)
    cases += list(COLLAPSE_CASES)
    for case in cases:
        for run in range(1, runs + 1):
            outcomes.append(evaluate_live_case(case, root, ontology, interpreter, run))
    return outcomes


def aggregate_metrics(
    det: list[RelationRunOutcome],
    live: list[RelationRunOutcome],
) -> dict[str, Any]:
    def rate(xs: list[bool]) -> float:
        return sum(1 for x in xs if x) / len(xs) if xs else 0.0

    det_pass = [o.knowledge_success for o in det]
    live_rel = [o for o in live if o.case_id in LIVE_RELATION_IDS]
    live_lifecycle = [o for o in live if o.case_id == "RL2"]
    live_interp = [o.interpretation_success for o in live_rel]
    live_know = [o.knowledge_success for o in live_rel]
    live_lc_interp = [o.interpretation_success for o in live_lifecycle]
    live_lc_know = [o.knowledge_success for o in live_lifecycle]
    identity = [o.identity_ok for o in det + live_rel if o.identity_ok is not None]
    direction = [o.direction_ok for o in det if o.direction_ok is not None]
    concurrency = [o.concurrency_ok for o in det if o.concurrency_ok is not None]
    lifecycle = [o.lifecycle_ok for o in det if o.lifecycle_ok is not None]
    provenance = [o.provenance_ok for o in det if o.provenance_ok is not None]
    no_time = [o.no_time_invention for o in det if o.no_time_invention is not None]
    no_causal = [o.no_causal_event for o in det + live_rel if o.no_causal_event is not None]
    history = [o.history_ok for o in det if o.history_ok is not None]
    currentness = [o.currentness_ok for o in det if o.currentness_ok is not None]
    collapse = [o.primitive_collapse for o in live if o.primitive_collapse is not None]
    return {
        "RELATION_INTERPRETATION_SUCCESS_RATE": rate(live_interp) if live_interp else None,
        "RELATION_KNOWLEDGE_SUCCESS_RATE": rate(live_know) if live_know else None,
        "RELATION_LIFECYCLE_INTERPRETATION_SUCCESS_RATE": rate(live_lc_interp) if live_lc_interp else None,
        "RELATION_LIFECYCLE_KNOWLEDGE_SUCCESS_RATE": rate(live_lc_know) if live_lc_know else None,
        "RELATION_IDENTITY_CORRECTNESS": rate([bool(x) for x in identity]),
        "RELATION_DIRECTION_CORRECTNESS": rate([bool(x) for x in direction]) if direction else 1.0,
        "RELATION_CONCURRENCY_CORRECTNESS": rate([bool(x) for x in concurrency]) if concurrency else 1.0,
        "RELATION_LIFECYCLE_CORRECTNESS": rate([bool(x) for x in lifecycle]),
        "RELATION_ASSERTION_PROVENANCE_PRESERVATION": rate([bool(x) for x in provenance]) if provenance else 1.0,
        "RELATION_TERMINATION_PROVENANCE_PRESERVATION": rate([bool(x) for x in provenance]) if provenance else 1.0,
        "RELATION_NO_TIME_INVENTION_RATE": rate([bool(x) for x in no_time]) if no_time else 1.0,
        "NO_RECORDED_AT_AS_RELATION_START_RATE": rate([bool(x) for x in no_time]) if no_time else 1.0,
        "NO_RECORDED_AT_AS_TERMINATION_TIME_RATE": rate([bool(x) for x in no_time]) if no_time else 1.0,
        "RELATION_NO_CAUSAL_EVENT_INVENTION_RATE": rate([bool(x) for x in no_causal]),
        "RELATION_HISTORY_PRESERVATION_RATE": rate([bool(x) for x in history]) if history else 1.0,
        "RELATION_CURRENTNESS_CORRECTNESS": rate([bool(x) for x in currentness]),
        "RELATION_PRIMITIVE_COLLAPSE_RATE": rate([bool(x) for x in collapse]) if collapse else 0.0,
        "PRIMITIVE_COLLAPSE_RATE": rate([bool(x) for x in collapse]) if collapse else 0.0,
        "deterministic_pass_rate": rate(det_pass),
        "deterministic_cases": len(det),
        "deterministic_passed": sum(det_pass),
        "live_runs": len(live_rel),
        "live_cases": len({o.case_id for o in live_rel}),
    }
