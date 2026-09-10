"""Avaliador ingest-path — interpreter + pipeline + query."""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from pke.application import AskService, AskStatus, FixedClock, IngestService, IngestStatus, SessionContext
from pke.application.ask_results import AskResult
from pke.domain import (
    ConceptRef,
    EventStatus,
    OccurrenceStatus,
    RelationToReference,
    TemporalUnknownReason,
    UserContext,
)
from pke.interpretation import (
    DeepSeekInterpreter,
    EntityMention,
    FakeInterpreter,
    IngestIntent,
    IngestIR,
    InterpretationContext,
    InterpretationError,
    IrEvent,
    IrFact,
    IrQueryTime,
    IrTime,
    QueryIR,
    QuerySpec,
    RelativePeriod,
)
from pke.llm.errors import LlmInvalidResponseError, LlmSchemaValidationError
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.query.results import TemporalCompleteness
from pke.query.spec import AggregateKind, EntityAssociation, FactVersionPolicy, ResolvedQuerySpec, TimeRange
from pke.query.engine import QueryEngine
from pke.resolution import PersonalContext

from tests.generalization.cases import DEVELOPMENT_CASES
from tests.generalization.invariants import stability_label
from tests.generalization_ingest.assertions import (
    check_ingest_result,
    check_query_result,
    check_temporal_knowledge,
    invented_time_in_event,
)
from tests.generalization_ingest.cases import (
    DEV_INGEST_CLASSIFICATION,
    DETERMINISTIC_TEMPORAL_IDS,
    ArchitecturalGap,
    CaseMode,
    DevIngestStatus,
    FailureFrontierV2,
    IngestBenchmarkCase,
    QUERY_CASES,
    StageStatus,
    TEMPORAL_CASES,
    TemporalExpectation,
)
from tests.generalization_ingest.fixtures import (
    BENCHMARK_NOW,
    FORTALEZA,
    USER_ID,
    benchmark_session,
    benchmark_user,
    fresh_db_path,
    seed_corolla,
    seed_oil_change_event,
    with_seeded_corolla,
)
from tests.integration.test_partial_temporal_i113 import (
    RAW_T1,
    RAW_T2,
    RAW_T3,
    RAW_T4,
    RAW_T5_CLUTCH,
    RAW_T5_OIL,
    RAW_T5_QUERY,
    ir_t1,
    ir_t2,
    ir_t5_clutch,
    ir_t5_oil,
)
from tests.integration.test_ingest import _corolla, _service

RUNS_LIVE = 3


@dataclass
class StageTrace:
    provider_json: StageStatus = StageStatus.NOT_REACHED
    wire: StageStatus = StageStatus.NOT_REACHED
    canonical: StageStatus = StageStatus.NOT_REACHED
    resolution: StageStatus = StageStatus.NOT_REACHED
    candidate: StageStatus = StageStatus.NOT_REACHED
    validation: StageStatus = StageStatus.NOT_REACHED
    completeness: StageStatus = StageStatus.NOT_REACHED
    materialization: StageStatus = StageStatus.NOT_REACHED
    commit: StageStatus = StageStatus.NOT_REACHED
    query: StageStatus = StageStatus.NA

    def to_dict(self) -> dict[str, str]:
        return {k: v.value for k, v in asdict(self).items()}


@dataclass
class RunOutcome:
    case_id: str
    run: int
    text: str
    deterministic: bool
    interpretation_success: bool
    knowledge_success: bool
    query_success: bool | None
    stages: StageTrace
    frontier: FailureFrontierV2
    stage_notes: list[str] = field(default_factory=list)
    temporal_fails: list[str] = field(default_factory=list)
    query_fails: list[str] = field(default_factory=list)
    forbidden_time_hits: list[str] = field(default_factory=list)
    ingest_status: str | None = None
    error_class: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "run": self.run,
            "text": self.text,
            "deterministic": self.deterministic,
            "interpretation_success": self.interpretation_success,
            "knowledge_success": self.knowledge_success,
            "query_success": self.query_success,
            "stages": self.stages.to_dict(),
            "frontier": self.frontier.value,
            "stage_notes": self.stage_notes,
            "temporal_fails": self.temporal_fails,
            "query_fails": self.query_fails,
            "forbidden_time_hits": self.forbidden_time_hits,
            "ingest_status": self.ingest_status,
            "error_class": self.error_class,
        }


