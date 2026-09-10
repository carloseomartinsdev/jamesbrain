"""Learned relation types + CORE relation.likes — not Attribute invention."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.ask import AskService
from pke.application.ask_results import AskStatus
from pke.application.clock import FixedClock
from pke.application.ingest import IngestService
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.learned_relation import (
    learned_key_from_expression,
    slug_from_expression,
)
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.semantic.self_repair import apply_e1_self_repairs
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.ontology.learned import hydrate_learned_relation_types, learned_concept_id
from pke.ontology.seeds import core_concept_id
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.persist.sqlite.engine import create_sqlite_engine, sqlite_url
from pke.resolution.context import PersonalContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = "u-learn") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-learn") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _link(
    raw: str,
    *,
    expr: str,
    obj: str,
    obj_kind: str = "thing",
    utterance_kind: str = "assert",
) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        utterance_kind=utterance_kind,
        primitive_hint="relation",
        subject=SemanticEntityMention(
            text="eu", kind_hint="person", reference_kind="contextual", confidence=1.0
        ),
        object=SemanticEntityMention(
            text=obj, kind_hint=obj_kind, reference_kind="named", confidence=1.0
        ),
        relation_expression=expr,
        link_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )


def _ingest(proposal: SemanticProposal, db: Path, ontology: OntologyRegistry, user: UserContext):
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    svc = IngestService(
        FakeInterpreter({proposal.raw_input: outcome.ir}),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    return svc.ingest(proposal.raw_input, user, _session(user.user_id)), outcome


def test_slug_from_portuguese_expression() -> None:
    assert slug_from_expression("sou fã de") == "sou_fa_de"
    assert learned_key_from_expression("sou fã de") == "relation.learned.sou_fa_de"
    assert learned_key_from_expression("sou fã de") == learned_key_from_expression("sou fa de")


def test_likes_alias_not_preference_attribute() -> None:
    proposal = _link("eu gosto de café", expr="gosta de", obj="café")
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.attribute_expression in {None, ""}
    outcome = proposal_to_canonical_ir(repaired)
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.likes"
    assert outcome.ir.attribute is None


def test_fan_expression_maps_to_likes_not_learned() -> None:
    proposal = _link("sou fã de jazz", expr="sou fã de", obj="jazz")
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.likes"
    assert outcome.ir.relation.object.type_hint is not None
    assert outcome.ir.relation.object.type_hint.key == "entity.thing"


def test_unmatched_link_learns_extended_type() -> None:
    proposal = _link("sou tutor de jazz", expr="é tutor de", obj="jazz")
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.learned.e_tutor_de"
    assert outcome.ir.relation.object.type_hint is not None
    assert outcome.ir.relation.object.type_hint.key == "entity.thing"


def test_likes_ingest_and_query(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "likes.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    result, outcome = _ingest(
        _link("eu gosto de café", expr="gosta de", obj="café"), db, ontology, user
    )
    assert result.status is IngestStatus.COMMITTED, result.issues
    assert outcome.ir is not None and outcome.ir.relation is not None
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        rels = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.likes" and r.is_current
        ]
        assert len(rels) == 1
        coffee = uow.entities.get(user.user_id, rels[0].to_id)
        assert coffee is not None
        assert coffee.type_id == core_concept_id("entity.thing")
        assert coffee.canonical_name == "café"
        uow.commit()

    q = _link("eu gosto de café?", expr="gosta de", obj="café", utterance_kind="query")
    q_out = proposal_to_query_ir(q)
    assert q_out.query_ir is not None, (q_out.status, q_out.notes)
    ask = AskService(
        FakeInterpreter({q.raw_input: q_out.query_ir}),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    answered = ask.ask(q.raw_input, user, _session(user.user_id))
    assert answered.status is AskStatus.ANSWERED
    assert answered.query_result is not None
    assert answered.query_result.relation_answer == "yes"


def test_likes_open_query_is_inventory_not_boolean() -> None:
    proposal = SemanticProposal(
        raw_input="do que eu gosto?",
        utterance_kind="query",
        primitive_hint="unknown",
        subject=SemanticEntityMention(
            text="eu", kind_hint="person", reference_kind="contextual", confidence=1.0
        ),
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=0.9,
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.primitive_hint == "relation"
    assert repaired.link_semantics is True
    assert repaired.object is None
    outcome = proposal_to_query_ir(repaired)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    assert outcome.query_ir.query.intent == "relation"
    assert outcome.query_ir.query.relation_query_kind is None
    assert len(outcome.query_ir.query.entities) == 1
    assert outcome.query_ir.query.relation_types[0].key == "relation.likes"


def test_agosto_is_not_a_likes_inventory_query() -> None:
    proposal = SemanticProposal(
        raw_input="o que fiz em agosto?",
        utterance_kind="query",
        primitive_hint="unknown",
        temporal=SemanticTime(occurrence_aspect="happened"),
        confidence=0.9,
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.primitive_hint != "relation"
    assert repaired.link_semantics is False


def test_likes_inventory_ask_lists_objects(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "likes-inv.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    committed, _ = _ingest(
        _link("eu gosto de café", expr="gosta de", obj="café"), db, ontology, user
    )
    assert committed.status is IngestStatus.COMMITTED, committed.issues
    q = SemanticProposal(
        raw_input="do que eu gosto?",
        utterance_kind="query",
        primitive_hint="unknown",
        subject=SemanticEntityMention(
            text="eu", kind_hint="person", reference_kind="contextual", confidence=1.0
        ),
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=0.9,
    )
    q_out = proposal_to_query_ir(q)
    assert q_out.query_ir is not None, (q_out.status, q_out.notes)
    ask = AskService(
        FakeInterpreter({q.raw_input: q_out.query_ir}),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    answered = ask.ask(q.raw_input, user, _session(user.user_id))
    assert answered.status is AskStatus.ANSWERED
    assert answered.query_result is not None
    assert answered.query_result.relation_answer is None
    labels = [item.object_label for item in answered.query_result.current_relations]
    assert "café" in labels


def test_learned_relation_persists_and_hydrates(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "learned.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    key = "relation.learned.e_tutor_de"
    result, _ = _ingest(
        _link("sou tutor de jazz", expr="é tutor de", obj="jazz"), db, ontology, user
    )
    assert result.status is IngestStatus.COMMITTED, result.issues
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        rels = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == key and r.is_current
        ]
        assert len(rels) == 1
        assert rels[0].concept_id == learned_concept_id(key)
        jazz = uow.entities.get(user.user_id, rels[0].to_id)
        assert jazz is not None
        assert jazz.type_id == core_concept_id("entity.thing")
        uow.commit()

    fresh = OntologyRegistry.with_core_seeds()
    assert fresh.get_by_key(key) is None
    engine = create_sqlite_engine(sqlite_url(db))
    n = hydrate_learned_relation_types(fresh, engine)
    assert n == 1
    restored = fresh.get_by_key(key)
    assert restored is not None
    assert restored.id == learned_concept_id(key)
    engine.dispose()
