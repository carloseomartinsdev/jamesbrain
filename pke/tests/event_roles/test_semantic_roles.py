"""I11.10 — Event semantic roles & participant representation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application import AskStatus, FixedClock, IngestService, IngestStatus, SessionContext
from pke.domain import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.event_roles import (
    false_role_assignments,
    resolve_event_roles,
    role_preservation_audit,
)
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.resolver import resolve_concepts
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from tests.event_roles import fixtures as rf
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ask import _session as ingest_session
from tests.integration.test_ingest import NOW
from tests.query_semantic import fixtures as qf
from tests.query_semantic.test_compositional_query import _run_query, _semantic_service, _to_ir, _user
from tests.semantic_resolution.fixtures import ls1_installed_ac, pr6_door_opened

pytestmark = pytest.mark.usefixtures("_catalog")


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _wire_roles(proposal: SemanticProposal) -> dict[str, str | None]:
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, outcome.failure_stage
    roles: dict[str, str | None] = {}
    for mention in outcome.ir.entities_mentioned:
        roles[mention.text] = mention.role.key if mention.role else None
    if outcome.ir.event:
        for mention in outcome.ir.event.participants:
            roles[mention.text] = mention.role.key if mention.role else None
    return roles


def _persisted_ids(db: Path, proposal: SemanticProposal) -> tuple[str | None, str | None]:
    user = _user()
    session = ingest_session()
    svc = _semantic_service(db, {proposal.raw_input: proposal})
    assert svc.ingest(proposal.raw_input, user, session).status is IngestStatus.COMMITTED
    store = open_sqlite_read_store(db)
    graph = store.load_user_graph(user.user_id)
    assert len(graph.events) == 1
    ev = graph.events[0]
    return ev.actor_id, ev.subject_id


def _entity_name_map(db: Path, user_id: str) -> dict[str, str]:
    store = open_sqlite_read_store(db)
    graph = store.load_user_graph(user_id)
    return {entity.canonical_name: entity.id for entity in graph.entities.values()}


# --- ER matrix (audit) ---


@pytest.mark.parametrize(
    ("fixture", "actor", "obj", "context", "implicit"),
    [
        (rf.er1_replace_clutch_corolla_implicit, None, "embreagem", ("Corolla",), True),
        (rf.er2_mechanic_replace_clutch_corolla, "mecânico", "embreagem", ("Corolla",), False),
        (rf.er3_joao_open_door, "João", "porta", (), False),
        (rf.er4_door_opened_intransitive, None, None, (), False),
        (rf.er5_technician_install_ac_bedroom, "técnico", "ar-condicionado", ("quarto",), False),
        (rf.er6_brought_corolla_workshop, None, "Corolla", ("oficina",), True),
    ],
)
def test_er_semantic_roles(fixture, actor, obj, context, implicit) -> None:
    roles = resolve_event_roles(fixture())
    assert (roles.actor.text if roles.actor else None) == actor
    assert (roles.object.text if roles.object else None) == obj
    assert tuple(c.text for c in roles.context) == context
    assert roles.actor_implicit is implicit
    assert false_role_assignments(roles) == []


# --- RT1–RT6 ---


def test_rt1_explicit_actor_not_context() -> None:
    roles = resolve_event_roles(rf.er2_mechanic_replace_clutch_corolla())
    assert roles.actor is not None and roles.actor.text == "mecânico"
    assert all(c.text != "mecânico" for c in roles.context)
    wire = _wire_roles(rf.er2_mechanic_replace_clutch_corolla())
    assert wire.get("mecânico") == "role.actor"
    assert wire.get("Corolla") == "role.context"
    assert false_role_assignments(roles) == []


def test_rt2_object_not_context() -> None:
    roles = resolve_event_roles(rf.er1_replace_clutch_corolla_implicit())
    assert roles.object is not None and roles.object.text == "embreagem"
    assert any(c.text == "Corolla" for c in roles.context)
    wire = _wire_roles(rf.er1_replace_clutch_corolla_implicit())
    assert wire.get("embreagem") == "role.object"
    assert wire.get("Corolla") == "role.context"
    assert false_role_assignments(roles) == []


def test_rt3_no_actor_invention_intransitive() -> None:
    roles = resolve_event_roles(pr6_door_opened())
    assert roles.actor is None
    assert roles.actor_implicit is False
    assert roles.affected is not None and roles.affected.text == "porta"
    assert false_role_assignments(roles) == []


def test_rt4_explicit_actor_preserved() -> None:
    roles = resolve_event_roles(rf.er3_joao_open_door())
    assert roles.actor is not None and roles.actor.text == "João"
    wire = _wire_roles(rf.er3_joao_open_door())
    assert wire.get("João") == "role.actor"
    assert false_role_assignments(roles) == []


def test_rt5_context_not_action_performer() -> None:
    roles = resolve_event_roles(rf.er1_replace_clutch_corolla_implicit())
    assert roles.actor is None
    assert roles.actor_implicit is True
    assert any(c.text == "Corolla" for c in roles.context)
    assert false_role_assignments(roles) == []


def test_rt6_install_not_replace() -> None:
    result = resolve_proposal(ls1_installed_ac())
    concepts = resolve_concepts(result.proposal, result.primitive)
    assert concepts.action == "action.install"
    assert concepts.action != "action.replace"
    roles = resolve_event_roles(ls1_installed_ac())
    assert roles.actor is not None and roles.actor.text == "técnico"
    assert false_role_assignments(roles) == []


# --- metrics ---


def test_semantic_role_preservation_metric() -> None:
    audit = role_preservation_audit(resolve_event_roles(rf.er1_replace_clutch_corolla_implicit()))
    assert audit["actor"] == "implicit_known"
    assert audit["object"] == "preserved"
    assert audit["context"] == "preserved"


def test_false_role_assignment_zero_matrix() -> None:
    cases = [
        rf.er1_replace_clutch_corolla_implicit(),
        rf.er2_mechanic_replace_clutch_corolla(),
        rf.er3_joao_open_door(),
        pr6_door_opened(),
        rf.er5_technician_install_ac_bedroom(),
        ls1_installed_ac(),
    ]
    total = sum(len(false_role_assignments(resolve_event_roles(p))) for p in cases)
    assert total == 0


# --- storage mapping (v7 participants + legacy projection) ---


def test_v7_implicit_actor_context_not_in_actor_slot(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "v7_ctx.db")
    proposal = rf.er1_replace_clutch_corolla_implicit()
    user = _user()
    actor_id, subject_id = _persisted_ids(db, proposal)
    assert actor_id is None
    assert subject_id is not None
    roles = resolve_event_roles(proposal)
    assert roles.actor is None
    assert roles.actor_implicit is True
    entities = _entity_name_map(db, user.user_id)
    assert entities["embreagem"] == subject_id
    graph = open_sqlite_read_store(db).load_user_graph(user.user_id)
    parts = {(p.role, graph.entities[p.entity_id].canonical_name) for p in graph.events[0].participants}
    assert ("role.object", "embreagem") in parts
    assert ("role.context", "Corolla") in parts


def test_v7_explicit_actor_and_context_persisted(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "v7_actor.db")
    proposal = rf.er2_mechanic_replace_clutch_corolla()
    user = _user()
    actor_id, subject_id = _persisted_ids(db, proposal)
    entities = _entity_name_map(db, user.user_id)
    assert entities["mecânico"] == actor_id
    assert entities["embreagem"] == subject_id
    assert actor_id != entities.get("Corolla")
    graph = open_sqlite_read_store(db).load_user_graph(user.user_id)
    parts = {(p.role, graph.entities[p.entity_id].canonical_name) for p in graph.events[0].participants}
    assert ("role.actor", "mecânico") in parts
    assert ("role.object", "embreagem") in parts
    assert ("role.context", "Corolla") in parts


# --- query regression (I11.9 discrimination) ---


def test_query_oil_vs_clutch(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "q_oil.db")
    result = _run_query(db, {qf.ingest_replace_oil_corolla().raw_input: qf.ingest_replace_oil_corolla()}, qf.query_replace_clutch_corolla())
    assert result.status is AskStatus.NO_RESULTS


def test_query_civic_vs_corolla(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "q_civic.db")
    ingest = qf.ingest_replace_clutch_corolla()
    other = SemanticProposal(
        raw_input="Troquei a embreagem do Civic.",
        object=SemanticEntityMention(text="embreagem", kind_hint="vehicle"),
        entities_mentioned=[SemanticEntityMention(text="Civic", kind_hint="vehicle")],
        action_expression="troquei a embreagem",
        change_semantics=True,
        event_expression="troquei a embreagem do Civic",
        primitive_hint="event",
        temporal=qf.ingest_replace_clutch_corolla().temporal,
    )
    user = _user()
    session = ingest_session()
    svc = _semantic_service(db, {ingest.raw_input: ingest, other.raw_input: other})
    assert svc.ingest(ingest.raw_input, user, session).status is IngestStatus.COMMITTED
    assert svc.ingest(other.raw_input, user, session).status is IngestStatus.COMMITTED
    from pke.application import AskService

    ask = AskService(
        FakeInterpreter({_to_ir(qf.query_replace_clutch_corolla()).raw_input: _to_ir(qf.query_replace_clutch_corolla())}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    result = ask.ask(qf.query_replace_clutch_corolla().raw_input, user, session)
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.matched_count == 1


def test_query_same_clutch_corolla_match(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "q_match.db")
    result = _run_query(
        db,
        {qf.ingest_replace_clutch_corolla().raw_input: qf.ingest_replace_clutch_corolla()},
        qf.query_replace_clutch_corolla(),
    )
    assert result.status is AskStatus.ANSWERED
