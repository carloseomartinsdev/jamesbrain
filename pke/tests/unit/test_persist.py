from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from pke.domain import (
    AnchorKind,
    Confidence,
    DayPeriod,
    Entity,
    Event,
    EventStatus,
    Fact,
    Money,
    RawInput,
    Recurrence,
    Relation,
    Source,
    SourceKind,
    State,
    TimePrecision,
    TimeValue,
    new_ulid,
)
from pke.ontology.seeds import CORE_SCHEMA_VERSION, core_concept_id
from pke.persist import (
    STORAGE_SCHEMA_FROZEN,
    STORAGE_SCHEMA_VERSION,
    RawInputImmutableError,
    SqliteUnitOfWork,
    StorageIntegrityError,
    open_sqlite_uow,
)
from pke.persist.sqlite.engine import create_sqlite_engine, sqlite_url

UTC = dt.UTC


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "pke.db"


@pytest.fixture
def uow_factory(db_path: Path):
    def _open() -> SqliteUnitOfWork:
        return open_sqlite_uow(db_path)

    return _open


def _raw(user: str = "u1") -> RawInput:
    return RawInput(
        id=new_ulid(),
        user_id=user,
        text="Troquei o óleo do Corolla hoje.",
        created_at=dt.datetime(2026, 9, 1, 18, 0, tzinfo=UTC),
    )


def _entity(user: str = "u1", name: str = "Corolla", aliases: list[str] | None = None) -> Entity:
    return Entity(
        id=new_ulid(),
        user_id=user,
        type_id=core_concept_id("entity.automobile"),
        canonical_name=name,
        aliases=aliases or [],
        created_at=dt.datetime(2026, 9, 1, tzinfo=UTC),
    )


def _time(**kwargs) -> TimeValue:
    base = dict(
        original_text="hoje",
        date=dt.date(2026, 9, 1),
        precision=TimePrecision.DAY,
        timezone="America/Fortaleza",
        reference_at=dt.datetime(2026, 9, 1, 15, 0, tzinfo=dt.timezone(dt.timedelta(hours=-3))),
        reference_timezone="America/Fortaleza",
        resolution_rule="relative.today",
    )
    base.update(kwargs)
    return TimeValue(**base)


def _event(user: str, raw_id: str, actor_id: str, **kwargs) -> Event:
    data = dict(
        id=new_ulid(),
        user_id=user,
        type_id=core_concept_id("event.vehicle_maintenance"),
        action_id=core_concept_id("action.oil_change"),
        actor_id=actor_id,
        time=_time(),
        status=EventStatus.COMPLETED,
        domain_ids=[core_concept_id("domain.vehicle"), core_concept_id("domain.finance")],
        raw_input_id=raw_id,
        created_at=dt.datetime(2026, 9, 1, 18, 1, tzinfo=UTC),
    )
    data.update(kwargs)
    return Event(**data)


def _fact(user: str, about_id: str, raw_id: str, **kwargs) -> Fact:
    data = dict(
        id=new_ulid(),
        user_id=user,
        about_kind=AnchorKind.EVENT,
        about_id=about_id,
        concept_id=core_concept_id("attribute.amount"),
        key="attribute.amount",
        value=Money(amount=Decimal("320.00"), currency="BRL"),
        source=Source(
            user_id=user,
            kind=SourceKind.USER_STATEMENT,
            raw_input_id=raw_id,
            id=new_ulid(),
        ),
        confidence=Confidence(score=1.0),
        created_at=dt.datetime(2026, 9, 1, 18, 2, tzinfo=UTC),
    )
    data.update(kwargs)
    return Fact(**data)


def _seed(uow: SqliteUnitOfWork, user: str = "u1"):
    raw = _raw(user)
    ent = _entity(user)
    uow.raw_inputs.add(raw)
    uow.entities.add(ent)
    return raw, ent


def test_raw_input_round_trip(uow_factory) -> None:
    raw = _raw()
    with uow_factory() as uow:
        uow.raw_inputs.add(raw)
        uow.commit()
    with uow_factory() as uow:
        got = uow.raw_inputs.get("u1", raw.id)
        assert got is not None
        assert got.text == raw.text
        assert got.created_at == raw.created_at


