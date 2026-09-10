from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pke.domain import (
    AnchorKind,
    Confidence,
    Entity,
    Event,
    EventStatus,
    Fact,
    Money,
    Qualifier,
    RawInput,
    Recurrence,
    Source,
    SourceKind,
    TimePrecision,
    TimeValue,
    new_ulid,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.query import (
    AggregateKind,
    EntityAssociation,
    FactVersionPolicy,
    HierarchyMode,
    MultiCurrencyAggregateError,
    QueryEngine,
    QueryIsolationError,
    QuerySpecError,
    ResolvedQuerySpec,
    TimeRange,
)

UTC = dt.UTC
FORTALEZA = ZoneInfo("America/Fortaleza")
SEP = TimeRange(
    start=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
    end=dt.datetime(2026, 10, 1, tzinfo=FORTALEZA),
)


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "query.db"


def _raw(user: str = "u1") -> RawInput:
    return RawInput(
        id=new_ulid(),
        user_id=user,
        text="seed",
        created_at=dt.datetime(2026, 9, 1, 12, tzinfo=UTC),
    )


def _car(user: str = "u1", name: str = "Corolla") -> Entity:
    return Entity(
        id=new_ulid(),
        user_id=user,
        type_id=core_concept_id("entity.automobile"),
        canonical_name=name,
        created_at=dt.datetime(2026, 9, 1, tzinfo=UTC),
    )


def _time(day: dt.date, *, created_shift: int = 0) -> TimeValue:
    return TimeValue(
        original_text=str(day),
        date=day,
        precision=TimePrecision.DAY,
        timezone="America/Fortaleza",
        reference_at=dt.datetime(2026, 9, 1, 15, tzinfo=FORTALEZA),
        reference_timezone="America/Fortaleza",
        resolution_rule="absolute.date",
    )


def _event(
    user: str,
    raw_id: str,
    subject_id: str,
    day: dt.date,
    *,
    type_key: str = "event.vehicle_maintenance",
    created_at: dt.datetime | None = None,
    status: EventStatus = EventStatus.COMPLETED,
) -> Event:
    return Event(
        id=new_ulid(),
        user_id=user,
        type_id=core_concept_id(type_key),
        action_id=core_concept_id("action.oil_change")
        if type_key == "event.vehicle_maintenance"
        else None,
        subject_id=subject_id,
        actor_id=subject_id,
        time=_time(day),
        status=status,
        domain_ids=[core_concept_id("domain.vehicle"), core_concept_id("domain.finance")],
        raw_input_id=raw_id,
        created_at=created_at or dt.datetime(2026, 9, 1, 18, tzinfo=UTC),
    )


def _amount(
    user: str,
    event_id: str,
    raw_id: str,
    amount: str,
    *,
    currency: str = "BRL",
    supersedes_id: str | None = None,
    created_at: dt.datetime | None = None,
) -> Fact:
    return Fact(
        id=new_ulid(),
        user_id=user,
        about_kind=AnchorKind.EVENT,
        about_id=event_id,
        concept_id=core_concept_id("attribute.amount"),
        key="attribute.amount",
        value=Money(amount=Decimal(amount), currency=currency),
        source=Source(
            user_id=user,
            kind=SourceKind.USER_STATEMENT,
            raw_input_id=raw_id,
            id=new_ulid(),
        ),
        confidence=Confidence(score=1.0, qualifier=Qualifier.EXACT),
        supersedes_id=supersedes_id,
        created_at=created_at or dt.datetime(2026, 9, 1, 18, tzinfo=UTC),
    )


class Seed:
    def __init__(self) -> None:
        self.corolla: str
        self.sep_a: str
        self.sep_b: str
        self.aug: str
        self.usd: str
        self.bill: str
        self.old_fact: str
        self.new_fact: str
        self.sep_a_fact: str
        self.civic: str
        self.other_event: str


def _seed(db_path: Path) -> Seed:
    seed = Seed()
    with open_sqlite_uow(db_path) as uow:
        raw = _raw()
        car = _car()
        uow.raw_inputs.add(raw)
        uow.entities.add(car)
        seed.corolla = car.id
        sep_a = _event("u1", raw.id, car.id, dt.date(2026, 9, 5))
        sep_b = _event(
            "u1",
            raw.id,
            car.id,
            dt.date(2026, 9, 20),
            created_at=dt.datetime(2026, 8, 1, tzinfo=UTC),
        )
        aug = _event("u1", raw.id, car.id, dt.date(2026, 8, 20))
        usd_event = _event("u1", raw.id, car.id, dt.date(2026, 9, 8))
        oct_edge = _event("u1", raw.id, car.id, dt.date(2026, 10, 1))
        bill = Event(
            id=new_ulid(),
            user_id="u1",
            type_id=core_concept_id("event.recurring_bill"),
            time=TimeValue(
                original_text="todo dia 10",
                precision=TimePrecision.RECURRING,
                recurrence=Recurrence(freq="monthly", by_monthday=10),
                resolution_rule="recurrence.as_stated",
            ),
            status=EventStatus.SCHEDULED,
            raw_input_id=raw.id,
            created_at=dt.datetime(2026, 9, 1, tzinfo=UTC),
        )
        for event in (sep_a, sep_b, aug, usd_event, oct_edge, bill):
            uow.events.add(event)
        seed.sep_a, seed.sep_b, seed.aug, seed.usd, seed.bill = (
            sep_a.id,
            sep_b.id,
            aug.id,
            usd_event.id,
            bill.id,
        )
        fact_a = _amount("u1", sep_a.id, raw.id, "320")
        old = _amount("u1", sep_b.id, raw.id, "180")
        uow.facts.add(fact_a)
        uow.facts.add(old)
        uow.facts.save(old.mark_superseded(dt.datetime(2026, 9, 21, tzinfo=UTC)))
        new = _amount("u1", sep_b.id, raw.id, "186.50", supersedes_id=old.id)
        uow.facts.add(new)
        uow.facts.add(_amount("u1", aug.id, raw.id, "50"))
        uow.facts.add(_amount("u1", usd_event.id, raw.id, "20", currency="USD"))
        uow.facts.add(_amount("u1", bill.id, raw.id, "129.90"))
        seed.sep_a_fact, seed.old_fact, seed.new_fact = fact_a.id, old.id, new.id
        raw_b = _raw("u2")
        civic = _car("u2", "Civic")
        uow.raw_inputs.add(raw_b)
        uow.entities.add(civic)
        other = _event("u2", raw_b.id, civic.id, dt.date(2026, 9, 5))
        uow.events.add(other)
        uow.facts.add(_amount("u2", other.id, raw_b.id, "999"))
        seed.civic, seed.other_event = civic.id, other.id
        uow.commit()
    return seed


def _engine(db_path: Path, ontology: OntologyRegistry) -> QueryEngine:
    return QueryEngine(open_sqlite_read_store(db_path), ontology)


def test_get_event_by_id(db_path: Path, ontology: OntologyRegistry) -> None:
    seed = _seed(db_path)
    result = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(user_id="u1", event_ids=[seed.sep_a])
    )
    assert [item.event_id for item in result.items] == [seed.sep_a]


