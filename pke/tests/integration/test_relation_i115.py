"""Integração I11.5 — Relation evolution."""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
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
    Relation,
    RelationToReference,
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
    IrRelation,
    IrTime,
    QueryIR,
    QuerySpec,
    RelationAssertionMode,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.ontology.relation_metadata import RELATION_METADATA
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.query.engine import QueryEngine
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


def _past_time() -> IrTime:
    return IrTime(
        original_text="",
        occurrence_status=OccurrenceStatus.HAPPENED,
        relation_to_reference=RelationToReference.BEFORE,
        tense_evidence="past",
    )


def _mention(text: str, *, type_key: str, role: str = "role.subject") -> EntityMention:
    return EntityMention(
        text=text,
        type_hint=ConceptRef(key=type_key),
        role=ConceptRef(key=role),
    )


def _relation_ir(
    raw: str,
    *,
    subject: EntityMention,
    object: EntityMention,
    relation_key: str,
    mode: RelationAssertionMode = RelationAssertionMode.ASSERT,
    time: IrTime | None = None,
) -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_RELATION,
        raw_input=raw,
        relation=IrRelation(
            type=ConceptRef(key=relation_key),
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


def _counts(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(db_path)
    try:
        return {
            "events": con.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "states": con.execute("SELECT COUNT(*) FROM states").fetchone()[0],
            "relations": con.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
        }
    finally:
        con.close()


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "relation.db"


RAW_R1 = "João trabalha na Acme."
RAW_R2 = "Eu moro em Fortaleza."
RAW_R3 = "O Corolla é meu."
RAW_R4 = "Ana é casada com João."
RAW_R5 = "Maria é mãe de João."
RAW_R6 = "Dr. Pedro é meu cardiologista."
RAW_EVOL_START = "João trabalha na Acme."
RAW_EVOL_END = "João não trabalha mais na Acme."
RAW_NEW_EMPLOYER_1 = "João trabalhava na Acme."
RAW_NEW_EMPLOYER_2 = "Agora trabalha na Beta."
RAW_CONCURRENT = "João também consulta para Beta."


def test_r1_employment_relation_only(db_path: Path, ontology: OntologyRegistry) -> None:
    joao = _mention("João", type_key="entity.person")
    acme = _mention("Acme", type_key="entity.organization")
    ir = _relation_ir(
        RAW_R1,
        subject=joao,
        object=acme,
        relation_key="relation.employed_by",
    )
    result = _service(db_path, ontology, {RAW_R1: ir}).ingest(RAW_R1, _user(), _session())
    assert result.status is IngestStatus.COMMITTED
    counts = _counts(db_path)
    assert counts["relations"] == 1
    assert counts["states"] == 0
    assert counts["events"] == 0
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    rel = graph.relations[0]
    assert rel.key == "relation.employed_by"
    assert rel.is_current is True


def test_r2_residence(db_path: Path, ontology: OntologyRegistry) -> None:
    ir = _relation_ir(
        RAW_R2,
        subject=_mention("eu", type_key="entity.person"),
        object=_mention("Fortaleza", type_key="entity.place"),
        relation_key="relation.resides_at",
    )
    assert _service(db_path, ontology, {RAW_R2: ir}).ingest(RAW_R2, _user(), _session()).status is IngestStatus.COMMITTED
    assert _counts(db_path)["events"] == 0


def test_r3_ownership_canonical_person_owns(db_path: Path, ontology: OntologyRegistry) -> None:
    corolla = _corolla()
    ir = _relation_ir(
        RAW_R3,
        subject=_mention("eu", type_key="entity.person"),
        object=corolla,
        relation_key="relation.owns",
    )
    assert _service(db_path, ontology, {RAW_R3: ir}).ingest(RAW_R3, _user(), _session()).status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    assert graph.relations[0].key == "relation.owns"


def test_r4_marriage_symmetric_storage(db_path: Path, ontology: OntologyRegistry) -> None:
    ana = _mention("Ana", type_key="entity.person")
    joao = _mention("João", type_key="entity.person")
    ir = _relation_ir(
        RAW_R4,
        subject=ana,
        object=joao,
        relation_key="relation.married_to",
    )
    assert _service(db_path, ontology, {RAW_R4: ir}).ingest(RAW_R4, _user(), _session()).status is IngestStatus.COMMITTED
    assert len(open_sqlite_read_store(db_path).load_user_graph("u1").relations) == 1


def test_r5_parent_relation(db_path: Path, ontology: OntologyRegistry) -> None:
    ir = _relation_ir(
        RAW_R5,
        subject=_mention("Maria", type_key="entity.person"),
        object=_mention("João", type_key="entity.person"),
        relation_key="relation.parent_of",
    )
    assert _service(db_path, ontology, {RAW_R5: ir}).ingest(RAW_R5, _user(), _session()).status is IngestStatus.COMMITTED


def test_r6_provider(db_path: Path, ontology: OntologyRegistry) -> None:
    ir = _relation_ir(
        RAW_R6,
        subject=_mention("Dr. Pedro", type_key="entity.person", role="role.provider"),
        object=_mention("eu", type_key="entity.person"),
        relation_key="relation.provider_for",
    )
    assert _service(db_path, ontology, {RAW_R6: ir}).ingest(RAW_R6, _user(), _session()).status is IngestStatus.COMMITTED


def test_evolution_termination_preserves_history(db_path: Path, ontology: OntologyRegistry) -> None:
    joao = _mention("João", type_key="entity.person")
    acme = _mention("Acme", type_key="entity.organization")
    start = _relation_ir(
        RAW_EVOL_START,
        subject=joao,
        object=acme,
        relation_key="relation.employed_by",
    )
    end = _relation_ir(
        RAW_EVOL_END,
        subject=joao,
        object=acme,
        relation_key="relation.employed_by",
        mode=RelationAssertionMode.TERMINATE,
    )
    service = _service(
        db_path,
        ontology,
        {RAW_EVOL_START: start, RAW_EVOL_END: end},
    )
    session, user = _session(), _user()
    assert service.ingest(RAW_EVOL_START, user, session).status is IngestStatus.COMMITTED
    assert service.ingest(RAW_EVOL_END, user, session).status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    assert len(graph.relations) == 1
    assert graph.relations[0].is_current is False
    assert graph.relations[0].valid_to is None
    assert graph.relations[0].termination_known is True
    assert graph.relations[0].termination_raw_input_id is not None
    assert graph.relations[0].raw_input_id != graph.relations[0].termination_raw_input_id


def test_new_employer_historical_and_current(db_path: Path, ontology: OntologyRegistry) -> None:
    joao = _mention("João", type_key="entity.person")
    acme = _mention("Acme", type_key="entity.organization")
    beta = _mention("Beta", type_key="entity.organization")
    service = _service(
        db_path,
        ontology,
        {
            RAW_NEW_EMPLOYER_1: _relation_ir(
                RAW_NEW_EMPLOYER_1,
                subject=joao,
                object=acme,
                relation_key="relation.employed_by",
                time=_past_time(),
                mode=RelationAssertionMode.HISTORICAL,
            ),
            RAW_NEW_EMPLOYER_2: _relation_ir(
                RAW_NEW_EMPLOYER_2,
                subject=joao,
                object=beta,
                relation_key="relation.employed_by",
            ),
        },
    )
    session, user = _session(), _user()
    assert service.ingest(RAW_NEW_EMPLOYER_1, user, session).status is IngestStatus.COMMITTED
    assert service.ingest(RAW_NEW_EMPLOYER_2, user, session).status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    assert len(graph.relations) == 2
    historical = [r for r in graph.relations if not r.is_current]
    current = [r for r in graph.relations if r.is_current]
    assert len(historical) == 1
    assert len(current) == 1


def test_concurrent_employments_both_current(db_path: Path, ontology: OntologyRegistry) -> None:
    joao = _mention("João", type_key="entity.person")
    acme = _mention("Acme", type_key="entity.organization")
    beta = _mention("Beta", type_key="entity.organization")
    service = _service(
        db_path,
        ontology,
        {
            "João trabalha na Acme.": _relation_ir(
                "João trabalha na Acme.",
                subject=joao,
                object=acme,
                relation_key="relation.employed_by",
            ),
            RAW_CONCURRENT: _relation_ir(
                RAW_CONCURRENT,
                subject=joao,
                object=beta,
                relation_key="relation.employed_by",
            ),
        },
    )
    session, user = _session(), _user()
    assert service.ingest("João trabalha na Acme.", user, session).status is IngestStatus.COMMITTED
    assert service.ingest(RAW_CONCURRENT, user, session).status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    assert len(graph.relations) == 2
    assert all(r.is_current for r in graph.relations)


def test_people_001_sentinel_employment(db_path: Path, ontology: OntologyRegistry) -> None:
    """PEOPLE_001 ingest-path: employment relation commits without State/Event."""
    raw = "João trabalha na Acme."
    ir = _relation_ir(
        raw,
        subject=_mention("João", type_key="entity.person"),
        object=_mention("Acme", type_key="entity.organization"),
        relation_key="relation.employed_by",
    )
    result = _service(db_path, ontology, {raw: ir}).ingest(raw, _user(), _session())
    assert result.status is IngestStatus.COMMITTED
    counts = _counts(db_path)
    assert counts == {"events": 0, "states": 0, "relations": 1}


def test_relation_query_where_and_boolean(db_path: Path, ontology: OntologyRegistry) -> None:
    joao = _mention("João", type_key="entity.person")
    acme = _mention("Acme", type_key="entity.organization")
    raw = "João trabalha na Acme."
    ir = _relation_ir(raw, subject=joao, object=acme, relation_key="relation.employed_by")
    service = _service(db_path, ontology, {raw: ir})
    session, user = _session(), _user()
    assert service.ingest(raw, user, session).status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    joao_id = next(e.id for e in graph.entities.values() if e.canonical_name == "João")
    acme_id = next(e.id for e in graph.entities.values() if e.canonical_name == "Acme")
    engine = QueryEngine(open_sqlite_read_store(db_path), ontology)
    from pke.query.spec import EntityAssociation, RelationScope, ResolvedQuerySpec

    where = engine.execute(
        ResolvedQuerySpec(
            user_id="u1",
            entity_ids=[joao_id],
            entity_association=EntityAssociation.RELATION_SUBJECT,
            relation_type_ids=[core_concept_id("relation.employed_by")],
            relation_scope=RelationScope.CURRENT,
        )
    )
    assert where.matched_count == 1
    assert where.current_relations[0].object_entity_id == acme_id
    boolean = engine.execute(
        ResolvedQuerySpec(
            user_id="u1",
            entity_ids=[joao_id, acme_id],
            entity_association=EntityAssociation.RELATION_SUBJECT,
            relation_type_ids=[core_concept_id("relation.employed_by")],
            relation_scope=RelationScope.CURRENT,
        )
    )
    assert boolean.relation_answer == "yes"


def test_symmetric_marriage_query(db_path: Path, ontology: OntologyRegistry) -> None:
    ana = _mention("Ana", type_key="entity.person")
    joao = _mention("João", type_key="entity.person")
    raw = RAW_R4
    service = _service(
        db_path,
        ontology,
        {raw: _relation_ir(raw, subject=ana, object=joao, relation_key="relation.married_to")},
    )
    session, user = _session(), _user()
    assert service.ingest(raw, user, session).status is IngestStatus.COMMITTED
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    ana_id = next(e.id for e in graph.entities.values() if e.canonical_name == "Ana")
    joao_id = next(e.id for e in graph.entities.values() if e.canonical_name == "João")
    from pke.query.relation_resolver import resolve_relation_query
    from pke.query.spec import RelationScope

    answer = resolve_relation_query(
        graph.relations,
        subject_id=joao_id,
        object_id=ana_id,
        concept_ids={core_concept_id("relation.married_to")},
        scope=RelationScope.CURRENT,
        boolean_check=True,
    )
    assert answer.answer == "yes"


def test_relation_metadata_contract() -> None:
    assert "relation.employed_by" in RELATION_METADATA
    assert RELATION_METADATA["relation.married_to"].symmetric is True
    assert RELATION_METADATA["relation.employed_by"].inverse == "relation.employs"
