"""Integração I11.4 / I11.4.1 — State dimension/value."""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Any
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
    Entity,
    OccurrenceStatus,
    RelationToReference,
    State,
    TemporalKnowledge,
    TimePrecision,
    TimeValue,
    UserContext,
    new_ulid,
)
from pke.interpretation import (
    EntityMention,
    FakeInterpreter,
    IngestIntent,
    IngestIR,
    IrState,
    IrTime,
    QueryIR,
    QuerySpec,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.query.engine import QueryEngine
from pke.query.results import TemporalCompleteness
from pke.query.spec import EntityAssociation, ResolvedQuerySpec
from pke.resolution import PersonalContext

from tests.integration.test_ask import _ask, _ingest
from tests.integration.test_ingest import NOW, _corolla, _service

FORTALEZA = ZoneInfo("America/Fortaleza")


def _present_time() -> IrTime:
    return IrTime(
        original_text="",
        occurrence_status=OccurrenceStatus.ONGOING,
        relation_to_reference=RelationToReference.DURING,
        tense_evidence="present",
    )


def _mention(text: str, *, type_key: str) -> EntityMention:
    return EntityMention(
        text=text,
        type_hint=ConceptRef(key=type_key),
        role=ConceptRef(key="role.subject"),
    )


def _state_ir(
    raw: str,
    *,
    entity: EntityMention,
    value_key: str,
    payload: Any | None = None,
    domains: list[ConceptRef] | None = None,
) -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_STATE,
        raw_input=raw,
        domains=domains or [],
        entities_mentioned=[entity],
        state=IrState(
            value=ConceptRef(key=value_key),
            payload=payload,
            time=_present_time(),
        ),
    )


def _state_query(
    raw: str,
    *,
    entity: EntityMention,
    value_key: str,
) -> QueryIR:
    return QueryIR(
        raw_input=raw,
        query=QuerySpec(
            intent="state",
            entities=[entity],
            entity_association="subject",
            state_values=[ConceptRef(key=value_key)],
        ),
    )


def _session() -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id="u1"))


def _user() -> UserContext:
    return UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)