def test_raw_input_immutable(uow_factory) -> None:
    raw = _raw()
    with uow_factory() as uow:
        uow.raw_inputs.add(raw)
        uow.commit()
    with uow_factory() as uow, pytest.raises(RawInputImmutableError):
        uow.raw_inputs.add(raw)


def test_source_user_owned_and_cross_user_rejected(uow_factory) -> None:
    raw = _raw("u1")
    source = Source(
        user_id="u1",
        kind=SourceKind.USER_STATEMENT,
        raw_input_id=raw.id,
        id=new_ulid(),
    )
    with uow_factory() as uow:
        uow.raw_inputs.add(raw)
        stored = uow.sources.add(source)
        uow.commit()
        sid = stored.id
        assert sid is not None
    with uow_factory() as uow:
        got = uow.sources.get("u1", sid)
        assert got is not None
        assert got.user_id == "u1"
        assert got.raw_input_id == raw.id
        assert uow.sources.get("u2", sid) is None
        foreign_raw = _raw("u2")
        uow.raw_inputs.add(foreign_raw)
        with pytest.raises(StorageIntegrityError):
            uow.sources.add(
                Source(
                    user_id="u1",
                    kind=SourceKind.INFERENCE,
                    raw_input_id=foreign_raw.id,
                    id=new_ulid(),
                )
            )


def test_entity_and_alias_isolation(uow_factory) -> None:
    car = _entity(aliases=["relampago"])
    with uow_factory() as uow:
        raw = _raw()
        uow.raw_inputs.add(raw)
        uow.entities.add(car)
        uow.commit()
    with uow_factory() as uow:
        got = uow.entities.get("u1", car.id)
        assert got is not None
        assert "relampago" in got.aliases
        assert uow.entities.get("u2", car.id) is None


def test_event_and_timevalue_round_trip(uow_factory) -> None:
    with uow_factory() as uow:
        raw, ent = _seed(uow)
        event = _event("u1", raw.id, ent.id)
        stored = uow.events.add(event)
        uow.commit()
        event_id = stored.id
        raw_id = raw.id
    with uow_factory() as uow:
        got = uow.events.get("u1", event_id)
        assert got is not None
        assert got.time.original_text == "hoje"
        assert got.time.date == dt.date(2026, 9, 1)
        assert got.time.resolution_rule == "relative.today"
        assert got.time.reference_timezone == "America/Fortaleza"
        assert got.time.timezone == "America/Fortaleza"
        assert got.time.reference_at is not None
        assert got.time.reference_at == dt.datetime(2026, 9, 1, 18, 0, tzinfo=UTC)
        assert got.raw_input_id == raw_id
        assert set(got.domain_ids) == {
            core_concept_id("domain.vehicle"),
            core_concept_id("domain.finance"),
        }
        assert got.type_id == core_concept_id("event.vehicle_maintenance")


def test_day_period_round_trip_no_invented_time(uow_factory) -> None:
    with uow_factory() as uow:
        raw, ent = _seed(uow)
        event = _event(
            "u1",
            raw.id,
            ent.id,
            time=_time(
                original_text="quinta de manhã",
                date=dt.date(2026, 9, 3),
                precision=TimePrecision.DAY_PERIOD,
                day_period=DayPeriod.MORNING,
                time_of_day=None,
                instant=None,
            ),
        )
        uow.events.add(event)
        uow.commit()
        eid = event.id
    with uow_factory() as uow:
        got = uow.events.get("u1", eid)
        assert got is not None
        assert got.time.day_period is DayPeriod.MORNING
        assert got.time.time_of_day is None
        assert got.time.instant is None


def test_recurrence_round_trip(uow_factory) -> None:
    with uow_factory() as uow:
        raw, ent = _seed(uow)
        event = _event(
            "u1",
            raw.id,
            ent.id,
            time=_time(
                original_text="todo dia 10",
                precision=TimePrecision.RECURRING,
                date=None,
                recurrence=Recurrence(freq="monthly", by_monthday=10),
            ),
        )
        uow.events.add(event)
        uow.commit()
        eid = event.id
    with uow_factory() as uow:
        got = uow.events.get("u1", eid)
        assert got is not None
        assert got.time.recurrence is not None
        assert got.time.recurrence.by_monthday == 10