def test_list_events_for_entity_subject(db_path: Path, ontology: OntologyRegistry) -> None:
    seed = _seed(db_path)
    result = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            entity_ids=[seed.corolla],
            entity_association=EntityAssociation.SUBJECT,
            event_type_ids=[core_concept_id("event.vehicle_maintenance")],
        )
    )
    ids = {item.event_id for item in result.items}
    assert seed.sep_a in ids
    assert seed.bill not in ids


def test_exact_excludes_descendant(db_path: Path, ontology: OntologyRegistry) -> None:
    _seed(db_path)
    result = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            event_type_ids=[core_concept_id("event.maintenance")],
            hierarchy=HierarchyMode.EXACT,
        )
    )
    assert result.items == []


def test_include_descendants(db_path: Path, ontology: OntologyRegistry) -> None:
    seed = _seed(db_path)
    result = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            event_type_ids=[core_concept_id("event.maintenance")],
            hierarchy=HierarchyMode.INCLUDE_DESCENDANTS,
        )
    )
    ids = {item.event_id for item in result.items}
    assert seed.sep_a in ids
    assert seed.bill not in ids


def test_time_range_start_included_end_excluded(
    db_path: Path, ontology: OntologyRegistry
) -> None:
    """Início entra; último dia linguístico entra; end exclusivo não entra."""
    with open_sqlite_uow(db_path) as uow:
        raw = _raw()
        car = _car()
        uow.raw_inputs.add(raw)
        uow.entities.add(car)
        start_ev = _event("u1", raw.id, car.id, dt.date(2026, 9, 1))
        last_day = _event("u1", raw.id, car.id, dt.date(2026, 9, 3))
        exclusive = _event("u1", raw.id, car.id, dt.date(2026, 9, 4))
        for event in (start_ev, last_day, exclusive):
            uow.events.add(event)
        uow.commit()
    linguistic = TimeRange(
        start=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 9, 4, tzinfo=FORTALEZA),
    )
    result = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            event_type_ids=[core_concept_id("event.vehicle_maintenance")],
            time_range=linguistic,
        )
    )
    ids = {item.event_id for item in result.items}
    assert start_ev.id in ids
    assert last_day.id in ids
    assert exclusive.id not in ids