def _counts(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(db_path)
    try:
        return {
            "events": con.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "states": con.execute("SELECT COUNT(*) FROM states").fetchone()[0],
        }
    finally:
        con.close()


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "state.db"


RAW_S1 = "A geladeira está quebrada."
RAW_S2 = "O remédio acabou."
RAW_S3 = "A conta de luz está atrasada."
RAW_S4 = "A porta está aberta."
RAW_S5 = "Minha CNH está vencida."
RAW_S6 = "O Corolla está com 84.500 km."
RAW_SHOP_002 = "Acabou detergente."
RAW_TRANSITION_1 = "A geladeira está quebrada."
RAW_TRANSITION_2 = "Agora ela está funcionando."


def test_s1_broken_appliance_no_causal_event(db_path: Path, ontology: OntologyRegistry) -> None:
    fridge = _mention("geladeira", type_key="entity.appliance")
    ir = _state_ir(RAW_S1, entity=fridge, value_key="state.value.broken")
    result = _service(db_path, ontology, {RAW_S1: ir}).ingest(RAW_S1, _user(), _session())
    assert result.status is IngestStatus.COMMITTED
    counts = _counts(db_path)
    assert counts["states"] == 1
    assert counts["events"] == 0
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    assert graph.states[0].value_key == "state.value.broken"
    assert graph.states[0].dimension_key == "state.operational_condition"


def test_s2_depleted_medication(db_path: Path, ontology: OntologyRegistry) -> None:
    med = _mention("remédio", type_key="entity.medication")
    ir = _state_ir(RAW_S2, entity=med, value_key="state.value.depleted")
    assert _service(db_path, ontology, {RAW_S2: ir}).ingest(RAW_S2, _user(), _session()).status is IngestStatus.COMMITTED
    assert _counts(db_path)["events"] == 0


def test_s3_overdue_bill_not_unpaid(db_path: Path, ontology: OntologyRegistry) -> None:
    bill = _mention("conta de luz", type_key="entity.home")
    ir = _state_ir(RAW_S3, entity=bill, value_key="state.value.overdue")
    result = _service(db_path, ontology, {RAW_S3: ir}).ingest(RAW_S3, _user(), _session())
    assert result.status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    assert graph.states[0].value_key == "state.value.overdue"
    assert graph.states[0].dimension_key == "state.due_status"


def test_s4_open_door(db_path: Path, ontology: OntologyRegistry) -> None:
    door = _mention("porta", type_key="entity.home")
    ir = _state_ir(RAW_S4, entity=door, value_key="state.value.open")
    assert _service(db_path, ontology, {RAW_S4: ir}).ingest(RAW_S4, _user(), _session()).status is IngestStatus.COMMITTED


def test_s5_expired_document(db_path: Path, ontology: OntologyRegistry) -> None:
    doc = _mention("CNH", type_key="entity.document")
    ir = _state_ir(RAW_S5, entity=doc, value_key="state.value.expired")
    assert _service(db_path, ontology, {RAW_S5: ir}).ingest(RAW_S5, _user(), _session()).status is IngestStatus.COMMITTED


def test_s6_quantitative_state_provisional(db_path: Path, ontology: OntologyRegistry) -> None:
    car = _corolla()
    ir = _state_ir(
        RAW_S6,
        entity=car,
        value_key="state.value.quantity_observation",
        payload={"amount": 84500, "unit": "km"},
    )
    result = _service(db_path, ontology, {RAW_S6: ir}).ingest(RAW_S6, _user(), _session())
    assert result.status is IngestStatus.COMMITTED
    state = open_sqlite_read_store(db_path).load_user_graph("u1").states[0]
    assert state.dimension_key == "state.observed_quantity"
    assert state.payload == {"amount": 84500, "unit": "km"}


def test_transition_broken_to_working_same_dimension(
    db_path: Path, ontology: OntologyRegistry
) -> None:
    fridge = _mention("geladeira", type_key="entity.appliance")
    broken = _state_ir(RAW_TRANSITION_1, entity=fridge, value_key="state.value.broken")
    working = _state_ir(RAW_TRANSITION_2, entity=fridge, value_key="state.value.working")
    service = _service(db_path, ontology, {RAW_TRANSITION_1: broken, RAW_TRANSITION_2: working})
    session, user = _session(), _user()
    assert service.ingest(RAW_TRANSITION_1, user, session).status is IngestStatus.COMMITTED
    assert service.ingest(RAW_TRANSITION_2, user, session).status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    assert len(graph.states) == 2
    broken_state = next(s for s in graph.states if s.value_key == "state.value.broken")
    working_state = next(s for s in graph.states if s.value_key == "state.value.working")
    assert broken_state.dimension_key == working_state.dimension_key == "state.operational_condition"
    assert broken_state.is_current is False
    assert working_state.is_current is True
    assert working_state.supersedes_id == broken_state.id


def test_independent_dimensions_both_current(db_path: Path, ontology: OntologyRegistry) -> None:
    fridge = _mention("geladeira", type_key="entity.appliance")
    service = _service(
        db_path,
        ontology,
        {
            "working": _state_ir("funcionando", entity=fridge, value_key="state.value.working"),
            "open": _state_ir("aberta", entity=fridge, value_key="state.value.open"),
        },
    )
    session, user = _session(), _user()
    assert service.ingest("working", user, session).status is IngestStatus.COMMITTED
    assert service.ingest("open", user, session).status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    current = [s for s in graph.states if s.is_current]
    assert len(current) == 2
    dims = {s.dimension_key for s in current}
    assert dims == {"state.operational_condition", "state.openness"}


def test_partial_ordering_current_state_indeterminate(
    db_path: Path, ontology: OntologyRegistry
) -> None:
    entity_id = new_ulid()
    with open_sqlite_uow(db_path) as uow:
        uow.entities.add(
            Entity(
                id=entity_id,
                user_id="u1",
                type_id=core_concept_id("entity.appliance"),
                canonical_name="geladeira",
                created_at=NOW,
            )
        )
        known = State(
            id=new_ulid(),
            user_id="u1",
            entity_id=entity_id,
            dimension_id=core_concept_id("state.operational_condition"),
            dimension_key="state.operational_condition",
            value_concept_id=core_concept_id("state.value.broken"),
            value_key="state.value.broken",
            temporal=TemporalKnowledge.from_calendar(
                TimeValue(
                    original_text="2026-09-01",
                    date=dt.date(2026, 9, 1),
                    precision=TimePrecision.DAY,
                )
            ),
            observed_at=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
            is_current=True,
        )
        unknown = State(
            id=new_ulid(),
            user_id="u1",
            entity_id=entity_id,
            dimension_id=core_concept_id("state.operational_condition"),
            dimension_key="state.operational_condition",
            value_concept_id=core_concept_id("state.value.working"),
            value_key="state.value.working",
            temporal=TemporalKnowledge.partial_ongoing(),
            observed_at=dt.datetime(2026, 9, 2, tzinfo=FORTALEZA),
            is_current=True,
        )
        uow.states.add(known)
        uow.states.add(unknown)
        uow.commit()
    result = QueryEngine(open_sqlite_read_store(db_path), ontology).execute(
        ResolvedQuerySpec(
            user_id="u1",
            entity_ids=[entity_id],
            entity_association=EntityAssociation.SUBJECT,
            state_dimension_ids=[core_concept_id("state.operational_condition")],
        )
    )
    assert result.temporal_completeness is TemporalCompleteness.PARTIAL
    assert result.indeterminate_state_count == 1


def test_state_query_broken_fridge(db_path: Path, ontology: OntologyRegistry) -> None:
    fridge = _mention("geladeira", type_key="entity.appliance")
    ingest_ir = _state_ir(RAW_S1, entity=fridge, value_key="state.value.broken")
    query_raw = "A geladeira está quebrada?"
    query_ir = _state_query(query_raw, entity=fridge, value_key="state.value.broken")
    ingest = _ingest(db_path, ontology, {RAW_S1: ingest_ir})
    ask = _ask(db_path, ontology, {query_raw: query_ir})
    user, session = _user(), _session()
    assert ingest.ingest(RAW_S1, user, session).status is IngestStatus.COMMITTED
    answer = ask.ask(query_raw, user, session)
    assert answer.status is AskStatus.ANSWERED
    assert answer.query_result is not None
    assert answer.query_result.matched_count == 1
    assert answer.query_result.state_value_key == "state.value.broken"


def test_shop_002_depletion_state_commits(db_path: Path, ontology: OntologyRegistry) -> None:
    product = _mention("detergente", type_key="entity.home")
    ir = _state_ir(RAW_SHOP_002, entity=product, value_key="state.value.depleted")
    result = _service(db_path, ontology, {RAW_SHOP_002: ir}).ingest(RAW_SHOP_002, _user(), _session())
    assert result.status is IngestStatus.COMMITTED
    assert _counts(db_path)["states"] == 1
    assert _counts(db_path)["events"] == 0
