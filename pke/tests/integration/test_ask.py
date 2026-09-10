from __future__ import annotations

import datetime as dt
import sqlite3
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
    ResolvedQueryBuilder,
    SessionContext,
)
from pke.domain import (
    AnchorKind,
    ConceptRef,
    Confidence,
    Entity,
    EpistemicStatus,
    Event,
    EventStatus,
    Fact,
    Money,
    Qualifier,
    RawInput,
    RelativeDay,
    Source,
    SourceKind,
    TimePrecision,
    TimeValue,
    UserContext,
    new_ulid,
)
from pke.interpretation import (
    CorrectionStrategy,
    EntityMention,
    FakeInterpreter,
    IngestIntent,
    IngestIR,
    IrCorrection,
    IrEvent,
    IrFact,
    IrQueryTime,
    IrTime,
    MentionReferenceKind,
    QueryIR,
    QuerySpec,
    RelativePeriod,
    ScriptedInterpreter,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.query.spec import AggregateKind, EntityAssociation, FactVersionPolicy, TimeRange
from pke.resolution import InMemoryEntityLookup, PersonalContext
from tests.integration.test_ingest import RAW_A, RAW_D1, RAW_E, ir_a, ir_d1, ir_e

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)
RAW_F = "Quanto gastei com o Corolla este mês?"
RAW_LAST = "Quanto gastei com o Corolla no mês passado?"
TABLES = (
    "raw_inputs",
    "entities",
    "events",
    "facts",
    "entity_aliases",
    "sources",
    "relations",
    "states",
)


def _amount(value: str, *, approx: bool = False, confidence: float = 1.0) -> IrFact:
    return IrFact(
        attribute=ConceptRef(key="attribute.amount"),
        value={"amount": value, "currency": "BRL"},
        qualifier=Qualifier.APPROXIMATELY if approx else Qualifier.EXACT,
        epistemic_status=EpistemicStatus.UNCERTAIN if approx else EpistemicStatus.EXPLICIT,
        confidence=confidence,
    )


def _corolla() -> EntityMention:
    return EntityMention(
        text="Corolla",
        type_hint=ConceptRef(key="entity.automobile"),
        role=ConceptRef(key="role.subject"),
    )


def ir_a() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=RAW_A,
        domains=[ConceptRef(key="domain.vehicle"), ConceptRef(key="domain.finance")],
        entities_mentioned=[_corolla()],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.oil_change"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text="hoje", relative_day=RelativeDay.TODAY),
            facts=[_amount("320")],
        ),
    )


def ir_e() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.CORRECT,
        raw_input=RAW_E,
        correction=IrCorrection(
            strategy=CorrectionStrategy.LAST_EVENT,
            facts=[_amount("186.50")],
        ),
    )


def _session(user_id: str = "u1") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=user_id))


def _ingest(
    db_path: Path,
    ontology: OntologyRegistry,
    responses: dict[str, object],
) -> IngestService:
    return IngestService(
        FakeInterpreter(responses),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db_path),
        FixedClock(NOW),
    )


def _query_ir(
    raw: str = RAW_F,
    *,
    period: RelativePeriod | None = RelativePeriod.THIS_MONTH,
    entity: EntityMention | None = None,
    event_key: str = "event.vehicle_maintenance",
    fact_key: str = "attribute.amount",
    time: IrQueryTime | None = None,
) -> QueryIR:
    if time is None and period is not None:
        time = IrQueryTime(relative_period=period, original_text="este mês")
    return QueryIR(
        raw_input=raw,
        query=QuerySpec(
            intent="aggregate",
            entities=[entity or _corolla()],
            entity_association="subject",
            event_types=[ConceptRef(key=event_key)],
            facts=[ConceptRef(key=fact_key)],
            aggregate="sum",
            version_policy="current",
            time=time,
        ),
    )


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "ask.db"


@pytest.fixture
def user() -> UserContext:
    return UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)


def _ask(
    db_path: Path,
    ontology: OntologyRegistry,
    responses: dict[str, object],
) -> AskService:
    return AskService(
        FakeInterpreter(responses),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db_path),
        FixedClock(NOW),
    )


