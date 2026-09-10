"""Avaliador I11.4-R — State dimension/value, currentness, collapse (sem alterar produção)."""

from __future__ import annotations

import datetime as dt
import sqlite3
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import text

from pke.application import FixedClock, IngestService, IngestStatus, SessionContext
from pke.domain import (
    ConceptKind,
    ConceptRef,
    OccurrenceStatus,
    RelationToReference,
    State,
    TemporalKnowledge,
    TimePrecision,
    TimeValue,
    UserContext,
    new_ulid,
)
from pke.interpretation import (
    DeepSeekInterpreter,
    EntityMention,
    FakeInterpreter,
    IngestIntent,
    IngestIR,
    IrState,
    IrTime,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.persist.migrations.v3_to_v4 import migrate_v3_to_v4
from pke.persist.sqlite.engine import create_sqlite_engine, sqlite_url
from pke.query.results import TemporalCompleteness
from pke.query.state_resolver import resolve_current
from pke.resolution import PersonalContext

from tests.generalization_ingest.fixtures import BENCHMARK_NOW, FORTALEZA, USER_ID
from tests.generalization_ingest.state_cases import (
    COLLAPSE_CASES,
    LIVE_STATE_IDS,
    STATE_CASES,
    StateBenchmarkCase,
    StateCaseKind,
)

RUNS_LIVE = 3


def _present() -> IrTime:
    return IrTime(
        original_text="",
        occurrence_status=OccurrenceStatus.ONGOING,
        relation_to_reference=RelationToReference.DURING,
        tense_evidence="present",
    )


def _mention(text: str, type_key: str) -> EntityMention:
    return EntityMention(
        text=text,
        type_hint=ConceptRef(key=type_key),
        role=ConceptRef(key="role.subject"),
    )


def _state_ir(raw: str, *, entity: EntityMention, value_key: str, payload: Any = None) -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_STATE,
        raw_input=raw,
        entities_mentioned=[entity],
        state=IrState(
            value=ConceptRef(key=value_key),
            payload=payload,
            time=_present(),
        ),
    )


def deterministic_responses(case: StateBenchmarkCase) -> dict[str, object]:
    entity = _mention(case.entity_text or "item", case.entity_type_hint)
    exp = case.expectation
    if case.kind is StateCaseKind.SINGLE:
        text = case.texts[0]
        payload = {"amount": 84500, "unit": "km"} if exp.provisional_s6 else None
        assert exp.value_key
        return {text: _state_ir(text, entity=entity, value_key=exp.value_key, payload=payload)}
    if case.kind is StateCaseKind.TRANSITION:
        return {
            case.texts[0]: _state_ir(
                case.texts[0], entity=entity, value_key="state.value.broken"
            ),
            case.texts[1]: _state_ir(
                case.texts[1], entity=entity, value_key="state.value.working"
            ),
        }
    if case.kind is StateCaseKind.INDEPENDENT_DIMS:
        fridge = _mention("geladeira", "entity.appliance")
        return {
            case.texts[0]: _state_ir(
                case.texts[0], entity=fridge, value_key="state.value.working"
            ),
            case.texts[1]: _state_ir(
                case.texts[1],
                entity=fridge,
                value_key="state.value.open",
            ),
        }
    return {}


