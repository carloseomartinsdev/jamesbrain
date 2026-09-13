"""Relation target constrained by entity class/type — no linguistic rules."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW

from pke.application.ask import AskService
from pke.application.ask_results import AskStatus
from pke.application.clock import FixedClock
from pke.application.ingest import IngestService
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.ontology.learned import hydrate_learned_entity_types, learned_concept_id
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.persist.sqlite.engine import create_sqlite_engine, sqlite_url
from pke.resolution.context import PersonalContext

OPAQUE = "OPAQUE-CLASS-QUERY-001"


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = "u-class") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-class") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _actor() -> SemanticEntityMention:
    return SemanticEntityMention(
        text="self",
        kind_hint="person",
        reference_kind="contextual",
        confidence=1.0,
    )


def _write_named(*, raw: str, name: str, class_hint: str) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="assert",
        primitive_hint="relation",
        subject=_actor(),
        object=SemanticEntityMention(
            text=name,
            kind_hint="thing",
            reference_kind="named",
            class_hint=class_hint,
            confidence=1.0,
        ),
        relation_expression="owns",
        link_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )


def _class_query(*, raw: str, text: str, class_hint: str) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="query",
        primitive_hint="relation",
        subject=_actor(),
        object=SemanticEntityMention(
            text=text,
            kind_hint="thing",
            reference_kind="class",
            class_hint=class_hint,
            confidence=1.0,
        ),
        relation_expression="owns",
        link_semantics=True,
        temporal=SemanticTime(),
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


def test_owns_class_constraint_matches_named_instance(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "class-cat.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    written, write_ir = _ingest(
        _write_named(raw="eu tenho uma gata chamada luna", name="Luna", class_hint="cat"),
        db,
        ontology,
        user,
    )
    assert written.status is IngestStatus.COMMITTED, written.issues
    assert write_ir.ir is not None and write_ir.ir.relation is not None
    assert write_ir.ir.relation.type.key == "relation.owns"
    assert write_ir.ir.relation.object.type_hint is not None
    assert write_ir.ir.relation.object.type_hint.key == "entity.learned.cat"

    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        rels = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current
        ]
        assert len(rels) == 1
        luna = uow.entities.get(user.user_id, rels[0].to_id)
        assert luna is not None
        assert luna.canonical_name == "Luna"
        assert luna.type_id == learned_concept_id("entity.learned.cat")
        uow.commit()

    query = _class_query(raw=OPAQUE, text="gata", class_hint="cat")
    q_out = proposal_to_query_ir(query)
    assert q_out.query_ir is not None, (q_out.status, q_out.notes)
    opaque = q_out.query_ir.model_copy(update={"raw_input": OPAQUE})
    ask = AskService(
        FakeInterpreter({OPAQUE: opaque}),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    answered = ask.ask(OPAQUE, user, _session(user.user_id))
    assert answered.status is AskStatus.ANSWERED, (answered.status, answered.issues)
    assert answered.query_result is not None
    assert answered.query_result.relation_answer == "yes"


def test_class_constraint_does_not_match_other_class(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "class-miss.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    written, _ = _ingest(
        _write_named(
            raw="eu tenho um computador chamado mac",
            name="MacBook",
            class_hint="computer",
        ),
        db,
        ontology,
        user,
    )
    assert written.status is IngestStatus.COMMITTED, written.issues
    query = _class_query(raw="eu tenho uma gata?", text="gata", class_hint="cat")
    q_out = proposal_to_query_ir(query)
    assert q_out.query_ir is not None
    ask = AskService(
        FakeInterpreter({query.raw_input: q_out.query_ir}),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    result = ask.ask(query.raw_input, user, _session(user.user_id))
    assert result.query_result is not None
    assert result.query_result.relation_answer == "no"


def test_learned_entity_type_hydrates(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "class-hydrate.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    written, _ = _ingest(
        _write_named(raw="named employee", name="Carlos", class_hint="employee"),
        db,
        ontology,
        user,
    )
    assert written.status is IngestStatus.COMMITTED, written.issues
    fresh = OntologyRegistry.with_core_seeds()
    assert fresh.get_by_key("entity.learned.employee") is None
    engine = create_sqlite_engine(sqlite_url(db))
    n = hydrate_learned_entity_types(fresh, engine)
    assert n == 1
    restored = fresh.get_by_key("entity.learned.employee")
    assert restored is not None
    assert restored.id == learned_concept_id("entity.learned.employee")
    engine.dispose()