def test_time_range_half_open(db_path: Path, ontology: OntologyRegistry) -> None:
    seed = _seed(db_path)
    result = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            event_type_ids=[core_concept_id("event.vehicle_maintenance")],
            time_range=SEP,
        )
    )
    ids = {item.event_id for item in result.items}
    assert seed.sep_a in ids
    assert seed.aug not in ids
    oct_start = TimeRange(
        start=dt.datetime(2026, 10, 1, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 11, 1, tzinfo=FORTALEZA),
    )
    edge = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            event_type_ids=[core_concept_id("event.vehicle_maintenance")],
            time_range=oct_start,
        )
    )
    assert any(item.event_id != seed.sep_a for item in edge.items)
    assert seed.sep_a not in {item.event_id for item in edge.items}


def test_current_and_history(db_path: Path, ontology: OntologyRegistry) -> None:
    seed = _seed(db_path)
    engine = _engine(db_path, ontology)
    spec = ResolvedQuerySpec(
        user_id="u1",
        event_ids=[seed.sep_b],
        fact_concept_ids=[core_concept_id("attribute.amount")],
        fact_version_policy=FactVersionPolicy.CURRENT,
    )
    current = engine.execute(spec)
    assert [item.fact_id for item in current.items] == [seed.new_fact]
    hist = engine.execute(
        spec.model_copy(update={"fact_version_policy": FactVersionPolicy.HISTORY})
    )
    assert {item.fact_id for item in hist.items} == {seed.old_fact, seed.new_fact}


def test_sum_current_decimal_and_provenance(
    db_path: Path, ontology: OntologyRegistry
) -> None:
    seed = _seed(db_path)
    result = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            entity_ids=[seed.corolla],
            entity_association=EntityAssociation.SUBJECT,
            event_type_ids=[core_concept_id("event.vehicle_maintenance")],
            fact_concept_ids=[core_concept_id("attribute.amount")],
            time_range=SEP,
            aggregate=AggregateKind.SUM,
            currency="BRL",
        )
    )
    assert result.aggregate is not None
    assert result.aggregate.value == Decimal("506.50")
    assert result.aggregate.currency == "BRL"
    assert set(result.aggregate.contributing_fact_ids) == {seed.sep_a_fact, seed.new_fact}
    assert seed.old_fact not in result.aggregate.contributing_fact_ids


def test_sum_rejects_multi_currency(db_path: Path, ontology: OntologyRegistry) -> None:
    seed = _seed(db_path)
    with pytest.raises(MultiCurrencyAggregateError):
        _engine(db_path, ontology).execute(
            ResolvedQuerySpec(
                user_id="u1",
                entity_ids=[seed.corolla],
                entity_association=EntityAssociation.SUBJECT,
                event_type_ids=[core_concept_id("event.vehicle_maintenance")],
                fact_concept_ids=[core_concept_id("attribute.amount")],
                time_range=SEP,
                aggregate=AggregateKind.SUM,
            )
        )


