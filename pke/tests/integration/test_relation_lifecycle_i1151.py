"""Integração I11.5.1 — Relation lifecycle & termination evidence."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pke.application import IngestStatus, SessionContext
from pke.domain import (
    ConceptRef,
    OccurrenceStatus,
    RelationToReference,
    TemporalGranularity,
    TemporalKind,
    TemporalKnowledge,
    TimePrecision,
    TimeValue,
    UserContext,
)
from pke.domain.relation_lifecycle import termination_calendar_known
from pke.interpretation import (
    EntityMention,
    IngestIntent,
    IngestIR,
    IrRelation,
    IrTime,
    QueryIR,
    QuerySpec,
    RelationAssertionMode,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist import open_sqlite_read_store
from pke.query.engine import QueryEngine
from pke.query.spec import EntityAssociation, RelationQueryKind, RelationScope, ResolvedQuerySpec, TimeRange
from pke.resolution import PersonalContext

from tests.integration.test_ingest import NOW, _service

FORTALEZA = ZoneInfo("America/Fortaleza")

RAW_LT1 = "João trabalha na Acme."
RAW_LT2 = "João não trabalha mais na Acme."
RAW_LT3 = "João saiu da Acme em 15/08/2026."
RAW_LT4 = "João saiu da Acme em agosto."
RAW_LT5 = "João já trabalhou na Acme?"
RAW_LT6 = "João trabalha na Acme?"
RAW_LT7 = "Quando João saiu da Acme?"
RAW_LT8 = "João trabalhava na Acme em agosto?"


def _present_time() -> IrTime:
    return IrTime(
        original_text="",
        occurrence_status=OccurrenceStatus.ONGOING,
        relation_to_reference=RelationToReference.DURING,
        tense_evidence="present",
    )


def _terminate_time() -> IrTime:
    return IrTime(
        original_text="",
        occurrence_status=OccurrenceStatus.HAPPENED,
        relation_to_reference=RelationToReference.BEFORE,
        tense_evidence="past",
    )


def _exact_date_time() -> IrTime:
    return IrTime(
        original_text="15/08/2026",
        instant=dt.datetime(2026, 8, 15, tzinfo=FORTALEZA),
        precision=TimePrecision.DAY,
        occurrence_status=OccurrenceStatus.HAPPENED,
        relation_to_reference=RelationToReference.BEFORE,
    )


def _partial_month_time() -> IrTime:
    return IrTime(
        original_text="agosto",
        partial_month=8,
        partial_year=2026,
        precision=TimePrecision.PARTIAL,
        occurrence_status=OccurrenceStatus.HAPPENED,
        relation_to_reference=RelationToReference.BEFORE,
    )


def _mention(text: str, *, type_key: str) -> EntityMention:
    return EntityMention(text=text, type_hint=ConceptRef(key=type_key))


def _relation_ir(
    raw: str,
    *,
    subject: EntityMention,
    object: EntityMention,
    mode: RelationAssertionMode = RelationAssertionMode.ASSERT,
    time: IrTime | None = None,
) -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_RELATION,
        raw_input=raw,
        relation=IrRelation(
            type=ConceptRef(key="relation.employed_by"),
            subject=subject,
            object=object,
            mode=mode,
            time=time or _present_time(),
        ),
    )


def _session() -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id="u1"))


def _user() -> UserContext:
    return UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)


def _employment_pair(
    db_path: Path,
    ontology: OntologyRegistry,
    *,
    end_raw: str,
    end_time: IrTime,
    end_mode: RelationAssertionMode = RelationAssertionMode.TERMINATE,
) -> tuple[str, str]:
    joao = _mention("João", type_key="entity.person")
    acme = _mention("Acme", type_key="entity.organization")
    service = _service(
        db_path,
        ontology,
        {
            RAW_LT1: _relation_ir(RAW_LT1, subject=joao, object=acme),
            end_raw: _relation_ir(
                end_raw,
                subject=joao,
                object=acme,
                mode=end_mode,
                time=end_time,
            ),
        },
    )
    session, user = _session(), _user()
    assert service.ingest(RAW_LT1, user, session).status is IngestStatus.COMMITTED
    assert service.ingest(end_raw, user, session).status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    rel = graph.relations[0]
    joao_id = next(e.id for e in graph.entities.values() if e.canonical_name == "João")
    acme_id = next(e.id for e in graph.entities.values() if e.canonical_name == "Acme")
    return joao_id, acme_id


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "lifecycle.db"


def test_lt1_current_assertion_no_invented_start(db_path: Path, ontology: OntologyRegistry) -> None:
    joao = _mention("João", type_key="entity.person")
    acme = _mention("Acme", type_key="entity.organization")
    result = _service(db_path, ontology, {RAW_LT1: _relation_ir(RAW_LT1, subject=joao, object=acme)}).ingest(
        RAW_LT1, _user(), _session()
    )
    assert result.status is IngestStatus.COMMITTED
    rel = open_sqlite_read_store(db_path).load_user_graph("u1").relations[0]
    assert rel.is_current is True
    assert rel.valid_from is None
    assert rel.termination_known is False


def test_lt2_termination_without_date(db_path: Path, ontology: OntologyRegistry) -> None:
    _employment_pair(db_path, ontology, end_raw=RAW_LT2, end_time=_terminate_time())
    rel = open_sqlite_read_store(db_path).load_user_graph("u1").relations[0]
    assert rel.is_current is False
    assert rel.termination_known is True
    assert rel.valid_to is None
    assert not termination_calendar_known(rel.termination_temporal)
    assert rel.termination_observed_at is not None
    assert rel.termination_raw_input_id != rel.raw_input_id


def test_lt3_exact_termination(db_path: Path, ontology: OntologyRegistry) -> None:
    _employment_pair(db_path, ontology, end_raw=RAW_LT3, end_time=_exact_date_time())
    rel = open_sqlite_read_store(db_path).load_user_graph("u1").relations[0]
    assert rel.valid_to is not None
    assert rel.valid_to.date() == dt.date(2026, 8, 15)
    assert termination_calendar_known(rel.termination_temporal)


def test_lt4_partial_termination_month(db_path: Path, ontology: OntologyRegistry) -> None:
    _employment_pair(db_path, ontology, end_raw=RAW_LT4, end_time=_partial_month_time())
    rel = open_sqlite_read_store(db_path).load_user_graph("u1").relations[0]
    assert rel.termination_known is True
    assert rel.valid_to is None
    assert rel.termination_temporal is not None


def test_lt5_historical_query_yes(db_path: Path, ontology: OntologyRegistry) -> None:
    joao_id, acme_id = _employment_pair(db_path, ontology, end_raw=RAW_LT2, end_time=_terminate_time())
    engine = QueryEngine(open_sqlite_read_store(db_path), ontology)
    result = engine.execute(
        ResolvedQuerySpec(
            user_id="u1",
            entity_ids=[joao_id, acme_id],
            relation_type_ids=[core_concept_id("relation.employed_by")],
            relation_query_kind=RelationQueryKind.HISTORICAL_EXISTENCE,
        )
    )
    assert result.relation_answer == "yes"


def test_lt6_current_query_no_after_termination(db_path: Path, ontology: OntologyRegistry) -> None:
    joao_id, acme_id = _employment_pair(db_path, ontology, end_raw=RAW_LT2, end_time=_terminate_time())
    engine = QueryEngine(open_sqlite_read_store(db_path), ontology)
    result = engine.execute(
        ResolvedQuerySpec(
            user_id="u1",
            entity_ids=[joao_id, acme_id],
            entity_association=EntityAssociation.RELATION_SUBJECT,
            relation_type_ids=[core_concept_id("relation.employed_by")],
            relation_scope=RelationScope.CURRENT,
        )
    )
    assert result.relation_answer == "no"


def test_lt7_termination_date_unknown(db_path: Path, ontology: OntologyRegistry) -> None:
    joao_id, acme_id = _employment_pair(db_path, ontology, end_raw=RAW_LT2, end_time=_terminate_time())
    engine = QueryEngine(open_sqlite_read_store(db_path), ontology)
    result = engine.execute(
        ResolvedQuerySpec(
            user_id="u1",
            entity_ids=[joao_id, acme_id],
            relation_type_ids=[core_concept_id("relation.employed_by")],
            relation_query_kind=RelationQueryKind.TERMINATION_DATE,
        )
    )
    assert result.relation_answer == "unknown"


def test_lt8_period_ambiguity_unknown(db_path: Path, ontology: OntologyRegistry) -> None:
    joao_id, acme_id = _employment_pair(db_path, ontology, end_raw=RAW_LT2, end_time=_terminate_time())
    engine = QueryEngine(open_sqlite_read_store(db_path), ontology)
    august = TimeRange(
        start=dt.datetime(2026, 8, 1, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
    )
    result = engine.execute(
        ResolvedQuerySpec(
            user_id="u1",
            entity_ids=[joao_id, acme_id],
            relation_type_ids=[core_concept_id("relation.employed_by")],
            relation_query_kind=RelationQueryKind.HELD_DURING,
            time_range=august,
        )
    )
    assert result.relation_answer == "unknown"


def test_provenance_assertion_vs_termination(db_path: Path, ontology: OntologyRegistry) -> None:
    joao = _mention("João", type_key="entity.person")
    acme = _mention("Acme", type_key="entity.organization")
    service = _service(
        db_path,
        ontology,
        {
            RAW_LT1: _relation_ir(RAW_LT1, subject=joao, object=acme),
            RAW_LT2: _relation_ir(
                RAW_LT2,
                subject=joao,
                object=acme,
                mode=RelationAssertionMode.TERMINATE,
                time=_terminate_time(),
            ),
        },
    )
    session, user = _session(), _user()
    assert service.ingest(RAW_LT1, user, session).status is IngestStatus.COMMITTED
    assert service.ingest(RAW_LT2, user, session).status is IngestStatus.COMMITTED
    rel = open_sqlite_read_store(db_path).load_user_graph("u1").relations[0]
    assert rel.raw_input_id is not None
    assert rel.termination_raw_input_id is not None
    assert rel.raw_input_id != rel.termination_raw_input_id
    assert rel.source is not None
    assert rel.termination_source is not None
    assert rel.source.raw_input_id == rel.raw_input_id
    assert rel.termination_source.raw_input_id == rel.termination_raw_input_id


def test_no_recorded_at_as_valid_to(db_path: Path, ontology: OntologyRegistry) -> None:
    _employment_pair(db_path, ontology, end_raw=RAW_LT2, end_time=_terminate_time())
    rel = open_sqlite_read_store(db_path).load_user_graph("u1").relations[0]
    assert rel.valid_to != rel.termination_observed_at
    assert rel.valid_to != rel.observed_at


def test_people_001_regression(db_path: Path, ontology: OntologyRegistry) -> None:
    joao = _mention("João", type_key="entity.person")
    acme = _mention("Acme", type_key="entity.organization")
    result = _service(
        db_path,
        ontology,
        {RAW_LT1: _relation_ir(RAW_LT1, subject=joao, object=acme)},
    ).ingest(RAW_LT1, _user(), _session())
    assert result.status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    assert len(graph.relations) == 1
    assert graph.relations[0].key == "relation.employed_by"
    assert len(graph.events) == 0
    assert len(graph.states) == 0
