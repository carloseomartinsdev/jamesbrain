from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pke.application import (
    ApprovedKnowledge,
    FixedClock,
    IngestService,
    IngestStatus,
    KnowledgeMaterializer,
    MaterializationDenied,
    SessionContext,
)
from pke.domain import (
    ConceptRef,
    EpistemicStatus,
    EventStatus,
    Money,
    Qualifier,
    Recurrence,
    RelativeDay,
    TimePrecision,
    UserContext,
    WeekdayPolicy,
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
    IrObligation,
    IrTime,
    QueryIR,
    QuerySpec,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist import open_sqlite_uow
from pke.resolution import PersonalContext

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)

RAW_A = "Troquei o óleo do Corolla hoje por 320 reais."
RAW_B = "Tenho dentista quinta às 15h com a Dra. Ana."
RAW_C = "A internet vence todo dia 10 e é 129,90."
RAW_D1 = "Acho que a revisão do Corolla hoje ficou em uns 180 reais."
RAW_D2 = "Acho que a revisão ficou em uns 180 reais."
RAW_E = "Não, achei a nota. Foi 186,50."
RAW_BAD_AMOUNT = "Troquei o óleo do Corolla hoje por -320 reais."
RAW_NO_TIME = "Troquei o óleo do Corolla."


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


def ir_a(raw: str = RAW_A) -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=raw,
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


def ir_b() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=RAW_B,
        domains=[ConceptRef(key="domain.health"), ConceptRef(key="domain.appointments")],
        entities_mentioned=[
            EntityMention(
                text="Dra. Ana",
                type_hint=ConceptRef(key="entity.person"),
                role=ConceptRef(key="role.provider"),
            )
        ],
        event=IrEvent(
            type=ConceptRef(key="event.appointment"),
            action=ConceptRef(key="action.attend"),
            status=EventStatus.SCHEDULED,
            time=IrTime(
                original_text="quinta às 15h",
                weekday=3,
                weekday_policy=WeekdayPolicy.NEXT,
                time_of_day=dt.time(15, 0),
            ),
            facts=[],
        ),
    )


def ir_c() -> IngestIR:
    cadence = Recurrence(freq="monthly", by_monthday=10)
    return IngestIR(
        intent=IngestIntent.RECORD_OBLIGATION,
        raw_input=RAW_C,
        domains=[ConceptRef(key="domain.finance"), ConceptRef(key="domain.services")],
        obligation=IrObligation(
            type=ConceptRef(key="event.recurring_bill"),
            cadence=cadence,
            due=IrTime(
                original_text="todo dia 10",
                precision=TimePrecision.RECURRING,
                recurrence=cadence,
            ),
            facts=[_amount("129.90")],
        ),
    )


def ir_d1() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=RAW_D1,
        domains=[ConceptRef(key="domain.vehicle"), ConceptRef(key="domain.finance")],
        entities_mentioned=[_corolla()],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.oil_change"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text="hoje", relative_day=RelativeDay.TODAY),
            facts=[_amount("180", approx=True, confidence=0.4)],
        ),
    )


def ir_d2() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=RAW_D2,
        domains=[ConceptRef(key="domain.vehicle"), ConceptRef(key="domain.finance")],
        entities_mentioned=[],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.oil_change"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text=""),
            facts=[_amount("180", approx=True, confidence=0.4)],
        ),
    )


def ir_d2_with_vehicle() -> IngestIR:
    return ir_d2().model_copy(update={"entities_mentioned": [_corolla()]})


def ir_e() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.CORRECT,
        raw_input=RAW_E,
        correction=IrCorrection(
            strategy=CorrectionStrategy.LAST_EVENT,
            facts=[_amount("186.50")],
        ),
    )


def ir_negative() -> IngestIR:
    ir = ir_a(RAW_BAD_AMOUNT)
    assert ir.event is not None
    return ir.model_copy(
        update={"event": ir.event.model_copy(update={"facts": [_amount("-320")]})}
    )


def ir_no_time() -> IngestIR:
    ir = ir_a(RAW_NO_TIME)
    assert ir.event is not None
    return ir.model_copy(
        update={"event": ir.event.model_copy(update={"time": IrTime(original_text="")})}
    )


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "pke.db"


@pytest.fixture
def user() -> UserContext:
    return UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)


def _session(user_id: str = "u1") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=user_id))


def _service(
    db_path: Path,
    ontology: OntologyRegistry,
    responses: dict[str, object],
    *,
    materializer: KnowledgeMaterializer | None = None,
) -> IngestService:
    return IngestService(
        FakeInterpreter(responses),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db_path),
        FixedClock(NOW),
        materializer=materializer,
    )