def _ir_tp03() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input="Comprei laranja.",
        domains=[ConceptRef(key="domain.shopping")],
        event=IrEvent(
            type=ConceptRef(key="event.purchase"),
            action=ConceptRef(key="action.buy"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text=""),
            facts=[],
        ),
    )


def _ir_tp05() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input="Troquei o óleo do Corolla em agosto.",
        domains=[ConceptRef(key="domain.vehicle")],
        entities_mentioned=[_corolla()],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.oil_change"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text="agosto", partial_month=8, partial_year=2026),
            facts=[],
        ),
    )


def _ir_tp06() -> IngestIR:
    from pke.domain import RelativeDay

    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input="Troquei o óleo do Corolla ontem.",
        domains=[ConceptRef(key="domain.vehicle")],
        entities_mentioned=[_corolla()],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.oil_change"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text="ontem", relative_day=RelativeDay.YESTERDAY),
            facts=[],
        ),
    )


def _ir_tp04() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input="Vou trocar o óleo do Corolla.",
        domains=[ConceptRef(key="domain.vehicle")],
        entities_mentioned=[_corolla()],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.oil_change"),
            status=EventStatus.PLANNED,
            time=IrTime(original_text=""),
            facts=[],
        ),
    )


def deterministic_ir(case_id: str) -> IngestIR | None:
    mapping = {
        "TP01": ir_t1,
        "TP02": ir_t2,
        "TP03": _ir_tp03,
        "TP04": _ir_tp04,
        "TP05": _ir_tp05,
        "TP06": _ir_tp06,
    }
    fn = mapping.get(case_id)
    return fn() if fn else None


def _query_ir_existential() -> QueryIR:
    return QueryIR(
        raw_input=RAW_T3,
        query=QuerySpec(
            intent="aggregate",
            entities=[_corolla()],
            entity_association="subject",
            event_types=[ConceptRef(key="event.vehicle_maintenance")],
            actions=[ConceptRef(key="action.replace")],
            aggregate="count",
        ),
    )


def _query_ir_period() -> QueryIR:
    return QueryIR(
        raw_input=RAW_T4,
        query=QuerySpec(
            intent="aggregate",
            entities=[_corolla()],
            entity_association="subject",
            event_types=[ConceptRef(key="event.vehicle_maintenance")],
            actions=[ConceptRef(key="action.replace")],
            aggregate="count",
            time=IrQueryTime(relative_period=RelativePeriod.THIS_MONTH),
        ),
    )


def _query_ir_sum() -> QueryIR:
    return QueryIR(
        raw_input=RAW_T5_QUERY,
        query=QuerySpec(
            intent="aggregate",
            entities=[_corolla()],
            entity_association="subject",
            event_types=[ConceptRef(key="event.vehicle_maintenance")],
            facts=[ConceptRef(key="attribute.amount")],
            aggregate="sum",
            time=IrQueryTime(relative_period=RelativePeriod.THIS_MONTH),
        ),
    )


def _trace_interpretation(exc: Exception | None, ir: IngestIR | QueryIR | None) -> tuple[StageTrace, FailureFrontierV2, list[str]]:
    stages = StageTrace()
    notes: list[str] = []
    if exc is not None:
        stages.provider_json = StageStatus.FAIL
        cause = getattr(exc, "__cause__", None)
        if isinstance(cause, LlmInvalidResponseError):
            return stages, FailureFrontierV2.PROVIDER, notes
        if isinstance(cause, LlmSchemaValidationError):
            stages.wire = StageStatus.FAIL
            return stages, FailureFrontierV2.WIRE, notes
        return stages, FailureFrontierV2.PROVIDER, notes
    if ir is None:
        stages.provider_json = StageStatus.FAIL
        return stages, FailureFrontierV2.PROVIDER, notes
    stages.provider_json = StageStatus.PASS
    stages.wire = StageStatus.PASS
    stages.canonical = StageStatus.PASS
    return stages, FailureFrontierV2.PASS, notes


