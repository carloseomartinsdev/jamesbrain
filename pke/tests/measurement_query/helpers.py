"""Helpers for Measurement query tests — seed observations without mutating via Ask."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from pke.domain.entities import Entity
from pke.domain.ids import new_ulid
from pke.domain.measurements import Measurement
from pke.domain.temporal_knowledge import TemporalKnowledge, TemporalUnknownReason
from pke.domain.value_objects import (
    Confidence,
    RawInput,
    Source,
    SourceKind,
    TimePrecision,
    TimeValue,
)
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.query.engine import QueryEngine
from pke.query.spec import (
    EntityAssociation,
    MeasurementQueryMode,
    MeasurementValueFilter,
    ResolvedQuerySpec,
    TimeRange,
)
from tests.generalization_ingest.fixtures import benchmark_user
from tests.integration.test_ingest import NOW

FORTALEZA = ZoneInfo("America/Fortaleza")


def _calendar_at(instant: dt.datetime) -> TemporalKnowledge:
    return TemporalKnowledge.from_calendar(
        TimeValue(
            original_text=instant.isoformat(),
            instant=instant,
            timezone="America/Fortaleza",
            precision=TimePrecision.MINUTE,
        )
    )


def seed_entity(
    db: Path,
    *,
    name: str = "bateria",
    type_id: str = "entity.thing",
) -> tuple[str, str]:
    """Return (user_id, entity_id)."""
    user = benchmark_user()
    with open_sqlite_uow(db) as uow:
        raw = RawInput(id=new_ulid(), user_id=user.user_id, text="seed", created_at=NOW)
        uow.raw_inputs.add(raw)
        src = Source(
            id=new_ulid(),
            user_id=user.user_id,
            kind=SourceKind.USER_STATEMENT,
            raw_input_id=raw.id,
        )
        uow.sources.add(src)
        ent = Entity(
            id=new_ulid(),
            user_id=user.user_id,
            type_id=type_id,
            canonical_name=name,
            aliases=[],
            created_at=NOW,
        )
        uow.entities.add(ent)
        uow.commit()
        return user.user_id, ent.id


def add_measurement(
    db: Path,
    *,
    user_id: str,
    entity_id: str,
    dimension_key: str,
    numeric_value: Decimal | str | int,
    unit: str | None = None,
    currency_code: str | None = None,
    observed_at: dt.datetime | None = None,
    temporal: TemporalKnowledge | None = None,
    context_entity_id: str | None = None,
    created_at: dt.datetime | None = None,
) -> str:
    """Persist one Measurement; returns measurement id. Does not use Ask."""
    with open_sqlite_uow(db) as uow:
        raw = RawInput(
            id=new_ulid(),
            user_id=user_id,
            text=f"{dimension_key}={numeric_value}",
            created_at=created_at or NOW,
        )
        uow.raw_inputs.add(raw)
        src = Source(
            id=new_ulid(),
            user_id=user_id,
            kind=SourceKind.USER_STATEMENT,
            raw_input_id=raw.id,
        )
        uow.sources.add(src)
        if temporal is None:
            if observed_at is not None:
                temporal = _calendar_at(observed_at)
            else:
                temporal = TemporalKnowledge.unknown(
                    "", unknown_reason=TemporalUnknownReason.NOT_PROVIDED
                )
        mid = new_ulid()
        uow.measurements.add(
            Measurement(
                id=mid,
                user_id=user_id,
                entity_id=entity_id,
                context_entity_id=context_entity_id,
                dimension_key=dimension_key,
                numeric_value=Decimal(str(numeric_value)),
                unit=unit,
                currency_code=currency_code,
                temporal=temporal,
                observed_at=observed_at,
                source=src,
                raw_input_id=raw.id,
                confidence=Confidence(score=1.0),
                created_at=created_at or NOW,
            )
        )
        uow.commit()
        return mid


def run_measurement_query(
    db: Path,
    *,
    user_id: str,
    entity_ids: list[str],
    dimension_key: str,
    mode: MeasurementQueryMode,
    time_range: TimeRange | None = None,
    value_filter: MeasurementValueFilter | None = None,
    context_entity_ids: list[str] | None = None,
):
    engine = QueryEngine(open_sqlite_read_store(db), OntologyRegistry.with_core_seeds())
    return engine.execute(
        ResolvedQuerySpec(
            user_id=user_id,
            entity_ids=entity_ids,
            entity_association=EntityAssociation.SUBJECT if entity_ids else None,
            measurement_dimension_key=dimension_key,
            measurement_query_mode=mode,
            measurement_value_filter=value_filter,
            context_entity_ids=context_entity_ids or [],
            time_range=time_range,
        )
    )


def yesterday_range(now: dt.datetime = NOW) -> TimeRange:
    day = now.astimezone(FORTALEZA).date() - dt.timedelta(days=1)
    start = dt.datetime.combine(day, dt.time.min, tzinfo=FORTALEZA)
    end = start + dt.timedelta(days=1)
    return TimeRange(start=start, end=end)


def today_range(now: dt.datetime = NOW) -> TimeRange:
    day = now.astimezone(FORTALEZA).date()
    start = dt.datetime.combine(day, dt.time.min, tzinfo=FORTALEZA)
    end = start + dt.timedelta(days=1)
    return TimeRange(start=start, end=end)


def now_range(now: dt.datetime = NOW) -> TimeRange:
    """Exact NOW membership window — NOT the calendar day."""
    return TimeRange(start=now, end=now + dt.timedelta(microseconds=1))


def august_2026_range() -> TimeRange:
    return TimeRange(
        start=dt.datetime(2026, 8, 1, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
    )
