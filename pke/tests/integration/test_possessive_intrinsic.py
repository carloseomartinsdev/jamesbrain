"""Possessive entity resolution + intrinsic name — no linguistic rules."""

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
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.query.intrinsic import INTRINSIC_NOTE
from pke.resolution.context import PersonalContext

OPAQUE = "OPAQUE-POSSESSIVE-001"


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = "u-poss") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-poss") -> SessionContext:
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


def _class_owns_query(*, raw: str, text: str, class_hint: str) -> SemanticProposal:
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


def _possessive_attr_query(
    *,
    raw: str,
    text: str,
    class_hint: str,
    attribute_expression: str,
) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="query",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text=text,
            kind_hint="thing",
            class_hint=class_hint,
            reference_kind="possessive",
            confidence=1.0,
        ),
        attribute_expression=attribute_expression,
        stable_property_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )


def _color_assert(*, raw: str, name: str, class_hint: str, expr: str) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text=name,
            kind_hint="thing",
            class_hint=class_hint,
            reference_kind="named",
            confidence=1.0,
        ),
        attribute_expression=expr,
        stable_property_semantics=True,
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


def _ask(proposal: SemanticProposal, db: Path, ontology: OntologyRegistry, user: UserContext, *, opaque: bool = False):
    q_out = proposal_to_query_ir(proposal)
    assert q_out.query_ir is not None, (q_out.status, q_out.notes)
    ir = q_out.query_ir
    raw = OPAQUE if opaque else proposal.raw_input
    if opaque:
        ir = ir.model_copy(update={"raw_input": OPAQUE})
    ask = AskService(
        FakeInterpreter({raw: ir}),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    return ask.ask(raw, user, _session(user.user_id)), q_out


def test_possessive_ir_ignores_surface_language() -> None:
    queries = [
        _possessive_attr_query(
            raw="qual o nome do meu gato?",
            text="gato",
            class_hint="cat",
            attribute_expression="name",
        ),
        _possessive_attr_query(
            raw="what is my cat's name?",
            text="cat",
            class_hint="cat",
            attribute_expression="name",
        ),
        _possessive_attr_query(
            raw="¿cómo se llama mi gato?",
            text="gato",
            class_hint="cat",
            attribute_expression="name",
        ),
    ]
    specs = []
    for proposal in queries:
        out = proposal_to_query_ir(proposal)
        assert out.query_ir is not None, (proposal.raw_input, out.notes)
        q = out.query_ir.query
        assert q.intent == "attribute"
        assert q.attribute_dimension_key == "name"
        assert q.attribute_query_mode == "value_lookup"
        subj = next(e for e in q.entities if e.reference_kind.value == "possessive")
        assert subj.type_hint is not None
        assert subj.type_hint.key == "entity.learned.cat"
        specs.append(
            (
                q.intent,
                q.attribute_dimension_key,
                q.attribute_query_mode,
                subj.reference_kind.value,
                subj.type_hint.key,
            )
        )
    assert specs[0] == specs[1] == specs[2]


def test_class_owns_query_still_answered(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "poss-class-reg.db")
    user = _user("u-class-reg")
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    written, _ = _ingest(
        _write_named(raw="eu tenho uma gata chamada luna", name="Luna", class_hint="cat"),
        db,
        ontology,
        user,
    )
    assert written.status is IngestStatus.COMMITTED
    result, _ = _ask(
        _class_owns_query(raw="eu tenho uma gata?", text="gata", class_hint="cat"),
        db,
        ontology,
        user,
    )
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.relation_answer == "yes"


def test_possessive_cat_name_from_identity(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "poss-luna.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    written, _ = _ingest(
        _write_named(raw="eu tenho uma gata chamada luna", name="Luna", class_hint="cat"),
        db,
        ontology,
        user,
    )
    assert written.status is IngestStatus.COMMITTED, written.issues
    luna_id = None
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
        luna_id = luna.id
        names = uow.attributes.for_entity_dimension(user.user_id, luna.id, "name")
        assert names == []
        uow.commit()

    result, q_out = _ask(
        _possessive_attr_query(
            raw="qual o nome do meu gato?",
            text="gato",
            class_hint="cat",
            attribute_expression="nome",
        ),
        db,
        ontology,
        user,
        opaque=False,
    )
    assert q_out.query_ir is not None
    assert q_out.query_ir.query.attribute_dimension_key == "name"
    assert result.status is AskStatus.ANSWERED, (result.status, result.issues)
    assert result.resolved_entity_ids == [luna_id]
    assert result.query_result is not None
    values = result.query_result.attribute_values
    assert len(values) == 1
    assert values[0].text_value == "Luna"
    assert INTRINSIC_NOTE in result.query_result.warnings
    assert not values[0].assertion_ids


def test_possessive_name_survives_opaque_raw_input(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "poss-opaque.db")
    user = _user("u-opaque")
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    written, _ = _ingest(
        _write_named(raw="named luna", name="Luna", class_hint="cat"),
        db,
        ontology,
        user,
    )
    assert written.status is IngestStatus.COMMITTED
    result, _ = _ask(
        _possessive_attr_query(
            raw="qual o nome do meu gato?",
            text="gato",
            class_hint="cat",
            attribute_expression="name",
        ),
        db,
        ontology,
        user,
        opaque=True,
    )
    assert result.status is AskStatus.ANSWERED, (result.status, result.issues)
    assert result.raw_text == OPAQUE
    assert result.query_result is not None
    assert result.query_result.attribute_values[0].text_value == "Luna"


@pytest.mark.parametrize(
    ("name", "class_hint"),
    [("Orion", "computer"), ("Solar", "property")],
)
def test_possessive_name_generic_types(tmp_path: Path, name: str, class_hint: str) -> None:
    db = fresh_db_path(tmp_path, f"poss-{class_hint}.db")
    user = _user(f"u-{class_hint}")
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    written, _ = _ingest(
        _write_named(raw=f"owns {name}", name=name, class_hint=class_hint),
        db,
        ontology,
        user,
    )
    assert written.status is IngestStatus.COMMITTED, written.issues
    result, _ = _ask(
        _possessive_attr_query(
            raw=f"name of my {class_hint}",
            text=class_hint,
            class_hint=class_hint,
            attribute_expression="name",
        ),
        db,
        ontology,
        user,
    )
    assert result.status is AskStatus.ANSWERED, (result.status, result.issues)
    assert result.query_result is not None
    assert result.query_result.attribute_values[0].text_value == name


def test_possessive_color_uses_attribute_not_intrinsic(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "poss-color.db")
    user = _user("u-color")
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    written, _ = _ingest(
        _write_named(raw="owns CarA", name="CarA", class_hint="automobile"),
        db,
        ontology,
        user,
    )
    assert written.status is IngestStatus.COMMITTED, written.issues
    colored, _ = _ingest(
        _color_assert(raw="CarA is blue", name="CarA", class_hint="automobile", expr="cor azul"),
        db,
        ontology,
        user,
    )
    assert colored.status is IngestStatus.COMMITTED, colored.issues
    result, _ = _ask(
        _possessive_attr_query(
            raw="qual a cor do meu carro?",
            text="carro",
            class_hint="automobile",
            attribute_expression="cor",
        ),
        db,
        ontology,
        user,
    )
    assert result.status is AskStatus.ANSWERED, (result.status, result.issues)
    assert result.query_result is not None
    assert result.query_result.attribute_values[0].text_value == "azul"
    assert INTRINSIC_NOTE not in result.query_result.warnings


def test_possessive_two_cats_needs_clarification(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "poss-two.db")
    user = _user("u-two")
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    for raw, name in (("owns luna", "Luna"), ("owns nala", "Nala")):
        written, _ = _ingest(_write_named(raw=raw, name=name, class_hint="cat"), db, ontology, user)
        assert written.status is IngestStatus.COMMITTED, written.issues
    result, _ = _ask(
        _possessive_attr_query(
            raw="name of my cat",
            text="gato",
            class_hint="cat",
            attribute_expression="name",
        ),
        db,
        ontology,
        user,
    )
    assert result.status is AskStatus.NEEDS_CLARIFICATION
    assert result.clarification is not None
    assert result.clarification.clarification_key == "clarify.entity.which_one"
    assert len(result.clarification.candidate_entity_ids) == 2


def test_possessive_wrong_class_is_no_match(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "poss-miss.db")
    user = _user("u-miss")
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    written, _ = _ingest(
        _write_named(raw="owns orion", name="Orion", class_hint="computer"),
        db,
        ontology,
        user,
    )
    assert written.status is IngestStatus.COMMITTED
    result, _ = _ask(
        _possessive_attr_query(
            raw="name of my cat",
            text="gato",
            class_hint="cat",
            attribute_expression="name",
        ),
        db,
        ontology,
        user,
    )
    assert result.status is AskStatus.NO_RESULTS
    assert result.resolved_entity_ids == []
    codes = [i.code for i in result.issues]
    assert "entity.unresolved" not in codes
    assert "entity.no_match" in codes
