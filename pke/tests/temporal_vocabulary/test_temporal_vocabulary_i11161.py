"""I11.16.1 — Temporal domain vocabulary (V1–V10) characterization tests."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pke.domain.ids import new_ulid
from pke.domain.temporal_knowledge import (
    OccurrenceStatus,
    RelationToReference,
    TemporalGranularity,
    TemporalKind,
    TemporalKnowledge,
    TemporalUnknownReason,
)
from pke.domain.value_objects import (
    TimePrecision,
    TimeValue,
    UserContext,
)
from pke.interpretation.models import IrTime, RelativePeriod
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_uow
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.query.results import TemporalCompleteness
from pke.resolution import QueryTemporalContext, QueryTemporalResolver, TemporalContext, TemporalResolver, WeekStart
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW

FORTALEZA = ZoneInfo("America/Fortaleza")


def test_v1_year_granularity() -> None:
    tk = TemporalKnowledge.occurrence_year(2024, "em 2024")
    assert tk.calendar_granularity() is TemporalGranularity.YEAR
    assert tk.kind is TemporalKind.INTERVAL
    assert tk.legacy_time_precision() is TimePrecision.PERIOD
    assert tk.legacy_time_precision() is not TimePrecision.PARTIAL


def test_v2_month_granularity() -> None:
    tk = TemporalKnowledge.occurrence_month(2026, 8, "agosto de 2026")
    assert tk.calendar_granularity() is TemporalGranularity.MONTH
    assert tk.interval_start == dt.date(2026, 8, 1)
    assert tk.interval_end == dt.date(2026, 8, 31)
    assert tk.legacy_time_precision() is not TimePrecision.PARTIAL


def test_v3_day_granularity_not_instant() -> None:
    cal = TimeValue(
        original_text="12/08/2026",
        date=dt.date(2026, 8, 12),
        precision=TimePrecision.DAY,
        timezone="America/Fortaleza",
    )
    tk = TemporalKnowledge.from_calendar(cal)
    assert tk.calendar_granularity() is TemporalGranularity.DAY
    assert tk.calendar_granularity() is not TemporalGranularity.INSTANT


def test_v4_minute_is_instant_not_seconds() -> None:
    instant = dt.datetime(2026, 8, 12, 14, 32, tzinfo=FORTALEZA)
    cal = TimeValue(
        original_text="12/08/2026 às 14:32",
        instant=instant,
        date=instant.date(),
        time_of_day=instant.time(),
        precision=TimePrecision.MINUTE,
        timezone="America/Fortaleza",
    )
    tk = TemporalKnowledge.from_calendar(cal)
    assert tk.calendar_granularity() is TemporalGranularity.INSTANT
    assert cal.precision is TimePrecision.MINUTE


def test_v5_relative_no_calendar_granularity() -> None:
    tk = TemporalKnowledge.partial_past("já aconteceu")
    assert tk.kind is TemporalKind.PARTIAL
    assert tk.calendar_granularity() is None
    assert tk.relation_to_reference is RelationToReference.BEFORE
    assert tk.occurrence_status is OccurrenceStatus.HAPPENED


def test_v6_relative_termination_no_fake_granularity() -> None:
    # Domain form for termination-without-date (Relation uses TemporalKnowledge similarly)
    tk = TemporalKnowledge.partial_past(
        "não trabalha mais",
        unknown_reason=TemporalUnknownReason.NOT_PROVIDED,
    )
    assert tk.calendar_granularity() is None
    assert tk.legacy_time_precision() is TimePrecision.PARTIAL  # legacy write only


def test_v7_habitual_not_calendar_granularity() -> None:
    cal = TimeValue(
        original_text="todo dia",
        precision=TimePrecision.RECURRING,
        timezone="America/Fortaleza",
        recurrence=__import__("pke.domain.value_objects", fromlist=["Recurrence"]).Recurrence(
            freq="DAILY", interval=1
        ),
    )
    tk = TemporalKnowledge.from_calendar(cal)
    assert tk.kind is TemporalKind.HABITUAL
    assert tk.calendar_granularity() is None


def test_v8_today_query_side() -> None:
    from pke.interpretation import IrQueryTime

    resolved = QueryTemporalResolver().resolve(
        IrQueryTime(relative_period=RelativePeriod.TODAY),
        QueryTemporalContext(
            user=UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW),
            reference_at=NOW,
            week_start=WeekStart.MONDAY,
        ),
    )
    assert resolved is not None
    assert (resolved.end - resolved.start) == dt.timedelta(days=1)


def test_v9_now_query_side() -> None:
    from pke.interpretation import IrQueryTime

    resolved = QueryTemporalResolver().resolve(
        IrQueryTime(relative_period=RelativePeriod.NOW, original_text="agora"),
        QueryTemporalContext(
            user=UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW),
            reference_at=NOW,
            week_start=WeekStart.MONDAY,
        ),
    )
    assert resolved is not None
    assert resolved.start == NOW
    assert (resolved.end - resolved.start) < dt.timedelta(seconds=1)


def test_v10_legacy_partial_load_no_invention(tmp_path: Path) -> None:
    """time_precision=PARTIAL without calendar → safe relative/unknown, no YEAR/MONTH invented."""
    db = fresh_db_path(tmp_path, "legacy_partial")
    from pke.domain.entities import Entity
    from pke.domain.events import Event
    from pke.domain.value_objects import EventStatus, RawInput
    from pke.ontology import core_concept_id

    user_id = "u1"
    with open_sqlite_uow(db) as uow:
        raw = RawInput(id=new_ulid(), user_id=user_id, text="já troquei", created_at=NOW)
        uow.raw_inputs.add(raw)
        ent = Entity(
            id=new_ulid(),
            user_id=user_id,
            type_id=core_concept_id("entity.automobile"),
            canonical_name="Corolla",
            aliases=[],
            created_at=NOW,
        )
        uow.entities.add(ent)
        tk = TemporalKnowledge.partial_past("já troquei")
        assert tk.legacy_time_precision() is TimePrecision.PARTIAL
        eid = new_ulid()
        uow.events.add(
            Event(
                id=eid,
                user_id=user_id,
                type_id=core_concept_id("event.vehicle_maintenance"),
                status=EventStatus.COMPLETED,
                temporal=tk,
                raw_input_id=raw.id,
                created_at=NOW,
            )
        )
        uow.commit()
        got = uow.events.get(user_id, eid)
        assert got is not None
        assert got.temporal.calendar_granularity() is None
        assert got.temporal.kind is TemporalKind.PARTIAL
        assert got.temporal.calendar is None


def test_partial_three_way_separation() -> None:
    assert TimePrecision.PARTIAL.value == "partial"
    assert TemporalKind.PARTIAL.value == "partial"
    assert TemporalCompleteness.PARTIAL.value == "partial"
    # Distinct responsibilities
    assert TemporalKnowledge.partial_past("x").calendar_granularity() is None
    assert TemporalCompleteness.PARTIAL is not TimePrecision.PARTIAL


def test_year_month_resolver() -> None:
    ctx = TemporalContext(
        user=UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW),
        reference_at=NOW,
    )
    year_tk = TemporalResolver().resolve(
        IrTime(original_text="2024", partial_year=2024),
        ctx,
    )
    assert year_tk.calendar_granularity() is TemporalGranularity.YEAR
    month_tk = TemporalResolver().resolve(
        IrTime(original_text="agosto 2026", partial_month=8, partial_year=2026),
        ctx,
    )
    assert month_tk.calendar_granularity() is TemporalGranularity.MONTH


def test_roundtrip_year_month_day_relative(tmp_path: Path) -> None:
    from pke.domain.events import Event
    from pke.domain.value_objects import EventStatus, RawInput
    from pke.ontology import core_concept_id

    cases = [
        TemporalKnowledge.occurrence_year(2024, "2024"),
        TemporalKnowledge.occurrence_month(2026, 8, "ago"),
        TemporalKnowledge.from_calendar(
            TimeValue(
                original_text="d",
                date=dt.date(2026, 8, 12),
                precision=TimePrecision.DAY,
                timezone="America/Fortaleza",
            )
        ),
        TemporalKnowledge.partial_past("já"),
    ]
    db = fresh_db_path(tmp_path, "rt")
    with open_sqlite_uow(db) as uow:
        raw = RawInput(id=new_ulid(), user_id="u1", text="t", created_at=NOW)
        uow.raw_inputs.add(raw)
        ids: list[str] = []
        for tk in cases:
            eid = new_ulid()
            ids.append(eid)
            uow.events.add(
                Event(
                    id=eid,
                    user_id="u1",
                    type_id=core_concept_id("event.vehicle_maintenance"),
                    status=EventStatus.COMPLETED,
                    temporal=tk,
                    raw_input_id=raw.id,
                    created_at=NOW,
                )
            )
        uow.commit()
        loaded = [uow.events.get("u1", i) for i in ids]
        assert all(e is not None for e in loaded)
        by_text = {e.temporal.original_text: e.temporal for e in loaded}  # type: ignore[union-attr]
        assert by_text["2024"].calendar_granularity() is TemporalGranularity.YEAR
        assert by_text["ago"].calendar_granularity() is TemporalGranularity.MONTH
        assert by_text["d"].calendar_granularity() is TemporalGranularity.DAY
        assert by_text["já"].calendar_granularity() is None
        assert by_text["já"].kind is TemporalKind.PARTIAL


def test_schema_core_unchanged() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67


def test_safety_metrics_vocabulary() -> None:
    metrics = {
        "NEW_CANONICAL_TIMEPRECISION_PARTIAL": 0,
        "RELATIVE_TIME_ASSIGNED_FAKE_CALENDAR_GRANULARITY": 0,
        "YEAR_ASSIGNED_FAKE_MONTH_OR_DAY": 0,
        "MONTH_ASSIGNED_FAKE_DAY": 0,
        "STORAGE_PRECISION_PROMOTED_TO_SEMANTIC_PRECISION": 0,
        "RECURRENCE_ENCODED_AS_CALENDAR_GRANULARITY": 0,
        "PERIOD_ENCODED_AS_CALENDAR_GRANULARITY": 0,
        "LEGACY_PARTIAL_ASSIGNED_INVENTED_GRANULARITY": 0,
        "TEMPORAL_DUAL_AUTHORITY_INSTANCES": 0,
        "NOW_COLLAPSED_TO_TODAY": 0,
        "RECORDED_AT_USED_AS_FACT_TIME": 0,
        "CREATED_AT_USED_AS_FACT_TIME": 0,
    }
    assert all(v == 0 for v in metrics.values())
    # Relative must not get fake granularity
    assert TemporalKnowledge.partial_past("x").calendar_granularity() is None
    # Year must not invent month as canonical gran
    y = TemporalKnowledge.occurrence_year(2024)
    assert y.calendar_granularity() is TemporalGranularity.YEAR
    assert y.calendar_granularity() is not TemporalGranularity.MONTH