def _counts(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(db_path)
    try:
        return {table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}
    finally:
        con.close()


def _seed_case_f(db_path: Path, ontology: OntologyRegistry, user: UserContext) -> SessionContext:
    session = _session()
    service = _ingest(db_path, ontology, {RAW_A: ir_a(), RAW_D1: ir_d1(), RAW_E: ir_e()})
    assert service.ingest(RAW_A, user, session).status is IngestStatus.COMMITTED
    assert service.ingest(RAW_D1, user, session).status is IngestStatus.COMMITTED
    assert service.ingest(RAW_E, user, session).status is IngestStatus.COMMITTED
    return session


def test_query_ir_builds_resolved_spec(ontology: OntologyRegistry, user: UserContext) -> None:
    lookup = InMemoryEntityLookup()
    entity = Entity(
        id="ent-corolla",
        user_id="u1",
        type_id=core_concept_id("entity.automobile"),
        canonical_name="Corolla",
        created_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
    )
    lookup.add(entity)
    spec = ResolvedQueryBuilder(ontology).build(
        _query_ir(),
        user,
        SessionContext(personal=PersonalContext(user_id="u1")),
        lookup,
        now=NOW,
    )
    assert spec.entity_ids == [entity.id]
    assert spec.entity_association is EntityAssociation.SUBJECT
    assert spec.event_type_ids == [core_concept_id("event.vehicle_maintenance")]
    assert spec.fact_concept_ids == [core_concept_id("attribute.amount")]
    assert spec.aggregate is AggregateKind.SUM
    assert spec.fact_version_policy is FactVersionPolicy.CURRENT
    assert spec.time_range == TimeRange(
        start=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 10, 1, tzinfo=FORTALEZA),
    )


