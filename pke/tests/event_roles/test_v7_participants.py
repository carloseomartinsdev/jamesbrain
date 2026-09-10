"""I11.10.3 — EventParticipant storage v7 migration + ingest/query cutover."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from pke.application import AskStatus, IngestStatus
from pke.ontology.seeds import core_concept_id
from pke.persist.migrations.errors import MigrationFailed, UnsupportedSchemaVersion
from pke.persist.migrations.runner import (
    MigrationStep,
    read_schema_version,
    schemas_structurally_equal,
    upgrade_to_current,
)
from pke.persist.migrations.v6_to_v7 import (
    classify_legacy_actor_role,
    classify_legacy_subject_role,
)
from pke.persist.sqlite.engine import create_sqlite_engine, init_database, sqlite_url
from pke.persist.sqlite.read_store import open_sqlite_read_store
from tests.event_roles import fixtures as rf
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ask import _session as ingest_session
from tests.persist_migrations.test_canonical_runner import (
    _minimal_v6,
    _seed_knowledge,
    _stamp,
)
from tests.query_semantic import fixtures as qf
from tests.query_semantic.test_compositional_query import _run_query, _semantic_service, _user
from tests.semantic_resolution.fixtures import pr6_door_opened
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry

pytestmark = pytest.mark.usefixtures("_catalog")


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _parts_by_name(db: Path, user_id: str = "u1") -> set[tuple[str, str]]:
    graph = open_sqlite_read_store(db).load_user_graph(user_id)
    assert len(graph.events) == 1
    names = {e.id: e.canonical_name for e in graph.entities.values()}
    return {(p.role, names[p.entity_id]) for p in graph.events[0].participants}


def _ingest(db: Path, proposal):
    user = _user()
    session = ingest_session()
    svc = _semantic_service(db, {proposal.raw_input: proposal})
    assert svc.ingest(proposal.raw_input, user, session).status is IngestStatus.COMMITTED
    return user


# --- classification: EntityKind ≠ SemanticRole ---


def test_legacy_classifier_never_promotes_kind_to_role() -> None:
    for tid in (
        core_concept_id("entity.person"),
        core_concept_id("entity.organization"),
        core_concept_id("entity.automobile"),
        core_concept_id("entity.place"),
        core_concept_id("entity.document"),
        None,
    ):
        assert classify_legacy_actor_role(tid) == "role.unspecified"
        assert classify_legacy_subject_role(tid) == "role.unspecified"


# --- L1–L8 legacy migration ---


def _legacy_event(
    eng,
    *,
    entity_id: str,
    type_key: str,
    name: str,
    as_actor: bool = True,
    as_subject: bool = False,
    event_id: str = "ev1",
) -> None:
    now = "2026-09-01T12:00:00+00:00"
    with eng.begin() as conn:
        if conn.execute(text("SELECT COUNT(*) FROM users WHERE id='u1'")).scalar() == 0:
            conn.execute(
                text("INSERT INTO users (id, created_at) VALUES ('u1', :at)"), {"at": now}
            )
            conn.execute(
                text(
                    "INSERT INTO raw_inputs (id, user_id, text, created_at) "
                    "VALUES ('r1', 'u1', 'x', :at)"
                ),
                {"at": now},
            )
        conn.execute(
            text(
                "INSERT INTO entities "
                "(id, user_id, type_id, canonical_name, normalized_canonical_name, created_at) "
                "VALUES (:id, 'u1', :t, :name, :norm, :at)"
            ),
            {
                "id": entity_id,
                "t": core_concept_id(type_key),
                "name": name,
                "norm": name.casefold(),
                "at": now,
            },
        )
        actor = entity_id if as_actor else None
        subject = entity_id if as_subject else None
        conn.execute(
            text(
                """
                INSERT INTO events (
                    id, user_id, type_id, status, raw_input_id, created_at,
                    time_original_text, time_precision, temporal_kind,
                    actor_id, subject_id
                ) VALUES (
                    :eid, 'u1', :type, 'completed', 'r1', :at, '', 'day', 'exact',
                    :actor, :subject
                )
                """
            ),
            {
                "eid": event_id,
                "type": core_concept_id("event.maintenance"),
                "at": now,
                "actor": actor,
                "subject": subject,
            },
        )


def test_l1_person_actor_id_unspecified(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "l1.db")
    _legacy_event(eng, entity_id="p1", type_key="entity.person", name="João")
    upgrade_to_current(eng)
    with eng.connect() as conn:
        role = conn.execute(
            text("SELECT role FROM event_participants WHERE entity_id='p1'")
        ).scalar()
    assert role == "role.unspecified"


def test_l2_vehicle_actor_id_unspecified(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "l2.db")
    _legacy_event(eng, entity_id="v1", type_key="entity.automobile", name="Corolla")
    upgrade_to_current(eng)
    with eng.connect() as conn:
        role = conn.execute(
            text("SELECT role FROM event_participants WHERE entity_id='v1'")
        ).scalar()
    assert role == "role.unspecified"


def test_l3_place_actor_id_unspecified(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "l3.db")
    _legacy_event(eng, entity_id="pl1", type_key="entity.place", name="Oficina")
    upgrade_to_current(eng)
    with eng.connect() as conn:
        assert (
            conn.execute(
                text("SELECT role FROM event_participants WHERE entity_id='pl1'")
            ).scalar()
            == "role.unspecified"
        )


def test_l4_org_actor_id_unspecified(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "l4.db")
    _legacy_event(eng, entity_id="o1", type_key="entity.organization", name="Acme")
    upgrade_to_current(eng)
    with eng.connect() as conn:
        assert (
            conn.execute(
                text("SELECT role FROM event_participants WHERE entity_id='o1'")
            ).scalar()
            == "role.unspecified"
        )


def test_l5_subject_id_unspecified(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "l5.db")
    _legacy_event(
        eng,
        entity_id="c1",
        type_key="entity.home",
        name="embreagem",
        as_actor=False,
        as_subject=True,
    )
    upgrade_to_current(eng)
    with eng.connect() as conn:
        assert (
            conn.execute(
                text("SELECT role FROM event_participants WHERE entity_id='c1'")
            ).scalar()
            == "role.unspecified"
        )


def test_l6_actor_and_subject_both_preserved(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "l6.db")
    ids = _seed_knowledge(eng)
    upgrade_to_current(eng)
    with eng.connect() as conn:
        rows = conn.execute(
            text("SELECT entity_id, role FROM event_participants WHERE event_id=:e"),
            {"e": ids["event"]},
        ).fetchall()
    by_entity = {r[0]: r[1] for r in rows}
    assert by_entity[ids["entity"]] == "role.unspecified"
    assert by_entity[ids["entity2"]] == "role.unspecified"
    assert len(rows) == 2


def test_l7_same_entity_actor_and_subject_no_duplicate(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "l7.db")
    _legacy_event(
        eng,
        entity_id="same",
        type_key="entity.person",
        name="X",
        as_actor=True,
        as_subject=True,
    )
    upgrade_to_current(eng)
    with eng.connect() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM event_participants WHERE event_id='ev1'")
        ).scalar()
        roles = [
            r[0]
            for r in conn.execute(
                text("SELECT role FROM event_participants WHERE event_id='ev1'")
            ).fetchall()
        ]
    assert n == 1
    assert roles == ["role.unspecified"]


def test_l8_unknown_kind_unspecified(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "l8.db")
    _legacy_event(eng, entity_id="d1", type_key="entity.document", name="Nota")
    upgrade_to_current(eng)
    with eng.connect() as conn:
        assert (
            conn.execute(
                text("SELECT role FROM event_participants WHERE entity_id='d1'")
            ).scalar()
            == "role.unspecified"
        )


def test_contrast_legacy_person_unspecified_vs_new_actor(tmp_path: Path) -> None:
    """Legacy person association ≠ new ResolvedEventRoles actor."""
    eng = _minimal_v6(tmp_path / "contrast.db")
    _legacy_event(eng, entity_id="leg", type_key="entity.person", name="MecânicoLeg")
    upgrade_to_current(eng)
    with eng.connect() as conn:
        legacy_role = conn.execute(
            text("SELECT role FROM event_participants WHERE entity_id='leg'")
        ).scalar()
    assert legacy_role == "role.unspecified"

    db = fresh_db_path(tmp_path, "contrast_new.db")
    _ingest(db, rf.er2_mechanic_replace_clutch_corolla())
    parts = _parts_by_name(db)
    assert ("role.actor", "mecânico") in parts


# --- remaining migration infrastructure ---


def test_v7_4_no_association_lost(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "v74.db")
    ids = _seed_knowledge(eng)
    upgrade_to_current(eng)
    with eng.connect() as conn:
        actor = conn.execute(
            text("SELECT actor_id FROM events WHERE id=:id"), {"id": ids["event"]}
        ).scalar()
        subject = conn.execute(
            text("SELECT subject_id FROM events WHERE id=:id"), {"id": ids["event"]}
        ).scalar()
        parts = {
            r[0]
            for r in conn.execute(
                text("SELECT entity_id FROM event_participants WHERE event_id=:e"),
                {"e": ids["event"]},
            ).fetchall()
        }
    assert actor in parts and subject in parts


def test_v7_5_repeat_migration_noop(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "v75.db")
    _seed_knowledge(eng)
    upgrade_to_current(eng)
    with eng.connect() as conn:
        n1 = conn.execute(text("SELECT COUNT(*) FROM event_participants")).scalar()
    assert upgrade_to_current(eng) == []
    with eng.connect() as conn:
        n2 = conn.execute(text("SELECT COUNT(*) FROM event_participants")).scalar()
    assert n1 == n2


def test_v7_6_failure_keeps_version_6(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "v76.db")

    def boom(_e) -> None:
        raise RuntimeError("fail")

    with pytest.raises(MigrationFailed):
        upgrade_to_current(eng, steps=(MigrationStep(6, 7, boom, "boom"),), target=7)
    assert read_schema_version(eng) == 6


def test_fresh_equals_migrated_v7(tmp_path: Path) -> None:
    fresh = create_sqlite_engine(sqlite_url(tmp_path / "fresh.db"))
    init_database(fresh)
    migrated = _minimal_v6(tmp_path / "mig.db")
    upgrade_to_current(migrated)
    assert schemas_structurally_equal(fresh, migrated)
    assert read_schema_version(fresh) == 11
    assert read_schema_version(migrated) == 11


def test_future_schema_fails(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "future.db"))
    init_database(eng)
    with eng.begin() as conn:
        _stamp(conn, "12")
    with pytest.raises(UnsupportedSchemaVersion):
        upgrade_to_current(eng)


# --- N1–N4 new-write roles (unchanged) ---


def test_n1_mechanic_clutch_corolla_all_roles(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "n1.db")
    _ingest(db, rf.er2_mechanic_replace_clutch_corolla())
    parts = _parts_by_name(db)
    assert ("role.actor", "mecânico") in parts
    assert ("role.object", "embreagem") in parts
    assert ("role.context", "Corolla") in parts
    assert len(parts) == 3


def test_n2_implicit_actor_no_fabricated_user(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "n2.db")
    _ingest(db, rf.er1_replace_clutch_corolla_implicit())
    parts = _parts_by_name(db)
    assert ("role.object", "embreagem") in parts
    assert ("role.context", "Corolla") in parts
    assert not any(r == "role.actor" for r, _ in parts)
    graph = open_sqlite_read_store(db).load_user_graph("u1")
    assert graph.events[0].actor_id is None


def test_n3_intransitive_door_patient(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "n3.db")
    _ingest(db, pr6_door_opened())
    parts = _parts_by_name(db)
    assert ("role.patient", "porta") in parts
    assert not any(r == "role.actor" for r, _ in parts)


def test_n4_joao_actor_preserved(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "n4.db")
    _ingest(db, rf.er3_joao_open_door())
    parts = _parts_by_name(db)
    assert ("role.actor", "João") in parts
    assert ("role.object", "porta") in parts


# --- query regressions ---


def test_q1_same_clutch_corolla_match(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "q1.db")
    result = _run_query(
        db,
        {qf.ingest_replace_clutch_corolla().raw_input: qf.ingest_replace_clutch_corolla()},
        qf.query_replace_clutch_corolla(),
    )
    assert result.status is AskStatus.ANSWERED


def test_q2_oil_vs_clutch(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "q2.db")
    result = _run_query(
        db,
        {qf.ingest_replace_oil_corolla().raw_input: qf.ingest_replace_oil_corolla()},
        qf.query_replace_clutch_corolla(),
    )
    assert result.status is AskStatus.NO_RESULTS


def test_q3_civic_vs_corolla(tmp_path: Path) -> None:
    from pke.application import AskService, FixedClock
    from pke.interpretation import FakeInterpreter
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal
    from tests.integration.test_ingest import NOW
    from tests.query_semantic.test_compositional_query import _to_ir

    db = fresh_db_path(tmp_path, "q3.db")
    ingest = qf.ingest_replace_clutch_corolla()
    other = SemanticProposal(
        raw_input="Troquei a embreagem do Civic.",
        object=SemanticEntityMention(text="embreagem", kind_hint="vehicle"),
        entities_mentioned=[SemanticEntityMention(text="Civic", kind_hint="vehicle")],
        action_expression="troquei a embreagem",
        change_semantics=True,
        event_expression="troquei a embreagem do Civic",
        primitive_hint="event",
        temporal=ingest.temporal,
    )
    user = _user()
    session = ingest_session()
    svc = _semantic_service(db, {ingest.raw_input: ingest, other.raw_input: other})
    assert svc.ingest(ingest.raw_input, user, session).status is IngestStatus.COMMITTED
    assert svc.ingest(other.raw_input, user, session).status is IngestStatus.COMMITTED
    ask = AskService(
        FakeInterpreter(
            {qf.query_replace_clutch_corolla().raw_input: _to_ir(qf.query_replace_clutch_corolla())}
        ),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    result = ask.ask(qf.query_replace_clutch_corolla().raw_input, user, session)
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.matched_count == 1


def test_generic_query_matches_unspecified_participant(tmp_path: Path) -> None:
    """EVENT_CONTEXT uses entity association, not role."""
    from pke.domain.events import Event
    from pke.domain.event_participants import EventParticipant
    from pke.domain.temporal_knowledge import TemporalKnowledge
    from pke.domain.value_objects import EventStatus, TimePrecision, TimeValue
    from pke.persist.snapshot import UserKnowledgeSnapshot
    from pke.query.engine import QueryEngine
    from pke.query.spec import EntityAssociation, ResolvedQuerySpec
    import datetime as dt

    participant = EventParticipant(
        id="p1", event_id="e1", entity_id="corolla", role="role.unspecified"
    )
    event = Event(
        id="e1",
        user_id="u1",
        type_id=core_concept_id("event.maintenance"),
        participants=[participant],
        temporal=TemporalKnowledge.from_calendar(
            TimeValue(original_text="", precision=TimePrecision.DAY)
        ),
        status=EventStatus.COMPLETED,
        raw_input_id="r1",
        created_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
    )
    graph = UserKnowledgeSnapshot(user_id="u1", events=[event])
    engine = QueryEngine.__new__(QueryEngine)
    spec = ResolvedQuerySpec(
        user_id="u1",
        entity_ids=["corolla"],
        entity_association=EntityAssociation.EVENT_CONTEXT,
    )
    assert engine._entity_match(event, spec, graph) is True


def test_unspecified_does_not_satisfy_actor_predicate() -> None:
    from pke.domain.events import Event
    from pke.domain.event_participants import EventParticipant
    from pke.domain.temporal_knowledge import TemporalKnowledge
    from pke.domain.value_objects import EventStatus, TimePrecision, TimeValue
    from pke.persist.snapshot import UserKnowledgeSnapshot
    from pke.query.engine import QueryEngine
    from pke.query.spec import EntityAssociation, ResolvedQuerySpec
    import datetime as dt

    participant = EventParticipant(
        id="p1", event_id="e1", entity_id="joao", role="role.unspecified"
    )
    event = Event(
        id="e1",
        user_id="u1",
        type_id=core_concept_id("event.maintenance"),
        participants=[participant],
        temporal=TemporalKnowledge.from_calendar(
            TimeValue(original_text="", precision=TimePrecision.DAY)
        ),
        status=EventStatus.COMPLETED,
        raw_input_id="r1",
        created_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
    )
    graph = UserKnowledgeSnapshot(user_id="u1", events=[event])
    engine = QueryEngine.__new__(QueryEngine)
    spec = ResolvedQuerySpec(
        user_id="u1",
        entity_ids=["joao"],
        entity_association=EntityAssociation.ACTOR,
    )
    assert engine._entity_match(event, spec, graph) is False
    assert event.participant_ids_for_role("role.actor") == set()


def test_q4_explicit_actor_context_still_queryable(tmp_path: Path) -> None:
    from pke.application import AskService, FixedClock
    from pke.interpretation import FakeInterpreter
    from tests.integration.test_ingest import NOW
    from tests.query_semantic.test_compositional_query import _to_ir

    db = fresh_db_path(tmp_path, "q4.db")
    _ingest(db, rf.er2_mechanic_replace_clutch_corolla())
    user = _user()
    session = ingest_session()
    ask = AskService(
        FakeInterpreter(
            {qf.query_replace_clutch_corolla().raw_input: _to_ir(qf.query_replace_clutch_corolla())}
        ),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    result = ask.ask(qf.query_replace_clutch_corolla().raw_input, user, session)
    assert result.status is AskStatus.ANSWERED


def test_role_sensitive_actor_vs_context_storage(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "role_disc.db")
    _ingest(db, rf.er2_mechanic_replace_clutch_corolla())
    graph = open_sqlite_read_store(db).load_user_graph("u1")
    ev = graph.events[0]
    actors = ev.participant_ids_for_role("role.actor")
    contexts = ev.participant_ids_for_role("role.context")
    assert actors and contexts
    assert actors.isdisjoint(contexts)


def test_event_delete_cascades_participants(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "cascade.db"))
    init_database(eng)
    ids = _seed_knowledge(eng)
    with eng.begin() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM event_participants WHERE event_id=:e"),
            {"e": ids["event"]},
        ).scalar()
        if n == 0:
            conn.execute(
                text(
                    "INSERT INTO event_participants (id, event_id, entity_id, role) "
                    "VALUES ('p1', :e, :ent, 'role.unspecified')"
                ),
                {"e": ids["event"], "ent": ids["entity"]},
            )
        conn.execute(text("DELETE FROM events WHERE id=:e"), {"e": ids["event"]})
        left = conn.execute(
            text("SELECT COUNT(*) FROM event_participants WHERE event_id=:e"),
            {"e": ids["event"]},
        ).scalar()
    assert left == 0