def test_money_decimal_and_fact_round_trip(uow_factory) -> None:
    with uow_factory() as uow:
        raw, ent = _seed(uow)
        event = _event("u1", raw.id, ent.id)
        uow.events.add(event)
        fact = _fact("u1", event.id, raw.id)
        uow.facts.add(fact)
        uow.commit()
        fid = fact.id
        rid = raw.id
    with uow_factory() as uow:
        got = uow.facts.get("u1", fid)
        assert got is not None
        assert isinstance(got.value, Money)
        assert got.value.amount == Decimal("320.00")
        assert got.value.currency == "BRL"
        assert not isinstance(got.value.amount, float)
        assert got.source.raw_input_id == rid
        assert got.source.kind is SourceKind.USER_STATEMENT


def test_fact_supersession_keeps_history(uow_factory) -> None:
    with uow_factory() as uow:
        raw, ent = _seed(uow)
        event = _event("u1", raw.id, ent.id)
        uow.events.add(event)
        old = _fact("u1", event.id, raw.id, value=Money(amount=Decimal("180"), currency="BRL"))
        uow.facts.add(old)
        historic = old.mark_superseded(dt.datetime(2026, 9, 1, 19, tzinfo=UTC))
        uow.facts.save(historic)
        new = _fact(
            "u1",
            event.id,
            raw.id,
            value=Money(amount=Decimal("186.50"), currency="BRL"),
            supersedes_id=old.id,
        )
        uow.facts.add(new)
        uow.commit()
        about = event.id
        old_id, new_id = old.id, new.id
    with uow_factory() as uow:
        hist = uow.facts.history("u1", about, core_concept_id("attribute.amount"))
        assert [f.id for f in hist] == [old_id, new_id]
        assert hist[0].superseded_at is not None
        assert hist[1].supersedes_id == old_id
        assert uow.facts.get("u1", old_id) is not None


def test_supersession_chain_is_linear_and_same_target(uow_factory) -> None:
    with uow_factory() as uow:
        raw, ent = _seed(uow, "u1")
        event = _event("u1", raw.id, ent.id)
        other = _event("u1", raw.id, ent.id)
        uow.events.add(event)
        uow.events.add(other)
        raw_b = _raw("u2")
        car_b = _entity("u2", "Civic")
        uow.raw_inputs.add(raw_b)
        uow.entities.add(car_b)
        event_b = _event("u2", raw_b.id, car_b.id)
        uow.events.add(event_b)
        a = _fact("u1", event.id, raw.id, value=Money(amount=Decimal("100"), currency="BRL"))
        uow.facts.add(a)
        b = _fact(
            "u1",
            event.id,
            raw.id,
            value=Money(amount=Decimal("110"), currency="BRL"),
            supersedes_id=a.id,
        )
        uow.facts.add(b)
        c = _fact(
            "u1",
            event.id,
            raw.id,
            value=Money(amount=Decimal("120"), currency="BRL"),
            supersedes_id=b.id,
        )
        uow.facts.add(c)
        with pytest.raises(StorageIntegrityError, match="sucessor"):
            uow.facts.add(
                _fact(
                    "u1",
                    event.id,
                    raw.id,
                    value=Money(amount=Decimal("99"), currency="BRL"),
                    supersedes_id=a.id,
                )
            )
        with pytest.raises(StorageIntegrityError, match="about"):
            uow.facts.add(
                _fact(
                    "u1",
                    other.id,
                    raw.id,
                    value=Money(amount=Decimal("1"), currency="BRL"),
                    supersedes_id=c.id,
                )
            )
        with pytest.raises(StorageIntegrityError, match="concept"):
            uow.facts.add(
                _fact(
                    "u1",
                    event.id,
                    raw.id,
                    concept_id=core_concept_id("attribute.mileage"),
                    key="attribute.mileage",
                    value=80000,
                    supersedes_id=c.id,
                )
            )
        fact_b = _fact("u2", event_b.id, raw_b.id)
        uow.facts.add(fact_b)
        with pytest.raises(StorageIntegrityError, match="cross-user"):
            uow.facts.add(
                _fact(
                    "u2",
                    event_b.id,
                    raw_b.id,
                    supersedes_id=c.id,
                )
            )
        uow.commit()
        about, ids = event.id, [a.id, b.id, c.id]
    with uow_factory() as uow:
        hist = uow.facts.history("u1", about, core_concept_id("attribute.amount"))
        assert [f.id for f in hist] == ids
        superseded = {f.supersedes_id for f in hist if f.supersedes_id}
        current = [f for f in hist if f.id not in superseded]
        assert [f.id for f in current] == [ids[2]]
        assert current[0].value.amount == Decimal("120")