def test_case_a_commits_with_useful_mileage_clarification(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()
    service = _service(db_path, ontology, {RAW_A: ir_a()})
    result = service.ingest(RAW_A, user, session)
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization is not None
    assert result.materialization.created_entity_ids
    assert result.materialization.event_ids
    assert result.materialization.fact_ids
    assert result.clarification is not None
    assert result.clarification.question_key == "clarify.attribute.mileage"
    assert result.clarification.blocking is False
    with open_sqlite_uow(db_path) as uow:
        event = uow.events.get("u1", result.materialization.event_ids[0])
        assert event is not None
        assert event.type_id == core_concept_id("event.vehicle_maintenance")
        assert event.action_id == core_concept_id("action.oil_change")
        assert event.time.date == dt.date(2026, 9, 1)
        fact = uow.facts.get("u1", result.materialization.fact_ids[0])
        assert fact is not None
        assert isinstance(fact.value, Money)
        assert fact.value.amount == Decimal("320")
        assert fact.value.currency == "BRL"
        assert fact.source.raw_input_id == result.materialization.raw_input_id
        assert fact.source.user_id == "u1"
    assert session.personal.recent_entity_ids
    assert session.last_event_id == result.materialization.event_ids[0]


def test_case_b_appointment_no_specialty(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()
    result = _service(db_path, ontology, {RAW_B: ir_b()}).ingest(RAW_B, user, session)
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization is not None
    with open_sqlite_uow(db_path) as uow:
        event = uow.events.get("u1", result.materialization.event_ids[0])
        assert event is not None
        assert event.status is EventStatus.SCHEDULED
        assert event.time.date == dt.date(2026, 9, 3)
        assert event.time.time_of_day == dt.time(15, 0)
        assert event.time.instant is not None
        facts = [uow.facts.get("u1", fid) for fid in result.materialization.fact_ids]
        assert all(f is None or f.key != "attribute.specialty" for f in facts)
        entity = uow.entities.get("u1", result.materialization.created_entity_ids[0])
        assert entity is not None
        assert entity.canonical_name == "Dra. Ana"


def test_case_c_recurring_bill_no_house(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()
    result = _service(db_path, ontology, {RAW_C: ir_c()}).ingest(RAW_C, user, session)
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization is not None
    assert result.materialization.created_entity_ids == []
    with open_sqlite_uow(db_path) as uow:
        event = uow.events.get("u1", result.materialization.event_ids[0])
        assert event is not None
        assert event.type_id == core_concept_id("event.recurring_bill")
        assert event.actor_id is None
        assert event.time.recurrence is not None
        assert event.time.recurrence.by_monthday == 10
        fact = uow.facts.get("u1", result.materialization.fact_ids[0])
        assert fact is not None
        assert fact.value.amount == Decimal("129.90")
        assert uow.entities.all_for_user("u1") == []


def test_case_d1_keeps_approximate(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()
    result = _service(db_path, ontology, {RAW_D1: ir_d1()}).ingest(RAW_D1, user, session)
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization is not None
    with open_sqlite_uow(db_path) as uow:
        fact = uow.facts.get("u1", result.materialization.fact_ids[0])
        assert fact is not None
        assert fact.qualifier is Qualifier.APPROXIMATELY
        assert fact.epistemic_status is EpistemicStatus.UNCERTAIN
        assert fact.confidence.score == 0.4
        assert fact.source.kind.value == "user_statement"
        event = uow.events.get("u1", result.materialization.event_ids[0])
        assert event is not None
        assert event.time.original_text
        assert "hoje" in event.time.original_text.lower()
        assert event.time.date == dt.date(2026, 9, 1)


def test_case_d2_commits_temporally_incomplete(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()
    result = _service(db_path, ontology, {RAW_D2: ir_d2_with_vehicle()}).ingest(RAW_D2, user, session)
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization is not None
    assert not any(issue.code == "time.missing" for issue in result.issues)
    with open_sqlite_uow(db_path) as uow:
        event = uow.events.get("u1", result.materialization.event_ids[0])
        assert event is not None
        assert event.temporal.kind.value == "partial"
        assert event.temporal.relation_to_reference is not None
        assert event.temporal.relation_to_reference.value == "before"
        assert event.temporal.unknown_reason is not None
        assert event.temporal.unknown_reason.value == "not_provided"
        assert not event.temporal.has_calendar_anchor()


def test_case_e_supersedes_previous_fact(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()
    service = _service(db_path, ontology, {RAW_D1: ir_d1(), RAW_E: ir_e()})
    first = service.ingest(RAW_D1, user, session)
    assert first.status is IngestStatus.COMMITTED
    assert first.materialization is not None
    old_id = first.materialization.fact_ids[0]
    second = service.ingest(RAW_E, user, session)
    assert second.status is IngestStatus.COMMITTED
    assert second.materialization is not None
    new_id = second.materialization.fact_ids[0]
    assert second.materialization.source_ids != first.materialization.source_ids
    with open_sqlite_uow(db_path) as uow:
        old = uow.facts.get("u1", old_id)
        new = uow.facts.get("u1", new_id)
        assert old is not None and new is not None
        assert old.superseded_at is not None
        assert new.supersedes_id == old.id
        assert new.value.amount == Decimal("186.50")
        assert new.source.kind.value == "correction"
        hist = uow.facts.history("u1", old.about_id, core_concept_id("attribute.amount"))
        assert [f.id for f in hist] == [old_id, new_id]


def test_validation_error_zero_writes(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()
    result = _service(db_path, ontology, {RAW_BAD_AMOUNT: ir_negative()}).ingest(
        RAW_BAD_AMOUNT, user, session
    )
    assert result.status is IngestStatus.REJECTED
    assert result.materialization is None
    with open_sqlite_uow(db_path) as uow:
        assert uow.entities.all_for_user("u1") == []
    assert session.personal.recent_entity_ids == []


def test_essential_missing_zero_writes(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()
    result = _service(db_path, ontology, {RAW_NO_TIME: ir_no_time()}).ingest(
        RAW_NO_TIME, user, session
    )
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization is not None
    with open_sqlite_uow(db_path) as uow:
        event = uow.events.get("u1", result.materialization.event_ids[0])
        assert event is not None
        assert event.temporal.kind.value == "partial"


def test_create_candidate_rolls_back_on_later_failure(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()

    def boom(stage: str, _result: object) -> None:
        if stage == "first_fact":
            raise RuntimeError("forced pipeline abort")

    materializer = KnowledgeMaterializer(ontology, on_progress=boom)
    service = _service(db_path, ontology, {RAW_A: ir_a()}, materializer=materializer)
    with pytest.raises(RuntimeError, match="forced"):
        service.ingest(RAW_A, user, session)
    with open_sqlite_uow(db_path) as uow:
        assert uow.entities.all_for_user("u1") == []
    assert session.personal.recent_entity_ids == []


def test_existing_entity_reused_not_duplicated(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()
    service = _service(db_path, ontology, {RAW_A: ir_a()})
    first = service.ingest(RAW_A, user, session)
    second = service.ingest(RAW_A, user, session)
    assert first.materialization and second.materialization
    assert first.materialization.created_entity_ids
    assert second.materialization.created_entity_ids == []
    assert second.materialization.reused_entity_ids == first.materialization.created_entity_ids
    assert first.materialization.event_ids != second.materialization.event_ids


def test_cross_user_cannot_see_entity(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session_a = _session("u1")
    _service(db_path, ontology, {RAW_A: ir_a()}).ingest(RAW_A, user, session_a)
    session_b = _session("u2")
    other = UserContext(user_id="u2", timezone="America/Fortaleza", now=NOW)
    result = _service(db_path, ontology, {RAW_A: ir_a()}).ingest(RAW_A, other, session_b)
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization is not None
    assert result.materialization.created_entity_ids
    assert result.materialization.created_entity_ids != session_a.personal.recent_entity_ids


def test_correction_unresolved_does_not_persist(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = _session()
    result = _service(db_path, ontology, {RAW_E: ir_e()}).ingest(RAW_E, user, session)
    assert result.status is IngestStatus.NEEDS_CLARIFICATION
    assert result.materialization is None
    with open_sqlite_uow(db_path) as uow:
        assert uow.entities.all_for_user("u1") == []


def test_query_ir_unsupported(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    raw = "Quanto gastei com o Corolla este mês?"
    query = QueryIR(raw_input=raw, query=QuerySpec())
    result = _service(db_path, ontology, {raw: query}).ingest(raw, user, _session())
    assert result.status is IngestStatus.UNSUPPORTED


def test_approved_knowledge_rejects_bypass(ontology: OntologyRegistry) -> None:
    from pke.reasoning import KnowledgeAssessor, KnowledgeCandidate
    from pke.resolution import InMemoryEntityLookup

    candidate = KnowledgeCandidate(user_id="u1", ir=ir_negative())
    assessment = KnowledgeAssessor(ontology, InMemoryEntityLookup()).assess(candidate)
    assert assessment.persistable is False
    with pytest.raises(MaterializationDenied):
        ApprovedKnowledge.certify(candidate, assessment, NOW)
    with pytest.raises(MaterializationDenied):
        ApprovedKnowledge(candidate, assessment, NOW)


def test_materializer_does_not_import_interpreter() -> None:
    root = Path(__file__).parents[2] / "src" / "pke" / "application" / "materializer.py"
    text = root.read_text(encoding="utf-8")
    assert "FakeInterpreter" not in text
    assert "from pke.interpretation.interpreter" not in text


def test_persist_does_not_import_application() -> None:
    root = Path(__file__).parents[2] / "src" / "pke" / "persist"
    for path in root.rglob("*.py"):
        assert "pke.application" not in path.read_text(encoding="utf-8")


def test_reasoning_does_not_import_persist() -> None:
    root = Path(__file__).parents[2] / "src" / "pke" / "reasoning"
    for path in root.rglob("*.py"):
        assert "pke.persist" not in path.read_text(encoding="utf-8")


def test_application_does_not_call_wall_clock() -> None:
    root = Path(__file__).parents[2] / "src" / "pke" / "application"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "dt.datetime.now" not in text
        assert "datetime.utcnow" not in text
        assert "datetime.now(" not in text
