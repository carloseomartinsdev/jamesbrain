"""Catálogo treinado (EXTENDED) — lemmas canônicos antes da memória do chat."""

from __future__ import annotations

from pathlib import Path

from pke.application.results import IngestStatus
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.ontology.seeds import CORE_SEEDS
from pke.ontology.trained import (
    apply_trained_catalog,
    load_trained_catalog,
    trained_concept_id,
    validate_trained_catalog,
)
from tests.e1_everyday.test_learned_relations import _ingest, _link, _user
from tests.generalization_ingest.fixtures import fresh_db_path


def test_approved_catalog_loads_and_is_consistent() -> None:
    catalog = load_trained_catalog()
    assert catalog.concepts
    assert validate_trained_catalog(catalog) == []
    core_count = len(CORE_SEEDS)
    ontology = OntologyRegistry.with_core_seeds()
    assert len(ontology.concepts()) == core_count == 67
    added = apply_trained_catalog(ontology)
    assert added >= 1
    assert len(ontology.concepts()) == core_count + added
    friend = ontology.get_by_key("relation.friend_of")
    assert friend is not None
    assert friend.id == trained_concept_id("relation.friend_of")
    assert ontology.get_by_key("relation.likes") is not None


def test_friend_of_is_catalog_not_learned() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    proposal = SemanticProposal(
        raw_input="sou amigo de João",
        utterance_kind="assert",
        primitive_hint="relation",
        subject=SemanticEntityMention(
            text="eu", kind_hint="person", reference_kind="contextual", confidence=1.0
        ),
        object=SemanticEntityMention(
            text="João", kind_hint="person", reference_kind="named", confidence=1.0
        ),
        relation_expression="amigo de",
        link_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.friend_of"


def test_contratado_por_extends_employed_by() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    proposal = SemanticProposal(
        raw_input="fui contratado pela Acme",
        utterance_kind="assert",
        primitive_hint="relation",
        subject=SemanticEntityMention(
            text="eu", kind_hint="person", reference_kind="contextual", confidence=1.0
        ),
        object=SemanticEntityMention(
            text="Acme", kind_hint="organization", reference_kind="named", confidence=1.0
        ),
        relation_expression="contratado por",
        link_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.employed_by"


def test_friend_of_ingests_with_deterministic_id(tmp_path: Path) -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    db = fresh_db_path(tmp_path, "friend.db")
    user = _user("u-train")
    ontology = OntologyRegistry.with_core_seeds()
    apply_trained_catalog(ontology)
    result, outcome = _ingest(
        _link("sou amigo de João", expr="amigo de", obj="João", obj_kind="person"),
        db,
        ontology,
        user,
    )
    assert result.status is IngestStatus.COMMITTED, result.issues
    assert outcome.ir is not None and outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.friend_of"
    from pke.persist import open_sqlite_uow

    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        rels = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.friend_of" and r.is_current
        ]
        assert len(rels) == 1
        assert rels[0].concept_id == trained_concept_id("relation.friend_of")
        uow.commit()