def test_relation_round_trip_and_cross_user(uow_factory) -> None:
    from pke.domain.temporal_knowledge import TemporalKnowledge

    with uow_factory() as uow:
        raw_a, car = _seed(uow, "u1")
        raw_b = _raw("u2")
        other = _entity("u2", "Civic")
        uow.raw_inputs.add(raw_b)
        uow.entities.add(other)
        rel = Relation(
            id=new_ulid(),
            user_id="u1",
            from_id=car.id,
            to_id=car.id,
            concept_id=core_concept_id("relation.owns"),
            key="relation.owns",
            temporal=TemporalKnowledge.partial_ongoing(),
            observed_at=dt.datetime(2026, 9, 1, tzinfo=UTC),
            created_at=dt.datetime(2026, 9, 1, tzinfo=UTC),
        )
        uow.relations.add(rel)
        uow.commit()
        rid = rel.id
        other_id = other.id
        car_id = car.id
    with uow_factory() as uow:
        assert uow.relations.get("u1", rid) is not None
        with pytest.raises(StorageIntegrityError):
            uow.relations.add(
                Relation(
                    id=new_ulid(),
                    user_id="u1",
                    from_id=car_id,
                    to_id=other_id,
                    concept_id=core_concept_id("relation.owns"),
                    key="relation.owns",
                    temporal=TemporalKnowledge.partial_ongoing(),
                    observed_at=dt.datetime(2026, 9, 1, tzinfo=UTC),
                    created_at=dt.datetime(2026, 9, 1, tzinfo=UTC),
                )
            )


def test_state_history_not_overwritten(uow_factory) -> None:
    from pke.domain.temporal_knowledge import TemporalKnowledge

    with uow_factory() as uow:
        raw, ent = _seed(uow)
        s1 = State(
            id=new_ulid(),
            user_id="u1",
            entity_id=ent.id,
            dimension_id=core_concept_id("state.observed_quantity"),
            dimension_key="state.observed_quantity",
            value_concept_id=core_concept_id("state.value.quantity_observation"),
            value_key="state.value.quantity_observation",
            payload=82000,
            temporal=TemporalKnowledge.partial_ongoing(),
            observed_at=dt.datetime(2026, 8, 1, tzinfo=UTC),
            valid_from=dt.datetime(2026, 8, 1, tzinfo=UTC),
            valid_to=dt.datetime(2026, 9, 1, tzinfo=UTC),
            is_current=False,
        )
        s2 = State(
            id=new_ulid(),
            user_id="u1",
            entity_id=ent.id,
            dimension_id=core_concept_id("state.observed_quantity"),
            dimension_key="state.observed_quantity",
            value_concept_id=core_concept_id("state.value.quantity_observation"),
            value_key="state.value.quantity_observation",
            payload=84500,
            temporal=TemporalKnowledge.partial_ongoing(),
            observed_at=dt.datetime(2026, 9, 1, tzinfo=UTC),
            valid_from=dt.datetime(2026, 9, 1, tzinfo=UTC),
            is_current=True,
        )
        uow.states.add(s1)
        uow.states.add(s2)
        uow.commit()
        eid = ent.id
        first = s1.id
    with uow_factory() as uow:
        rows = uow.states.for_entity("u1", eid)
        assert len(rows) == 2
        assert uow.states.get("u1", first) is not None
        assert rows[0].payload == 82000
        assert rows[1].payload == 84500


def test_rollback_removes_all(uow_factory) -> None:
    raw, ent = _raw(), _entity()
    event = _event("u1", raw.id, ent.id)
    fact = _fact("u1", event.id, raw.id)
    with pytest.raises(RuntimeError, match="pipeline abort"):
        with uow_factory() as uow:
            uow.raw_inputs.add(raw)
            uow.entities.add(ent)
            uow.events.add(event)
            uow.facts.add(fact)
            raise RuntimeError("pipeline abort")
    with uow_factory() as uow:
        assert uow.raw_inputs.get("u1", raw.id) is None
        assert uow.entities.get("u1", ent.id) is None
        assert uow.events.get("u1", event.id) is None
        assert uow.facts.get("u1", fact.id) is None