def test_count_and_combined_filters(db_path: Path, ontology: OntologyRegistry) -> None:
    seed = _seed(db_path)
    result = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            entity_ids=[seed.corolla],
            entity_association=EntityAssociation.SUBJECT,
            event_type_ids=[core_concept_id("event.vehicle_maintenance")],
            event_statuses=[EventStatus.COMPLETED.value],
            domain_ids=[core_concept_id("domain.vehicle")],
            time_range=SEP,
            aggregate=AggregateKind.COUNT,
        )
    )
    assert result.aggregate is not None
    assert result.aggregate.value == 3
    assert seed.bill not in result.aggregate.contributing_event_ids


def test_latest_uses_event_time_not_created_at(
    db_path: Path, ontology: OntologyRegistry
) -> None:
    seed = _seed(db_path)
    result = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            entity_ids=[seed.corolla],
            entity_association=EntityAssociation.SUBJECT,
            event_type_ids=[core_concept_id("event.vehicle_maintenance")],
            time_range=SEP,
            aggregate=AggregateKind.LATEST,
            fact_concept_ids=[core_concept_id("attribute.amount")],
            currency="BRL",
        )
    )
    assert result.aggregate is not None
    assert result.aggregate.contributing_event_ids == [seed.sep_b]
    assert result.aggregate.value == Decimal("186.50")


def test_isolation_and_unknown_concept(db_path: Path, ontology: OntologyRegistry) -> None:
    seed = _seed(db_path)
    engine = _engine(db_path, ontology)
    with pytest.raises(QueryIsolationError):
        engine.execute(ResolvedQuerySpec(user_id="u1", event_ids=[seed.other_event]))
    with pytest.raises(QueryIsolationError):
        engine.execute(
            ResolvedQuerySpec(
                user_id="u1",
                entity_ids=[seed.civic],
                entity_association=EntityAssociation.SUBJECT,
            )
        )
    foreign = engine.execute(ResolvedQuerySpec(user_id="u2", event_ids=[seed.other_event]))
    assert [item.event_id for item in foreign.items] == [seed.other_event]
    with pytest.raises(QuerySpecError, match="inexistente"):
        engine.execute(ResolvedQuerySpec(user_id="u1", event_type_ids=["core:event.unknown"]))
    with pytest.raises(QuerySpecError, match="kind"):
        engine.execute(
            ResolvedQuerySpec(user_id="u1", event_type_ids=[core_concept_id("attribute.amount")])
        )


def test_recurring_bill_not_exploded_into_september(
    db_path: Path, ontology: OntologyRegistry
) -> None:
    seed = _seed(db_path)
    result = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            event_type_ids=[core_concept_id("event.recurring_bill")],
            time_range=SEP,
        )
    )
    assert result.items == []
    listed = _engine(db_path, ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            event_type_ids=[core_concept_id("event.recurring_bill")],
        )
    )
    assert [item.event_id for item in listed.items] == [seed.bill]


def test_deterministic_and_no_interpreter(db_path: Path, ontology: OntologyRegistry) -> None:
    seed = _seed(db_path)
    engine = _engine(db_path, ontology)
    spec = ResolvedQuerySpec(user_id="u1", event_ids=[seed.sep_a])
    first = engine.execute(spec)
    second = engine.execute(spec)
    assert first.model_dump() == second.model_dump()
    root = Path(__file__).parents[2] / "src" / "pke" / "query"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "FakeInterpreter" not in text
        assert "from pke.interpretation" not in text
        assert "openai" not in text.lower()
        assert "ollama" not in text.lower()


def test_persist_does_not_import_query() -> None:
    root = Path(__file__).parents[2] / "src" / "pke" / "persist"
    for path in root.rglob("*.py"):
        assert "pke.query" not in path.read_text(encoding="utf-8")
