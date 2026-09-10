"""Testes de integridade temporal — recorded_at ≠ Event.time."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pke.application import FixedClock, IngestService, IngestStatus, SessionContext
from pke.domain import ConceptRef, EventStatus, UserContext
from pke.interpretation import FakeInterpreter, IngestIR, IngestIntent, IrEvent, IrFact, IrTime
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.resolution import PersonalContext
from tests.integration.test_ingest import RAW_D2, _corolla, ir_d2, ir_d2_with_vehicle

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "pke.db"


@pytest.fixture
def user() -> UserContext:
    return UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)


def _service(db_path: Path, ontology: OntologyRegistry, responses: dict[str, object]) -> IngestService:
    return IngestService(
        FakeInterpreter(responses),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db_path),
        FixedClock(NOW),
    )


def test_missing_event_time_does_not_default_to_now(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    result = _service(db_path, ontology, {RAW_D2: ir_d2_with_vehicle()}).ingest(
        RAW_D2,
        user,
        SessionContext(personal=PersonalContext(user_id="u1")),
    )
    assert result.status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    assert len(graph.events) == 1
    event = graph.events[0]
    assert not event.temporal.has_calendar_anchor()
    assert event.created_at is not None


def test_recorded_at_is_distinct_from_event_time(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    raw = "Troquei o óleo do Corolla no dia 15 de agosto por 320 reais."
    ir = IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=raw,
        domains=[ConceptRef(key="domain.vehicle")],
        entities_mentioned=[_corolla()],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.oil_change"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text="15 de agosto", date=dt.date(2026, 8, 15)),
            facts=[
                IrFact(
                    attribute=ConceptRef(key="attribute.amount"),
                    value={"amount": "320", "currency": "BRL"},
                )
            ],
        ),
    )
    session = SessionContext(personal=PersonalContext(user_id="u1"))
    result = _service(db_path, ontology, {raw: ir}).ingest(raw, user, session)
    assert result.status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    assert len(graph.events) == 1
    event = graph.events[0]
    assert event.time.date == dt.date(2026, 8, 15)
    assert event.created_at is not None
    assert event.created_at.date() == dt.date(2026, 9, 1)
    assert event.created_at.date() != event.time.date