def _trace_ingest(stages: StageTrace, result, *, started: bool) -> tuple[StageTrace, FailureFrontierV2, list[str]]:
    notes: list[str] = []
    if not started:
        return stages, FailureFrontierV2.CANONICAL, notes
    if result.status is IngestStatus.COMMITTED:
        stages.resolution = StageStatus.PASS
        stages.candidate = StageStatus.PASS
        stages.validation = StageStatus.PASS
        stages.completeness = StageStatus.PASS
        stages.materialization = StageStatus.PASS
        stages.commit = StageStatus.PASS
        return stages, FailureFrontierV2.PASS, notes
    issues = [i.code for i in result.issues]
    if "time.missing" in issues:
        stages.resolution = StageStatus.FAIL
        return stages, FailureFrontierV2.TEMPORAL_RESOLUTION, notes
    if any(c.startswith("entity.") or c.startswith("clarify.entity") for c in issues):
        stages.resolution = StageStatus.FAIL
        return stages, FailureFrontierV2.ENTITY_RESOLUTION, notes
    if result.assessment is not None:
        if not result.assessment.validation.valid:
            stages.validation = StageStatus.FAIL
            return stages, FailureFrontierV2.VALIDATION, notes
        if result.assessment.completeness.blocking:
            stages.completeness = StageStatus.FAIL
            return stages, FailureFrontierV2.COMPLETENESS, notes
    if result.status is IngestStatus.NEEDS_CLARIFICATION:
        stages.completeness = StageStatus.FAIL
        return stages, FailureFrontierV2.COMPLETENESS, notes
    stages.materialization = StageStatus.FAIL
    return stages, FailureFrontierV2.MATERIALIZATION, notes


