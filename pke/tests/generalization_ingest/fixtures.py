"""Fixtures determinísticas para benchmark ingest-path."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from pke.application import FixedClock, SessionContext
from pke.domain import (
    AnchorKind,
    Confidence,
    Entity,
    Event,
    EventStatus,
    Fact,
    Money,
    OccurrenceStatus,
    Qualifier,
    RawInput,
    RelationToReference,
    Source,
    SourceKind,
    TemporalGranularity,
    TemporalKnowledge,
    TemporalKind,
    TemporalUnknownReason,
    TimePrecision,
    TimeValue,
    UserContext,
    new_ulid,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist import open_sqlite_uow
from pke.resolution import PersonalContext

FORTALEZA = ZoneInfo("America/Fortaleza")
BENCHMARK_NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)
USER_ID = "bench-u1"


def benchmark_user() -> UserContext:
    return UserContext(user_id=USER_ID, timezone="America/Fortaleza", now=BENCHMARK_NOW)


def benchmark_session() -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=USER_ID))


def benchmark_clock() -> FixedClock:
    return FixedClock(BENCHMARK_NOW)


def fresh_db_path(root: Path, name: str) -> Path:
    path = root / name
    if path.exists():
        path.unlink()
    return path


def seed_corolla(uow, user_id: str = USER_ID) -> Entity:
    entity = Entity(
        id=new_ulid(),
        user_id=user_id,
        type_id=core_concept_id("entity.automobile"),
        canonical_name="Corolla",
        created_at=BENCHMARK_NOW,
    )
    uow.entities.add(entity)
    return entity


def _raw(user_id: str = USER_ID, text: str = "seed") -> RawInput:
    return RawInput(
        id=new_ulid(),
        user_id=user_id,
        text=text,
        created_at=BENCHMARK_NOW,
    )


def _exact_day(day: dt.date, text: str) -> TimeValue:
    return TimeValue(
        original_text=text,
        date=day,
        precision=TimePrecision.DAY,
        timezone="America/Fortaleza",
        reference_at=BENCHMARK_NOW,
        reference_timezone="America/Fortaleza",
        resolution_rule="absolute.date",
    )


def seed_oil_change_event(
    uow,
    *,
    entity_id: str,
    day: dt.date | None = None,
    partial: bool = False,
    amount: str | None = None,
    action_key: str = "action.oil_change",
    user_id: str = USER_ID,
) -> Event:
    raw = _raw(user_id)
    uow.raw_inputs.add(raw)
    if partial:
        temporal = TemporalKnowledge(
            kind=TemporalKind.PARTIAL,
            original_text="",
            relation_to_reference=RelationToReference.BEFORE,
            occurrence_status=OccurrenceStatus.HAPPENED,
            unknown_reason=TemporalUnknownReason.NOT_PROVIDED,
        )
    else:
        assert day is not None
        temporal = TemporalKnowledge.from_calendar(_exact_day(day, str(day)))
    event = Event(
        id=new_ulid(),
        user_id=user_id,
        type_id=core_concept_id("event.vehicle_maintenance"),
        action_id=core_concept_id(action_key),
        subject_id=entity_id,
        actor_id=entity_id,
        temporal=temporal,
        status=EventStatus.COMPLETED,
        domain_ids=[core_concept_id("domain.vehicle"), core_concept_id("domain.finance")],
        raw_input_id=raw.id,
        created_at=BENCHMARK_NOW,
    )
    uow.events.add(event)
    if amount is not None:
        source = Source(
            id=new_ulid(),
            user_id=user_id,
            kind=SourceKind.USER_STATEMENT,
            raw_input_id=raw.id,
        )
        uow.sources.add(source)
        uow.facts.add(
            Fact(
                id=new_ulid(),
                user_id=user_id,
                about_kind=AnchorKind.EVENT,
                about_id=event.id,
                concept_id=core_concept_id("attribute.amount"),
                key="attribute.amount",
                value=Money(amount=Decimal(amount), currency="BRL"),
                qualifier=Qualifier.EXACT,
                source=source,
                confidence=Confidence(score=1.0, qualifier=Qualifier.EXACT),
                created_at=BENCHMARK_NOW,
            )
        )
    return event


def seed_month_partial_oil_change(
    uow,
    *,
    entity_id: str,
    month: int,
    year: int = 2026,
    user_id: str = USER_ID,
) -> Event:
    """Agosto sem dia — partial interval/month."""
    raw = _raw(user_id)
    uow.raw_inputs.add(raw)
    start = dt.date(year, month, 1)
    if month == 12:
        end = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        end = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    temporal = TemporalKnowledge(
        kind=TemporalKind.PARTIAL,
        original_text=f"{month:02d}/{year}",
        interval_start=start,
        interval_end=end,
        granularity=TemporalGranularity.MONTH,
        relation_to_reference=RelationToReference.BEFORE,
        occurrence_status=OccurrenceStatus.HAPPENED,
        unknown_reason=TemporalUnknownReason.NOT_PROVIDED,
    )
    event = Event(
        id=new_ulid(),
        user_id=user_id,
        type_id=core_concept_id("event.vehicle_maintenance"),
        action_id=core_concept_id("action.oil_change"),
        subject_id=entity_id,
        actor_id=entity_id,
        temporal=temporal,
        status=EventStatus.COMPLETED,
        domain_ids=[core_concept_id("domain.vehicle")],
        raw_input_id=raw.id,
        created_at=BENCHMARK_NOW,
    )
    uow.events.add(event)
    return event


def with_seeded_corolla(db_path: Path, ontology: OntologyRegistry | None = None) -> Entity:
    with open_sqlite_uow(db_path) as uow:
        entity = seed_corolla(uow)
        uow.commit()
        return entity


def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()