def test_named_and_contextual_entity(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _seed_case_f(db_path, ontology, user)
    named = _ask(db_path, ontology, {RAW_F: _query_ir()}).ask(RAW_F, user, session)
    assert named.status is AskStatus.ANSWERED
    entity_id = named.resolved_entity_ids[0]
    assert entity_id in session.personal.recent_entity_ids
    contextual = QueryIR(
        raw_input="e o carro?",
        query=QuerySpec(
            intent="aggregate",
            entities=[
                EntityMention(
                    text="o carro",
                    type_hint=ConceptRef(key="entity.automobile"),
                    reference_kind=MentionReferenceKind.CONTEXTUAL,
                )
            ],
            entity_association="subject",
            event_types=[ConceptRef(key="event.vehicle_maintenance")],
            facts=[ConceptRef(key="attribute.amount")],
            aggregate="sum",
            time=IrQueryTime(relative_period=RelativePeriod.THIS_MONTH),
        ),
    )
    result = _ask(db_path, ontology, {"e o carro?": contextual}).ask("e o carro?", user, session)
    assert result.status is AskStatus.ANSWERED
    assert result.resolved_entity_ids == [entity_id]


def test_unknown_entity_does_not_create(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()
    raw = "Quanto gastei com o Civic este mês?"
    ir = _query_ir(
        raw,
        entity=EntityMention(text="Civic", type_hint=ConceptRef(key="entity.automobile")),
    )
    result = _ask(db_path, ontology, {raw: ir}).ask(raw, user, session)
    assert result.status is AskStatus.NO_RESULTS
    with open_sqlite_uow(db_path) as uow:
        assert uow.entities.all_for_user("u1") == []
    assert _counts(db_path)["entities"] == 0
    assert _counts(db_path)["raw_inputs"] == 0


def test_ambiguous_entity_needs_clarification(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _seed_case_f(db_path, ontology, user)
    first = session.personal.recent_entity_ids[0]
    second = new_ulid()
    with open_sqlite_uow(db_path) as uow:
        uow.entities.add(
            Entity(
                id=second,
                user_id="u1",
                type_id=core_concept_id("entity.automobile"),
                canonical_name="Corolla",
                created_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
            )
        )
        uow.commit()
    result = _ask(db_path, ontology, {RAW_F: _query_ir()}).ask(RAW_F, user, session)
    assert result.status is AskStatus.NEEDS_CLARIFICATION
    assert result.query_result is None
    assert result.clarification is not None
    assert result.clarification.clarification_key == "clarify.entity.which_one"
    assert result.clarification.blocking is True
    assert set(result.clarification.candidate_entity_ids) == {first, second}


def test_query_does_not_learn_alias(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _seed_case_f(db_path, ontology, user)
    aliases_before = session.personal.confirmed_aliases.copy()
    mention = _corolla().model_copy(update={"suggested_aliases": ["carrão"]})
    ir = _query_ir(entity=mention)
    _ask(db_path, ontology, {RAW_F: ir}).ask(RAW_F, user, session)
    assert session.personal.confirmed_aliases == aliases_before
    with open_sqlite_uow(db_path) as uow:
        entity = uow.entities.get("u1", session.personal.recent_entity_ids[0])
        assert entity is not None
        assert "carrão" not in entity.aliases


def test_case_f_sum_current_provenance_readonly(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _seed_case_f(db_path, ontology, user)
    snapshot = _counts(db_path)
    raw_ids = snapshot["raw_inputs"]
    personal = list(session.personal.recent_entity_ids)
    service = _ask(db_path, ontology, {RAW_F: _query_ir(), RAW_LAST: _query_ir(RAW_LAST, period=RelativePeriod.LAST_MONTH)})
    first = service.ask(RAW_F, user, session)
    second = service.ask(RAW_F, user, session)
    assert first.status is AskStatus.ANSWERED
    assert first.model_dump() == second.model_dump()
    assert first.query_result is not None
    assert first.query_result.aggregate is not None
    assert first.query_result.aggregate.value == Decimal("506.50")
    assert first.query_result.aggregate.currency == "BRL"
    assert first.resolved_spec is not None
    assert first.resolved_spec.fact_version_policy is FactVersionPolicy.CURRENT
    assert first.resolved_spec.time_range is not None
    assert first.resolved_spec.time_range.start <= NOW < first.resolved_spec.time_range.end
    assert len(first.query_result.aggregate.contributing_fact_ids) == 2
    assert first.query_result.provenance_fact_ids == first.query_result.aggregate.contributing_fact_ids
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    amounts = []
    for fact_id in first.query_result.aggregate.contributing_fact_ids:
        fact = next(item for item in graph.facts if item.id == fact_id)
        assert fact.superseded_at is None
        assert isinstance(fact.value, Money)
        amounts.append(fact.value.amount)
    assert sorted(amounts) == [Decimal("186.50"), Decimal("320")]
    for fact in graph.facts:
        if isinstance(fact.value, Money) and fact.value.amount == Decimal("180"):
            assert fact.id not in first.query_result.aggregate.contributing_fact_ids
    last = service.ask(RAW_LAST, user, session)
    assert last.status is AskStatus.NO_RESULTS
    assert last.query_result is not None
    assert last.query_result.aggregate is not None
    assert last.query_result.aggregate.contributing_fact_ids == []
    assert last.issues == []
    assert _counts(db_path) == snapshot
    assert snapshot["raw_inputs"] == raw_ids
    assert session.personal.recent_entity_ids == personal
    con = sqlite3.connect(db_path)
    try:
        texts = [row[0] for row in con.execute("SELECT text FROM raw_inputs")]
    finally:
        con.close()
    assert RAW_F not in texts
    assert RAW_LAST not in texts


def test_scripted_interpreter_ask(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _seed_case_f(db_path, ontology, user)
    service = AskService(
        ScriptedInterpreter([_query_ir()]),
        ontology,
        open_sqlite_read_store(db_path),
        FixedClock(NOW),
    )
    result = service.ask(RAW_F, user, session)
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.aggregate is not None
    assert result.query_result.aggregate.value == Decimal("506.50")


def test_ingest_ir_unsupported_and_unknown_raw(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    unsupported = _ask(db_path, ontology, {RAW_A: ir_a()}).ask(RAW_A, user, _session())
    assert unsupported.status is AskStatus.UNSUPPORTED
    missing = _ask(db_path, ontology, {}).ask("???", user, _session())
    assert missing.status is AskStatus.REJECTED


def test_concept_errors_rejected(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _seed_case_f(db_path, ontology, user)
    unknown = _ask(
        db_path,
        ontology,
        {"q": _query_ir("q", event_key="event.not_a_thing")},
    ).ask("q", user, session)
    assert unknown.status is AskStatus.REJECTED
    kind = _ask(
        db_path,
        ontology,
        {"k": _query_ir("k", fact_key="event.vehicle_maintenance")},
    ).ask("k", user, session)
    assert kind.status is AskStatus.REJECTED


def test_multi_currency_rejected(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _seed_case_f(db_path, ontology, user)
    entity_id = session.personal.recent_entity_ids[0]
    with open_sqlite_uow(db_path) as uow:
        raw = RawInput(
            id=new_ulid(),
            user_id="u1",
            text="usd",
            created_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
        )
        uow.raw_inputs.add(raw)
        event = Event(
            id=new_ulid(),
            user_id="u1",
            type_id=core_concept_id("event.vehicle_maintenance"),
            action_id=core_concept_id("action.oil_change"),
            subject_id=entity_id,
            time=TimeValue(
                original_text="hoje",
                date=dt.date(2026, 9, 2),
                precision=TimePrecision.DAY,
                timezone="America/Fortaleza",
            ),
            status=EventStatus.COMPLETED,
            raw_input_id=raw.id,
            created_at=dt.datetime(2026, 9, 2, tzinfo=dt.UTC),
        )
        uow.events.add(event)
        uow.facts.add(
            Fact(
                id=new_ulid(),
                user_id="u1",
                about_kind=AnchorKind.EVENT,
                about_id=event.id,
                concept_id=core_concept_id("attribute.amount"),
                key="attribute.amount",
                value=Money(amount=Decimal("20"), currency="USD"),
                source=Source(
                    user_id="u1",
                    kind=SourceKind.USER_STATEMENT,
                    raw_input_id=raw.id,
                    id=new_ulid(),
                ),
                confidence=Confidence(score=1.0, qualifier=Qualifier.EXACT),
                created_at=dt.datetime(2026, 9, 2, tzinfo=dt.UTC),
            )
        )
        uow.commit()
    result = _ask(db_path, ontology, {RAW_F: _query_ir()}).ask(RAW_F, user, session)
    assert result.status is AskStatus.REJECTED
    assert any(issue.code == "query.multi_currency" for issue in result.issues)


def test_foreign_entity_does_not_leak(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    _seed_case_f(db_path, ontology, user)
    foreign_id = new_ulid()
    with open_sqlite_uow(db_path) as uow:
        uow.entities.add(
            Entity(
                id=foreign_id,
                user_id="u2",
                type_id=core_concept_id("entity.automobile"),
                canonical_name="Civic",
                created_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
            )
        )
        uow.commit()
    ir = _query_ir(
        entity=EntityMention(
            text="x",
            type_hint=ConceptRef(key="entity.automobile"),
            known_entity_id=foreign_id,
        )
    )
    result = _ask(db_path, ontology, {RAW_F: ir}).ask(RAW_F, user, _session())
    assert result.status is AskStatus.REJECTED
    assert result.query_result is None
    dumped = result.model_dump()
    assert "999" not in str(dumped)
    assert foreign_id not in (result.resolved_entity_ids or [])


def test_query_layer_does_not_import_interpretation() -> None:
    root = Path(__file__).parents[2] / "src" / "pke" / "query"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "pke.interpretation" not in text
        assert "FakeInterpreter" not in text


def test_ask_service_does_not_sum_decimal() -> None:
    ask = Path(__file__).parents[2] / "src" / "pke" / "application" / "ask.py"
    text = ask.read_text(encoding="utf-8")
    assert "Decimal" not in text
    assert "from decimal" not in text
    builder = Path(__file__).parents[2] / "src" / "pke" / "application" / "query_builder.py"
    assert "Decimal" not in builder.read_text(encoding="utf-8")
