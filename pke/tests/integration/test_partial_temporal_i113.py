"""Testes I11.3 — Partial Temporal Knowledge."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pke.application import (
    AskService,
    AskStatus,
    FixedClock,
    IngestService,
    IngestStatus,
    SessionContext,
)
from pke.domain import (
    ConceptRef,
    EventStatus,
    OccurrenceStatus,
    RelationToReference,
    TemporalKnowledge,
    TemporalUnknownReason,
    UserContext,
)
from pke.interpretation import (
    EntityMention,
    FakeInterpreter,
    IngestIntent,
    IngestIR,
    IrEvent,
    IrFact,
    IrQueryTime,
    IrTime,
    QueryIR,
    QuerySpec,
    RelativePeriod,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist import open_sqlite_uow
from pke.query.results import TemporalCompleteness
from pke.query.spec import AggregateKind
from pke.resolution import PersonalContext
from pke.temporal.membership import TemporalMembership, range_membership
from pke.query.spec import TimeRange
from tests.integration.test_ask import _ask, _ingest, _query_ir
from tests.integration.test_ingest import NOW, _corolla, _service

FORTALEZA = ZoneInfo("America/Fortaleza")

RAW_T1 = "Troquei a embreagem do Corolla."
RAW_T2 = "Fui ao cardiologista, mas não lembro quando."
RAW_T5_OIL = "Troquei o óleo hoje por 320 reais."
RAW_T5_CLUTCH = "Troquei a embreagem por 1800 reais."
RAW_T5_QUERY = "Quanto gastei com o Corolla este mês?"
RAW_T3 = "Já troquei a embreagem do Corolla?"
RAW_T4 = "Troquei a embreagem este mês?"


def ir_t1() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=RAW_T1,
        domains=[ConceptRef(key="domain.vehicle")],
        entities_mentioned=[_corolla()],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.replace"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text=""),
            facts=[],
        ),
    )


def ir_t2() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=RAW_T2,
        domains=[ConceptRef(key="domain.health")],
        event=IrEvent(
            type=ConceptRef(key="event.appointment"),
            action=ConceptRef(key="action.attend"),
            status=EventStatus.COMPLETED,
            time=IrTime(
                original_text="não lembro quando",
                unknown_reason=TemporalUnknownReason.FORGOTTEN,
                relation_to_reference=RelationToReference.BEFORE,
                occurrence_status=OccurrenceStatus.HAPPENED,
            ),
            facts=[],
        ),
    )


def ir_t5_oil() -> IngestIR:
    from pke.domain import Qualifier, RelativeDay

    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=RAW_T5_OIL,
        domains=[ConceptRef(key="domain.vehicle"), ConceptRef(key="domain.finance")],
        entities_mentioned=[_corolla()],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.oil_change"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text="hoje", relative_day=RelativeDay.TODAY),
            facts=[
                IrFact(
                    attribute=ConceptRef(key="attribute.amount"),
                    value={"amount": "320", "currency": "BRL"},
                    qualifier=Qualifier.EXACT,
                )
            ],
        ),
    )


def ir_t5_clutch() -> IngestIR:
    from pke.domain import Qualifier

    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=RAW_T5_CLUTCH,
        domains=[ConceptRef(key="domain.vehicle"), ConceptRef(key="domain.finance")],
        entities_mentioned=[_corolla()],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.replace"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text=""),
            facts=[
                IrFact(
                    attribute=ConceptRef(key="attribute.amount"),
                    value={"amount": "1800", "currency": "BRL"},
                    qualifier=Qualifier.EXACT,
                )
            ],
        ),
    )


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "partial.db"


@pytest.fixture
def user() -> UserContext:
    return UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)


def test_t1_commits_partial_past(db_path: Path, ontology: OntologyRegistry, user: UserContext) -> None:
    result = _service(db_path, ontology, {RAW_T1: ir_t1()}).ingest(
        RAW_T1, user, SessionContext(personal=PersonalContext(user_id="u1"))
    )
    assert result.status is IngestStatus.COMMITTED
    assert result.clarification is None or result.clarification.blocking is False
    with open_sqlite_uow(db_path) as uow:
        event = uow.events.get("u1", result.materialization.event_ids[0])  # type: ignore[union-attr]
        assert event is not None
        assert event.temporal.kind.value == "partial"
        assert event.temporal.relation_to_reference is RelationToReference.BEFORE
        assert not event.temporal.has_calendar_anchor()


def test_t2_forgotten_reason(db_path: Path, ontology: OntologyRegistry, user: UserContext) -> None:
    result = _service(db_path, ontology, {RAW_T2: ir_t2()}).ingest(
        RAW_T2, user, SessionContext(personal=PersonalContext(user_id="u1"))
    )
    assert result.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db_path) as uow:
        event = uow.events.get("u1", result.materialization.event_ids[0])  # type: ignore[union-attr]
        assert event is not None
        assert event.temporal.unknown_reason is TemporalUnknownReason.FORGOTTEN


def test_t3_existential_count(db_path: Path, ontology: OntologyRegistry, user: UserContext) -> None:
    session = SessionContext(personal=PersonalContext(user_id="u1"))
    _service(db_path, ontology, {RAW_T1: ir_t1()}).ingest(RAW_T1, user, session)
    query = QueryIR(
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
    result = _ask(db_path, ontology, {RAW_T3: query}).ask(RAW_T3, user, session)
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.aggregate is not None
    assert result.query_result.aggregate.value == 1


def test_t4_period_query_unknown(db_path: Path, ontology: OntologyRegistry, user: UserContext) -> None:
    session = SessionContext(personal=PersonalContext(user_id="u1"))
    _service(db_path, ontology, {RAW_T1: ir_t1()}).ingest(RAW_T1, user, session)
    query = QueryIR(
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
    result = _ask(db_path, ontology, {RAW_T4: query}).ask(RAW_T4, user, session)
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.aggregate is not None
    assert result.query_result.aggregate.value == 0
    assert result.query_result.temporal_completeness is TemporalCompleteness.PARTIAL
    assert result.query_result.temporal_membership_unknown is True


def test_t5_partial_sum(db_path: Path, ontology: OntologyRegistry, user: UserContext) -> None:
    session = SessionContext(personal=PersonalContext(user_id="u1"))
    ingest = _ingest(
        db_path,
        ontology,
        {RAW_T5_OIL: ir_t5_oil(), RAW_T5_CLUTCH: ir_t5_clutch()},
    )
    assert ingest.ingest(RAW_T5_OIL, user, session).status is IngestStatus.COMMITTED
    assert ingest.ingest(RAW_T5_CLUTCH, user, session).status is IngestStatus.COMMITTED
    result = _ask(db_path, ontology, {RAW_T5_QUERY: _query_ir(RAW_T5_QUERY)}).ask(
        RAW_T5_QUERY, user, session
    )
    assert result.status is AskStatus.ANSWERED
    agg = result.query_result.aggregate  # type: ignore[union-attr]
    assert agg is not None
    assert agg.value == Decimal("320")
    assert agg.temporal_completeness is TemporalCompleteness.PARTIAL
    assert len(agg.unknown_temporal_contributors) == 1
    assert agg.unknown_temporal_contributors[0].value == Decimal("1800")


def test_range_membership_unknown_for_partial_past() -> None:
    partial = TemporalKnowledge.partial_past("embreagem")
    tr = TimeRange(
        start=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 10, 1, tzinfo=FORTALEZA),
    )
    assert range_membership(partial, tr) is TemporalMembership.UNKNOWN