class IngestPathEvaluator:
    def __init__(
        self,
        ontology: OntologyRegistry,
        work_dir: Path,
        *,
        interpreter: Any | None = None,
    ) -> None:
        self._ontology = ontology
        self._work_dir = work_dir
        self._interpreter = interpreter
        self._user = benchmark_user()
        self._clock = FixedClock(BENCHMARK_NOW)

    def _db(self, name: str) -> Path:
        self._work_dir.mkdir(parents=True, exist_ok=True)
        return fresh_db_path(self._work_dir, name)

    def _prepare_db(self, db_path: Path, seed_corolla_entity: bool) -> None:
        if seed_corolla_entity:
            with_seeded_corolla(db_path)

    def _ingest_service(self, db_path: Path, responses: dict[str, object]) -> IngestService:
        return IngestService(
            FakeInterpreter(responses),  # type: ignore[arg-type]
            self._ontology,
            lambda: open_sqlite_uow(db_path),
            self._clock,
        )

    def _ask_service(self, db_path: Path, responses: dict[str, object]) -> AskService:
        return AskService(
            FakeInterpreter(responses),  # type: ignore[arg-type]
            self._ontology,
            open_sqlite_read_store(db_path),
            self._clock,
        )

    def run_deterministic_temporal(self, case: IngestBenchmarkCase) -> RunOutcome:
        ir = deterministic_ir(case.case_id)
        assert ir is not None and case.temporal is not None
        db_path = self._db(f"{case.case_id}-det.db")
        self._prepare_db(db_path, case.seed_corolla)
        session = benchmark_session()
        result = self._ingest_service(db_path, {case.text: ir}).ingest(case.text, self._user, session)
        stages, frontier, _ = _trace_interpretation(None, ir)
        stages, frontier, _ = _trace_ingest(stages, result, started=True)
        temporal_fails = check_ingest_result(result, case.temporal)
        event = None
        if result.status is IngestStatus.COMMITTED and result.materialization:
            with open_sqlite_uow(db_path) as uow:
                event = uow.events.get(USER_ID, result.materialization.event_ids[0])
        if event and case.temporal:
            temporal_fails.extend(check_temporal_knowledge(event, case.temporal))
            forbidden = invented_time_in_event(event, benchmark_day=BENCHMARK_NOW.date())
        else:
            forbidden = []
        knowledge_ok = not temporal_fails and not forbidden
        return RunOutcome(
            case_id=case.case_id,
            run=1,
            text=case.text,
            deterministic=True,
            interpretation_success=True,
            knowledge_success=knowledge_ok,
            query_success=None,
            stages=stages,
            frontier=FailureFrontierV2.PASS if knowledge_ok else frontier,
            temporal_fails=temporal_fails,
            forbidden_time_hits=forbidden,
            ingest_status=result.status.value,
        )

    def run_live_temporal(self, case: IngestBenchmarkCase, *, run: int) -> RunOutcome:
        assert self._interpreter is not None and case.temporal is not None
        db_path = self._db(f"{case.case_id}-live-r{run}.db")
        self._prepare_db(db_path, case.seed_corolla)
        session = benchmark_session()
        ctx = InterpretationContext(user=self._user)
        ir = None
        exc = None
        try:
            ir = self._interpreter.interpret(case.text, ctx)
        except InterpretationError as e:
            exc = e
        stages, interp_frontier, _ = _trace_interpretation(exc, ir if isinstance(ir, IngestIR) else None)
        interp_ok = exc is None and isinstance(ir, IngestIR)
        ingest = IngestService(
            self._interpreter,
            self._ontology,
            lambda: open_sqlite_uow(db_path),
            self._clock,
        )
        ingest_result = ingest.ingest(case.text, self._user, session)
        stages, ingest_frontier, _ = _trace_ingest(stages, ingest_result, started=interp_ok)
        frontier = ingest_frontier if ingest_frontier is not FailureFrontierV2.PASS else interp_frontier
        temporal_fails: list[str] = []
        forbidden: list[str] = []
        if case.temporal:
            temporal_fails.extend(check_ingest_result(ingest_result, case.temporal))
        event = None
        if ingest_result.status is IngestStatus.COMMITTED and ingest_result.materialization:
            with open_sqlite_uow(db_path) as uow:
                event = uow.events.get(USER_ID, ingest_result.materialization.event_ids[0])
        if event and case.temporal:
            temporal_fails.extend(check_temporal_knowledge(event, case.temporal))
            forbidden = invented_time_in_event(event, benchmark_day=BENCHMARK_NOW.date())
        knowledge_ok = ingest_result.status is IngestStatus.COMMITTED and not temporal_fails and not forbidden
        if case.temporal and not case.temporal.committed:
            knowledge_ok = ingest_result.status is not IngestStatus.COMMITTED and not forbidden
        return RunOutcome(
            case_id=case.case_id,
            run=run,
            text=case.text,
            deterministic=False,
            interpretation_success=interp_ok,
            knowledge_success=knowledge_ok,
            query_success=None,
            stages=stages,
            frontier=FailureFrontierV2.PASS if knowledge_ok else frontier,
            temporal_fails=temporal_fails,
            forbidden_time_hits=forbidden,
            ingest_status=ingest_result.status.value,
            error_class=type(exc).__name__ if exc else None,
        )

    def _setup_query(self, db_path: Path, setup_key: str) -> SessionContext:
        session = benchmark_session()
        if setup_key == "qtp01_ingest":
            svc = self._ingest_service(db_path, {RAW_T1: ir_t1()})
            assert svc.ingest(RAW_T1, self._user, session).status is IngestStatus.COMMITTED
        elif setup_key == "qtp03_ingest":
            svc = self._ingest_service(
                db_path,
                {RAW_T5_OIL: ir_t5_oil(), RAW_T5_CLUTCH: ir_t5_clutch()},
            )
            assert svc.ingest(RAW_T5_OIL, self._user, session).status is IngestStatus.COMMITTED
            assert svc.ingest(RAW_T5_CLUTCH, self._user, session).status is IngestStatus.COMMITTED
        elif setup_key == "qtp04_seed":
            with open_sqlite_uow(db_path) as uow:
                entity = seed_corolla(uow)
                seed_oil_change_event(uow, entity_id=entity.id, day=dt.date(2026, 7, 10), amount="100")
                seed_oil_change_event(uow, entity_id=entity.id, day=dt.date(2026, 8, 20), amount="186.50")
                seed_oil_change_event(uow, entity_id=entity.id, partial=True, amount="50")
                uow.commit()
        elif setup_key == "qtp05_seed":
            with open_sqlite_uow(db_path) as uow:
                entity = seed_corolla(uow)
                seed_oil_change_event(uow, entity_id=entity.id, day=dt.date(2026, 3, 1))
                seed_oil_change_event(uow, entity_id=entity.id, day=dt.date(2026, 6, 15))
                seed_oil_change_event(uow, entity_id=entity.id, partial=True)
                uow.commit()
        return session

    def run_query_case(self, case: IngestBenchmarkCase) -> RunOutcome:
        assert case.query is not None and case.setup_key
        db_path = self._db(f"{case.case_id}-det.db")
        session = self._setup_query(db_path, case.setup_key)
        stages = StageTrace()
        stages.provider_json = StageStatus.PASS
        stages.wire = StageStatus.PASS
        stages.canonical = StageStatus.PASS
        stages.resolution = StageStatus.PASS
        stages.candidate = StageStatus.PASS
        stages.validation = StageStatus.PASS
        stages.completeness = StageStatus.PASS
        stages.materialization = StageStatus.PASS
        stages.commit = StageStatus.PASS
        stages.query = StageStatus.PASS

        if case.case_id == "QTP01":
            ask = self._ask_service(db_path, {RAW_T3: _query_ir_existential()})
            result = ask.ask(RAW_T3, self._user, session)
            fails = check_query_result(result, case.query)
        elif case.case_id == "QTP02":
            ask = self._ask_service(db_path, {RAW_T4: _query_ir_period()})
            result = ask.ask(RAW_T4, self._user, session)
            fails = check_query_result(result, case.query)
        elif case.case_id == "QTP03":
            ask = self._ask_service(db_path, {RAW_T5_QUERY: _query_ir_sum()})
            result = ask.ask(RAW_T5_QUERY, self._user, session)
            fails = check_query_result(result, case.query)
        elif case.case_id == "QTP04":
            with open_sqlite_uow(db_path) as uow:
                entities = uow.entities.all_for_user(USER_ID)
                entity_id = entities[0].id
            store = open_sqlite_read_store(db_path)
            engine = QueryEngine(store, self._ontology)
            spec = ResolvedQuerySpec(
                user_id=USER_ID,
                entity_ids=[entity_id],
                entity_association=EntityAssociation.SUBJECT,
                event_type_ids=[core_concept_id("event.vehicle_maintenance")],
                aggregate=AggregateKind.LATEST,
                fact_concept_ids=[core_concept_id("attribute.amount")],
                currency="BRL",
                time_range=TimeRange(
                    start=dt.datetime(2026, 1, 1, tzinfo=FORTALEZA),
                    end=dt.datetime(2026, 12, 31, tzinfo=FORTALEZA),
                ),
            )
            qr = engine.execute(spec)
            result = AskResult(status=AskStatus.ANSWERED, raw_text="latest", query_result=qr)
            fails = check_query_result(result, case.query)
        elif case.case_id == "QTP05":
            with open_sqlite_uow(db_path) as uow:
                entities = uow.entities.all_for_user(USER_ID)
                entity_id = entities[0].id
            store = open_sqlite_read_store(db_path)
            engine = QueryEngine(store, self._ontology)
            base = ResolvedQuerySpec(
                user_id=USER_ID,
                entity_ids=[entity_id],
                entity_association=EntityAssociation.SUBJECT,
                event_type_ids=[core_concept_id("event.vehicle_maintenance")],
                aggregate=AggregateKind.COUNT,
            )
            qr_all = engine.execute(base)
            if qr_all.aggregate is None or qr_all.aggregate.value != 3:
                fails = [f"count_no_period expected 3 got {getattr(qr_all.aggregate, 'value', None)}"]
            else:
                year_spec = base.model_copy(
                    update={
                        "time_range": TimeRange(
                            start=dt.datetime(2026, 1, 1, tzinfo=FORTALEZA),
                            end=dt.datetime(2027, 1, 1, tzinfo=FORTALEZA),
                        )
                    }
                )
                qr_year = engine.execute(year_spec)
                if qr_year.temporal_completeness is not TemporalCompleteness.PARTIAL:
                    fails = [f"year count expected PARTIAL got {qr_year.temporal_completeness}"]
                else:
                    fails = []
            result = AskResult(status=AskStatus.ANSWERED, raw_text="count", query_result=qr_all)
        else:
            fails = ["unknown query case"]

        query_ok = not fails
        if not query_ok:
            stages.query = StageStatus.FAIL
        return RunOutcome(
            case_id=case.case_id,
            run=1,
            text=case.text,
            deterministic=True,
            interpretation_success=True,
            knowledge_success=True,
            query_success=query_ok,
            stages=stages,
            frontier=FailureFrontierV2.PASS if query_ok else FailureFrontierV2.QUERY,
            query_fails=fails,
        )

    def run_dev_case_live(self, case_id: str, text: str, *, run: int) -> RunOutcome:
        assert self._interpreter is not None
        db_path = self._db(f"DEV-{case_id}-r{run}.db")
        session = benchmark_session()
        ctx = InterpretationContext(user=self._user)
        ir = None
        exc = None
        try:
            ir = self._interpreter.interpret(text, ctx)
        except InterpretationError as e:
            exc = e
        stages, frontier, _ = _trace_interpretation(exc, ir if isinstance(ir, IngestIR) else None)
        interp_ok = exc is None and isinstance(ir, IngestIR)
        ingest = IngestService(
            self._interpreter,
            self._ontology,
            lambda: open_sqlite_uow(db_path),
            self._clock,
        )
        ingest_result = ingest.ingest(text, self._user, session)
        stages, ingest_frontier, _ = _trace_ingest(stages, ingest_result, started=interp_ok)
        if ingest_frontier is not FailureFrontierV2.PASS:
            frontier = ingest_frontier
        knowledge_ok = ingest_result.status is IngestStatus.COMMITTED
        return RunOutcome(
            case_id=case_id,
            run=run,
            text=text,
            deterministic=False,
            interpretation_success=interp_ok,
            knowledge_success=knowledge_ok,
            query_success=None,
            stages=stages,
            frontier=FailureFrontierV2.PASS if knowledge_ok else frontier,
            ingest_status=ingest_result.status.value,
            error_class=type(exc).__name__ if exc else None,
        )


def aggregate_runs(runs: list[RunOutcome]) -> dict[str, Any]:
    total = len(runs)
    interp = sum(1 for r in runs if r.interpretation_success)
    know = sum(1 for r in runs if r.knowledge_success)
    query = [r for r in runs if r.query_success is not None]
    query_ok = sum(1 for r in query if r.query_success)
    return {
        "total_runs": total,
        "interpretation_success_rate": round(interp / total, 4) if total else 0,
        "knowledge_success_rate": round(know / total, 4) if total else 0,
        "query_success_rate": round(query_ok / len(query), 4) if query else None,
        "stability": stability_label(know, total) if total else "0/0",
        "pass_count": know,
    }