def test_commit_keeps_all(uow_factory) -> None:
    raw, ent = _raw(), _entity()
    event = _event("u1", raw.id, ent.id)
    fact = _fact("u1", event.id, raw.id)
    with uow_factory() as uow:
        uow.raw_inputs.add(raw)
        uow.entities.add(ent)
        uow.events.add(event)
        uow.facts.add(fact)
        uow.commit()
    with uow_factory() as uow:
        assert uow.raw_inputs.get("u1", raw.id) is not None
        assert uow.entities.get("u1", ent.id) is not None
        assert uow.events.get("u1", event.id) is not None
        assert uow.facts.get("u1", fact.id) is not None


def test_missing_entity_fk_rejected(uow_factory) -> None:
    from pke.domain.temporal_knowledge import TemporalKnowledge

    with uow_factory() as uow:
        raw = _raw()
        uow.raw_inputs.add(raw)
        with pytest.raises(StorageIntegrityError):
            uow.events.add(_event("u1", raw.id, actor_id=new_ulid()))
        with pytest.raises(StorageIntegrityError):
            uow.facts.add(_fact("u1", about_id=new_ulid(), raw_id=raw.id))
        with pytest.raises(StorageIntegrityError):
            uow.relations.add(
                Relation(
                    id=new_ulid(),
                    user_id="u1",
                    from_id=new_ulid(),
                    to_id=new_ulid(),
                    concept_id=core_concept_id("relation.owns"),
                    key="relation.owns",
                    temporal=TemporalKnowledge.partial_ongoing(),
                    observed_at=dt.datetime(2026, 9, 1, tzinfo=UTC),
                    created_at=dt.datetime(2026, 9, 1, tzinfo=UTC),
                )
            )


def test_fact_rejects_foreign_source(uow_factory) -> None:
    with uow_factory() as uow:
        raw_a, car = _seed(uow, "u1")
        event = _event("u1", raw_a.id, car.id)
        uow.events.add(event)
        raw_b = _raw("u2")
        uow.raw_inputs.add(raw_b)
        foreign = Source(
            user_id="u2",
            kind=SourceKind.USER_STATEMENT,
            raw_input_id=raw_b.id,
            id=new_ulid(),
        )
        uow.sources.add(foreign)
        with pytest.raises(StorageIntegrityError):
            uow.facts.add(_fact("u1", event.id, raw_a.id, source=foreign))
        uow.rollback()


def test_schema_versions_and_reopen(uow_factory, db_path: Path) -> None:
    with uow_factory() as uow:
        raw, _ent = _seed(uow)
        uow.commit()
        rid = raw.id
    engine = create_sqlite_engine(sqlite_url(db_path))
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT storage_schema_version, core_schema_version FROM schema_meta")
        ).one()
        assert row[0] == STORAGE_SCHEMA_VERSION
        assert row[1] == CORE_SCHEMA_VERSION
        assert STORAGE_SCHEMA_FROZEN is False
        fk = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert fk == 1
    with uow_factory() as uow:
        assert uow.raw_inputs.get("u1", rid) is not None


def test_created_at_is_utc(uow_factory) -> None:
    raw = _raw()
    with uow_factory() as uow:
        uow.raw_inputs.add(raw)
        uow.commit()
    with uow_factory() as uow:
        got = uow.raw_inputs.get("u1", raw.id)
        assert got is not None
        assert got.created_at.tzinfo is not None
        assert got.created_at.utcoffset() == dt.timedelta(0)


def test_persist_package_does_not_interpret() -> None:
    root = Path(__file__).parents[2] / "src" / "pke" / "persist"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "FakeInterpreter" not in text
        assert "from pke.interpretation.interpreter" not in text


def test_domain_does_not_import_sqlalchemy() -> None:
    root = Path(__file__).parents[2] / "src" / "pke" / "domain"
    for path in root.rglob("*.py"):
        assert "sqlalchemy" not in path.read_text(encoding="utf-8")