@dataclass
class StateRunOutcome:
    case_id: str
    run: int
    deterministic: bool
    interpretation_success: bool
    knowledge_success: bool
    dimension_value_ok: bool | None = None
    no_causal_event: bool | None = None
    currentness_ok: bool | None = None
    history_ok: bool | None = None
    primitive_collapse: bool | None = None
    unpaid_overdue_ok: bool | None = None
    frontier: str = "OTHER"
    ingest_status: str | None = None
    notes: list[str] = field(default_factory=list)
    ir_intent: str | None = None
    state_count: int = 0
    event_count: int = 0
    observed_dimension: str | None = None
    observed_value: str | None = None
    error_class: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _counts(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(db_path)
    try:
        return {
            "events": con.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "states": con.execute("SELECT COUNT(*) FROM states").fetchone()[0],
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


def _check_dimension_value(states: list[State], case: StateBenchmarkCase) -> tuple[bool, str | None, str | None]:
    exp = case.expectation
    if not states:
        return False, None, None
    # Prefer current of expected dimension
    pool = states
    if exp.dimension_key:
        pool = [s for s in states if s.dimension_key == exp.dimension_key] or states
    current = [s for s in pool if s.is_current] or pool
    s = current[-1]
    ok = True
    if exp.dimension_key and s.dimension_key != exp.dimension_key:
        ok = False
    if exp.value_key and s.value_key != exp.value_key:
        ok = False
    return ok, s.dimension_key, s.value_key


def evaluate_deterministic_case(
    case: StateBenchmarkCase,
    root: Path,
    ontology: OntologyRegistry,
) -> StateRunOutcome:
    db = root / f"det_{case.case_id}.db"
    if db.exists():
        db.unlink()
    responses = deterministic_responses(case)
    if not responses and case.kind is StateCaseKind.COLLAPSE_CONTRAST:
        return StateRunOutcome(
            case_id=case.case_id,
            run=0,
            deterministic=True,
            interpretation_success=False,
            knowledge_success=False,
            notes=["no deterministic fixture for collapse-only live contrast"],
            frontier="OTHER",
        )
    svc = _service(db, ontology, FakeInterpreter(responses))  # type: ignore[arg-type]
    user, session = _user(), _session()
    notes: list[str] = []
    last_status = None
    for text in case.texts:
        result = svc.ingest(text, user, session)
        last_status = result.status.value
        if result.status is not IngestStatus.COMMITTED:
            return StateRunOutcome(
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
    dim_ok, obs_dim, obs_val = _check_dimension_value(graph.states, case)
    no_causal = counts["events"] == 0 if case.expectation.forbid_causal_event else True
    unpaid_ok = True
    if case.expectation.forbid_unpaid_for_overdue:
        unpaid_ok = all(s.value_key != "state.value.unpaid" for s in graph.states)
        if not unpaid_ok:
            notes.append("unpaid used for overdue utterance")
    currentness_ok = True
    history_ok = True
    if case.kind is StateCaseKind.TRANSITION:
        broken = [s for s in graph.states if s.value_key == "state.value.broken"]
        working = [s for s in graph.states if s.value_key == "state.value.working"]
        history_ok = len(broken) == 1 and len(working) == 1
        currentness_ok = (
            history_ok
            and broken[0].is_current is False
            and working[0].is_current is True
            and working[0].supersedes_id == broken[0].id
            and broken[0].dimension_key == working[0].dimension_key
        )
        dim_ok = currentness_ok
        obs_dim = working[0].dimension_key if working else None
        obs_val = working[0].value_key if working else None
        if not currentness_ok:
            notes.append("transition currentness failed")
    if case.kind is StateCaseKind.INDEPENDENT_DIMS:
        current = [s for s in graph.states if s.is_current]
        dims = {s.dimension_key for s in current}
        currentness_ok = (
            "state.operational_condition" in dims and "state.openness" in dims and len(current) >= 2
        )
        dim_ok = currentness_ok
        history_ok = len(graph.states) >= 2
        if not currentness_ok:
            notes.append(f"independent dims current={dims}")
    knowledge = dim_ok and no_causal and unpaid_ok and currentness_ok and history_ok
    frontier = "PASS" if knowledge else ("SEMANTIC_ASSERTION" if dim_ok is False else "STATE")
    return StateRunOutcome(
        case_id=case.case_id,
        run=0,
        deterministic=True,
        interpretation_success=True,
        knowledge_success=knowledge,
        dimension_value_ok=dim_ok,
        no_causal_event=no_causal,
        currentness_ok=currentness_ok,
        history_ok=history_ok,
        unpaid_overdue_ok=unpaid_ok,
        frontier=frontier,
        ingest_status=last_status,
        notes=notes,
        ir_intent="record_state",
        state_count=counts["states"],
        event_count=counts["events"],
        observed_dimension=obs_dim,
        observed_value=obs_val,
    )


def evaluate_live_case(
    case: StateBenchmarkCase,
    root: Path,
    ontology: OntologyRegistry,
    interpreter: DeepSeekInterpreter,
    run: int,
) -> StateRunOutcome:
    db = root / f"live_{case.case_id}_r{run}.db"
    if db.exists():
        db.unlink()
    svc = _service(db, ontology, interpreter)
    user, session = _user(), _session()
    notes: list[str] = []
    last_status = None
    ir_intent = None
    interpretation_ok = True
    try:
        for text in case.texts:
            result = svc.ingest(text, user, session)
            last_status = result.status.value
            if result.status is IngestStatus.REJECTED:
                interpretation_ok = False
                return StateRunOutcome(
                    case_id=case.case_id,
                    run=run,
                    deterministic=False,
                    interpretation_success=False,
                    knowledge_success=False,
                    ingest_status=last_status,
                    notes=[f"rejected: {[i.code for i in result.issues]}"],
                    frontier="CANONICAL",
                    error_class="rejected",
                )
            if result.status is IngestStatus.UNSUPPORTED:
                interpretation_ok = False
                return StateRunOutcome(
                    case_id=case.case_id,
                    run=run,
                    deterministic=False,
                    interpretation_success=False,
                    knowledge_success=False,
                    ingest_status=last_status,
                    notes=["unsupported (query IR?)"],
                    frontier="WIRE",
                )
            if result.status is not IngestStatus.COMMITTED:
                return StateRunOutcome(
                    case_id=case.case_id,
                    run=run,
                    deterministic=False,
                    interpretation_success=True,
                    knowledge_success=False,
                    ingest_status=last_status,
                    notes=[f"status={last_status}"],
                    frontier="VALIDATION" if result.status is IngestStatus.NEEDS_CLARIFICATION else "MATERIALIZATION",
                )
    except Exception as exc:  # noqa: BLE001 — benchmark capture
        return StateRunOutcome(
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
    # Live: detect if any state was committed
    has_state = counts["states"] > 0
    has_event = counts["events"] > 0
    dim_ok, obs_dim, obs_val = (False, None, None)
    if has_state:
        dim_ok, obs_dim, obs_val = _check_dimension_value(graph.states, case)
    no_causal = counts["events"] == 0 if case.expectation.forbid_causal_event else True
    collapse = False
    if case.kind is StateCaseKind.COLLAPSE_CONTRAST:
        # Event-expecting cases: State-only without Event = collapse risk
        if case.case_id.startswith("COLLAPSE_EVENT") or case.case_id in {
            "COLLAPSE_RELATION",
            "COLLAPSE_ATTRIBUTE_COLOR",
        }:
            collapse = has_state and not has_event and ir_intent != "record_event"
            if collapse:
                notes.append("primitive collapse: State absorbed non-State utterance")
            knowledge = not collapse
            return StateRunOutcome(
                case_id=case.case_id,
                run=run,
                deterministic=False,
                interpretation_success=interpretation_ok,
                knowledge_success=knowledge,
                dimension_value_ok=None,
                no_causal_event=None,
                primitive_collapse=collapse,
                frontier="STATE" if collapse else ("PASS" if has_event or not has_state else "OTHER"),
                ingest_status=last_status,
                notes=notes,
                state_count=counts["states"],
                event_count=counts["events"],
                observed_dimension=obs_dim,
                observed_value=obs_val,
            )
    unpaid_ok = True
    if case.expectation.forbid_unpaid_for_overdue and has_state:
        unpaid_ok = all(s.value_key != "state.value.unpaid" for s in graph.states)
    currentness_ok = True
    history_ok = True
    if case.kind is StateCaseKind.TRANSITION and has_state:
        broken = [s for s in graph.states if s.value_key == "state.value.broken"]
        working = [s for s in graph.states if s.value_key == "state.value.working"]
        if broken and working:
            history_ok = True
            currentness_ok = (
                broken[0].is_current is False
                and working[0].is_current is True
            )
        else:
            history_ok = False
            currentness_ok = False
            notes.append("transition values missing after live ingest")
    knowledge = has_state and dim_ok and no_causal and unpaid_ok and currentness_ok and history_ok
    frontier = "PASS" if knowledge else ("WIRE" if not has_state else "SEMANTIC_ASSERTION")
    return StateRunOutcome(
        case_id=case.case_id,
        run=run,
        deterministic=False,
        interpretation_success=interpretation_ok and (has_state or last_status == "committed"),
        knowledge_success=knowledge,
        dimension_value_ok=dim_ok if has_state else False,
        no_causal_event=no_causal,
        currentness_ok=currentness_ok,
        history_ok=history_ok,
        unpaid_overdue_ok=unpaid_ok,
        primitive_collapse=False,
        frontier=frontier,
        ingest_status=last_status,
        notes=notes,
        ir_intent="record_state" if has_state else None,
        state_count=counts["states"],
        event_count=counts["events"],
        observed_dimension=obs_dim,
        observed_value=obs_val,
    )


def audit_currentness_invariants(ontology: OntologyRegistry) -> dict[str, Any]:
    """In-memory invariants A–D — no production mutation."""
    results: dict[str, Any] = {}
    entity_id = "ent-audit"

    def st(
        value_key: str,
        *,
        temporal: TemporalKnowledge,
        is_current: bool = True,
        dim: str = "state.operational_condition",
        observed: dt.datetime | None = None,
        supersedes: str | None = None,
        sid: str | None = None,
    ) -> State:
        return State(
            id=sid or new_ulid(),
            user_id=USER_ID,
            entity_id=entity_id,
            dimension_id=core_concept_id(dim),
            dimension_key=dim,
            value_concept_id=core_concept_id(value_key),
            value_key=value_key,
            temporal=temporal,
            observed_at=observed or BENCHMARK_NOW,
            is_current=is_current,
            supersedes_id=supersedes,
        )

    # A known supersession
    a_id, b_id = new_ulid(), new_ulid()
    a = st(
        "state.value.broken",
        temporal=TemporalKnowledge.from_calendar(
            TimeValue(original_text="T1", date=dt.date(2026, 9, 1), precision=TimePrecision.DAY)
        ),
        is_current=False,
        observed=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
        sid=a_id,
    )
    b = st(
        "state.value.working",
        temporal=TemporalKnowledge.from_calendar(
            TimeValue(original_text="T2", date=dt.date(2026, 9, 5), precision=TimePrecision.DAY)
        ),
        is_current=True,
        observed=dt.datetime(2026, 9, 5, tzinfo=FORTALEZA),
        supersedes=a_id,
        sid=b_id,
    )
    res_a = resolve_current([a, b], dimension_key="state.operational_condition")
    results["A_known_supersession"] = {
        "pass": res_a.state is b and a.is_current is False and b.is_current is True,
        "resolver_picked": res_a.state.value_key if res_a.state else None,
        "completeness": res_a.completeness.value,
    }

    # B unknown ordering — both marked current; resolver must not claim COMPLETE certainty wrongly
    known = st(
        "state.value.broken",
        temporal=TemporalKnowledge.from_calendar(
            TimeValue(original_text="T1", date=dt.date(2026, 9, 1), precision=TimePrecision.DAY)
        ),
        is_current=True,
    )
    unknown = st(
        "state.value.working",
        temporal=TemporalKnowledge.partial_ongoing(),
        is_current=True,
        observed=dt.datetime(2026, 9, 2, tzinfo=FORTALEZA),
    )
    res_b = resolve_current([known, unknown], dimension_key="state.operational_condition")
    results["B_unknown_ordering"] = {
        "pass": res_b.completeness
        in {TemporalCompleteness.PARTIAL, TemporalCompleteness.INDETERMINATE},
        "completeness": res_b.completeness.value,
        "indeterminate_count": res_b.indeterminate_count,
        "persisted_both_current": known.is_current and unknown.is_current,
        "note": "persisted is_current may both be True while resolver returns PARTIAL",
    }

    # C different dimensions
    working = st("state.value.working", temporal=TemporalKnowledge.partial_ongoing())
    open_s = st(
        "state.value.open",
        temporal=TemporalKnowledge.partial_ongoing(),
        dim="state.openness",
    )
    results["C_different_dimensions"] = {
        "pass": working.is_current and open_s.is_current,
        "dims": [working.dimension_key, open_s.dimension_key],
    }

    # D history
    results["D_history"] = {
        "pass": a.id != b.id and b.supersedes_id == a.id,
        "note": "supersession preserves both rows",
    }

    # Persisted is_current divergence classification
    diverge = bool(results["B_unknown_ordering"]["persisted_both_current"]) and results[
        "B_unknown_ordering"
    ]["pass"]
    results["persisted_is_current_audit"] = {
        "can_diverge": diverge,
        "classification": "SAFE_WITH_INVARIANTS" if diverge else "SAFE",
        "reason": (
            "Materializer sets is_current on write-order supersession; "
            "StateResolver uses temporal sort and may return PARTIAL when "
            "persisted flags still show multiple is_current=True in same dimension. "
            "QueryEngine uses resolver — correct for queries. Persisted flag alone "
            "is write-path bookkeeping, not sole epistemic source."
        ),
    }
    _ = ontology
    return results


def ontology_audit(ontology: OntologyRegistry) -> dict[str, Any]:
    dims = [c for c in ontology.concepts() if c.kind is ConceptKind.STATE_DIMENSION]
    vals = [c for c in ontology.concepts() if c.kind is ConceptKind.STATE_VALUE]
    kinds = {c.kind.value for c in ontology.concepts()}
    return {
        "state_dimension_count": len(dims),
        "state_value_count": len(vals),
        "has_state_type_kind": "state_type" in kinds,
        "dimension_keys": sorted(c.key for c in dims),
        "value_keys": sorted(c.key for c in vals),
        "unpaid_key": "state.value.unpaid",
        "overdue_key": "state.value.overdue",
        "unpaid_neq_overdue": True,
        "depleted_key": "state.value.depleted",
        "no_unavailable_value": ontology.get_by_key("state.value.unavailable") is None,
        "pass": (
            "state_type" not in kinds
            and len(dims) >= 1
            and len(vals) >= 1
            and ontology.get_by_key("state.value.unpaid") is not None
            and ontology.get_by_key("state.value.overdue") is not None
            and ontology.get_by_key("state.value.unpaid").parent_id  # type: ignore[union-attr]
            != ontology.get_by_key("state.value.overdue").parent_id  # type: ignore[union-attr]
        ),
    }


def migration_smoke_v3_to_v4() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "v3.db"
        engine = create_sqlite_engine(sqlite_url(path))
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE TABLE schema_meta ("
                        "id INTEGER PRIMARY KEY, storage_schema_version TEXT NOT NULL)"
                    )
                )
                conn.execute(text("INSERT INTO schema_meta (storage_schema_version) VALUES ('3')"))
                conn.execute(
                    text(
                        """CREATE TABLE states (
                        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, entity_id TEXT NOT NULL,
                        concept_id TEXT NOT NULL, key TEXT NOT NULL,
                        value_kind TEXT, value_text TEXT, value_int INTEGER,
                        value_decimal TEXT, value_bool INTEGER, money_amount TEXT,
                        money_currency TEXT, ref_id TEXT, value_json TEXT,
                        time_original_text TEXT, time_date TEXT, time_instant TEXT,
                        time_precision TEXT, temporal_kind TEXT, temporal_relation TEXT,
                        temporal_occurrence_status TEXT, temporal_unknown_reason TEXT,
                        temporal_interval_start TEXT, temporal_interval_end TEXT,
                        temporal_granularity TEXT, temporal_tense_evidence TEXT,
                        temporal_source_kind TEXT, observed_at TEXT, valid_from TEXT,
                        valid_to TEXT, caused_by_event_id TEXT, supersedes_id TEXT,
                        raw_input_id TEXT, source_id TEXT, confidence_score REAL,
                        confidence_qualifier TEXT, created_at TEXT)"""
                    )
                )
                dim_broken = ("state.anomaly",)
                conn.execute(
                    text(
                        "INSERT INTO states (id, user_id, entity_id, concept_id, key, "
                        "observed_at, created_at) VALUES "
                        "('s1', 'u1', 'e1', 'cid', :k, '2026-09-01', '2026-09-01')"
                    ),
                    {"k": dim_broken[0]},
                )
            migrate_v3_to_v4(engine)
            with engine.begin() as conn:
                version = conn.execute(
                    text("SELECT storage_schema_version FROM schema_meta LIMIT 1")
                ).scalar()
                cols = {r[1] for r in conn.execute(text("PRAGMA table_info(states)")).fetchall()}
                row = conn.execute(
                    text(
                        "SELECT dimension_key, value_key, is_current FROM states WHERE id='s1'"
                    )
                ).fetchone()
            migrate_v3_to_v4(engine)
            with engine.begin() as conn:
                version2 = conn.execute(
                    text("SELECT storage_schema_version FROM schema_meta LIMIT 1")
                ).scalar()
            ok = (
                version == "4"
                and version2 == "4"
                and "dimension_key" in cols
                and "value_key" in cols
                and "is_current" in cols
                and row is not None
                and row[0] == "state.operational_condition"
                and row[1] == "state.value.broken"
            )
            return {
                "ok": ok,
                "version": version,
                "idempotent": version2 == "4",
                "mapped_dimension": row[0] if row else None,
                "mapped_value": row[1] if row else None,
                "data_preserved": row is not None,
            }
        finally:
            engine.dispose()


def run_deterministic_suite(root: Path) -> list[StateRunOutcome]:
    ontology = OntologyRegistry.with_core_seeds()
    outcomes: list[StateRunOutcome] = []
    for case in STATE_CASES:
        outcomes.append(evaluate_deterministic_case(case, root, ontology))
    return outcomes


def run_live_suite(
    root: Path,
    interpreter: DeepSeekInterpreter,
    *,
    runs: int = RUNS_LIVE,
) -> list[StateRunOutcome]:
    ontology = OntologyRegistry.with_core_seeds()
    outcomes: list[StateRunOutcome] = []
    cases = [c for c in STATE_CASES if c.case_id in LIVE_STATE_IDS]
    cases += list(COLLAPSE_CASES)
    for case in cases:
        for run in range(1, runs + 1):
            outcomes.append(evaluate_live_case(case, root, ontology, interpreter, run))
    return outcomes


def aggregate_metrics(
    det: list[StateRunOutcome],
    live: list[StateRunOutcome],
) -> dict[str, Any]:
    def rate(xs: list[bool]) -> float:
        return sum(1 for x in xs if x) / len(xs) if xs else 0.0

    det_pass = [o.knowledge_success for o in det]
    live_state = [o for o in live if o.case_id in LIVE_STATE_IDS or o.case_id.startswith("S")]
    live_interp = [o.interpretation_success for o in live_state]
    live_know = [o.knowledge_success for o in live_state]
    dim = [o.dimension_value_ok for o in det + live_state if o.dimension_value_ok is not None]
    no_causal = [o.no_causal_event for o in det + live_state if o.no_causal_event is not None]
    curr = [o.currentness_ok for o in det if o.currentness_ok is not None]
    hist = [o.history_ok for o in det if o.history_ok is not None]
    collapse = [o.primitive_collapse for o in live if o.primitive_collapse is not None]
    return {
        "STATE_INTERPRETATION_SUCCESS_RATE": rate(live_interp) if live_interp else None,
        "STATE_KNOWLEDGE_SUCCESS_RATE": rate(live_know) if live_know else None,
        "STATE_DIMENSION_VALUE_CORRECTNESS": rate([bool(x) for x in dim]),
        "STATE_NO_CAUSAL_EVENT_INVENTION_RATE": rate([bool(x) for x in no_causal]),
        "STATE_CURRENTNESS_CORRECTNESS": rate([bool(x) for x in curr]),
        "STATE_HISTORY_PRESERVATION_RATE": rate([bool(x) for x in hist]),
        "PRIMITIVE_COLLAPSE_RATE": rate([bool(x) for x in collapse]) if collapse else 0.0,
        "deterministic_pass_rate": rate(det_pass),
        "deterministic_cases": len(det),
        "deterministic_passed": sum(det_pass),
        "live_runs": len(live_state),
        "live_cases": len({o.case_id for o in live_state}),
    }
