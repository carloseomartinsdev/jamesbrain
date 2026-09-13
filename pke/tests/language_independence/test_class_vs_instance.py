"""Class vs instance on Semantic IR — Interpreter distinguishes; PKE must not reread NL."""

from __future__ import annotations

import datetime as dt

import pytest

from pke.domain.value_objects import UserContext
from pke.interpretation.interpreter import InterpretationContext
from pke.interpretation.ontology_view import InterpreterOntologyView
from pke.interpretation.prompts import PROMPT_VERSION_V4, PROMPT_VERSION_V5_EVENT, build_messages
from pke.interpretation.semantic.class_reference import propagate_class_hints
from pke.interpretation.semantic.entity_kinds import (
    class_hint_to_entity_type_key,
    resolve_entity_type,
)
from pke.interpretation.semantic.llm_vocab import coerce_reference_kind, normalize_entity_dict
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.semantic.self_repair import apply_e1_self_repairs
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.ontology import OntologyRegistry

NOW = dt.datetime(2026, 9, 10, 12, 0, tzinfo=dt.UTC)
OPAQUE = "OPAQUE-CLASS-QUERY-001"


def setup_module() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _actor() -> SemanticEntityMention:
    return SemanticEntityMention(
        text="self",
        kind_hint="person",
        reference_kind="contextual",
        confidence=1.0,
    )


def _query(**kwargs) -> SemanticProposal:
    body = {
        "raw_input": OPAQUE,
        "utterance_kind": "query",
        "temporal": SemanticTime(),
        "confidence": 1.0,
        "link_semantics": True,
        "primitive_hint": "relation",
        "relation_expression": "owns",
        "subject": _actor(),
    }
    body.update(kwargs)
    return SemanticProposal(**body)


def _envelope_query(raw: str, object_payload: dict) -> SemanticProposal:
    env = WireSemanticEnvelope.model_validate(
        {
            "ir_kind": "semantic_query",
            "ir": {
                "raw_input": raw,
                "utterance_kind": "query",
                "primitive_hint": "relation",
                "subject": {
                    "text": "self",
                    "kind_hint": "person",
                    "reference_kind": "contextual",
                },
                "object": object_payload,
                "relation_expression": "owns",
                "link_semantics": True,
                "confidence": 0.9,
            },
        }
    )
    return env.parsed_query_proposal()


CLASS_CASES = [
    ("eu tenho uma gata?", "gata", "cat"),
    ("eu tenho um cachorro?", "cachorro", "dog"),
    ("eu tenho um imóvel?", "imóvel", "property"),
    ("eu tenho um funcionário?", "funcionário", "employee"),
    ("eu tenho um computador?", "computador", "computer"),
    ("Do I have a cat?", "cat", "cat"),
    ("¿Tengo una gata?", "gata", "cat"),
    ("tenho alguma gata?", "gata", "cat"),
    ("existe alguma gata minha?", "gata", "cat"),
    ("possuo uma gata?", "gata", "cat"),
    ("há alguma gata que seja minha?", "gata", "cat"),
]

INSTANCE_CASES = [
    ("eu tenho Luna?", "Luna"),
    ("eu tenho Thor?", "Thor"),
    ("eu tenho a casa da praia?", "casa da praia"),
    ("eu tenho Carlos?", "Carlos"),
    ("eu tenho meu MacBook?", "MacBook"),
]


def test_contract_accepts_reference_kind_class() -> None:
    assert coerce_reference_kind("class") == "class"
    assert coerce_reference_kind("type_constraint") == "class"
    assert coerce_reference_kind("generic") == "class"
    mention = SemanticEntityMention(
        text="gata", kind_hint="thing", reference_kind="class", class_hint="cat"
    )
    assert mention.reference_kind == "class"
    assert resolve_entity_type(mention) == "entity.learned.cat"


def test_unknown_kind_hint_is_salvaged_as_class_hint() -> None:
    out = normalize_entity_dict({"text": "gata", "kind_hint": "cat"})
    assert "kind_hint" not in out
    assert out["class_hint"] == "cat"


def test_prompt_teaches_class_vs_instance() -> None:
    ctx = InterpretationContext(user=UserContext(user_id="u", timezone="UTC", now=NOW))
    view = InterpreterOntologyView.from_registry(OntologyRegistry.with_core_seeds())
    for version in (PROMPT_VERSION_V4, PROMPT_VERSION_V5_EVENT):
        blob = "\n".join(
            m.content
            for m in build_messages("eu tenho uma gata?", ctx, view, prompt_version=version)
        )
        assert "reference_kind=class" in blob or 'reference_kind:"class"' in blob
        assert "Do I have Luna?" in blob
        assert "Do I have a cat?" in blob
        assert "class_hint" in blob
        assert "gata = cat" not in blob
        assert "ANIMAL_WORDS" not in blob


@pytest.mark.parametrize("raw,text,lemma", CLASS_CASES)
def test_interpreter_envelope_class_constraint(raw: str, text: str, lemma: str) -> None:
    proposal = _envelope_query(
        raw,
        {"text": text, "kind_hint": "thing", "reference_kind": "class", "class_hint": lemma},
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.object is not None
    assert repaired.object.reference_kind == "class"
    assert repaired.object.class_hint == lemma
    outcome = proposal_to_query_ir(repaired)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    entities = outcome.query_ir.query.entities
    assert any(e.reference_kind.value == "class" for e in entities)
    class_ent = next(e for e in entities if e.reference_kind.value == "class")
    assert class_ent.type_hint is not None
    assert class_ent.type_hint.key == class_hint_to_entity_type_key(lemma)
    assert any(r.key == "relation.owns" for r in outcome.query_ir.query.relation_types)
    assert outcome.query_ir.query.relation_query_kind == "current_boolean"


@pytest.mark.parametrize("raw,text", INSTANCE_CASES)
def test_interpreter_envelope_named_instance_is_not_class(raw: str, text: str) -> None:
    proposal = _envelope_query(
        raw,
        {"text": text, "kind_hint": "thing", "reference_kind": "named"},
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.object is not None
    assert repaired.object.reference_kind == "named"
    assert repaired.object.reference_kind != "class"
    outcome = proposal_to_query_ir(repaired)
    assert outcome.query_ir is not None
    obj = next(e for e in outcome.query_ir.query.entities if e.role and e.role.key == "role.object")
    assert obj.reference_kind.value == "named"


def test_repair_does_not_overwrite_explicit_class() -> None:
    proposal = _query(
        raw_input="eu tenho gata?",
        object=SemanticEntityMention(
            text="gata",
            kind_hint="thing",
            reference_kind="class",
            class_hint="cat",
            confidence=1.0,
        ),
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.object is not None
    assert repaired.object.reference_kind == "class"
    assert repaired.object.class_hint == "cat"
    assert repaired.object.reference_kind != "contextual"


def test_repair_does_not_overwrite_named_instance() -> None:
    proposal = _query(
        raw_input="eu tenho Luna?",
        object=SemanticEntityMention(
            text="Luna", kind_hint="thing", reference_kind="named", confidence=1.0
        ),
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.object is not None
    assert repaired.object.reference_kind == "named"
    assert repaired.object.text == "Luna"


def test_propagate_class_hint_onto_named_instance() -> None:
    proposal = SemanticProposal(
        raw_input="eu tenho uma gata chamada luna",
        utterance_kind="assert",
        primitive_hint="relation",
        subject=_actor(),
        object=SemanticEntityMention(
            text="Luna", kind_hint="thing", reference_kind="named", confidence=1.0
        ),
        entities_mentioned=[
            SemanticEntityMention(
                text="gata",
                kind_hint="thing",
                reference_kind="class",
                class_hint="cat",
                confidence=1.0,
            )
        ],
        relation_expression="owns",
        link_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    merged = propagate_class_hints(proposal)
    assert merged.object is not None
    assert merged.object.class_hint == "cat"
    assert merged.object.reference_kind == "named"


def test_write_named_instance_keeps_class_type_and_owns() -> None:
    proposal = SemanticProposal(
        raw_input="eu tenho uma gata chamada luna",
        utterance_kind="assert",
        primitive_hint="relation",
        subject=_actor(),
        object=SemanticEntityMention(
            text="Luna",
            kind_hint="thing",
            reference_kind="named",
            class_hint="cat",
            confidence=1.0,
        ),
        relation_expression="owns",
        link_semantics=True,
        classification_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.owns"
    assert outcome.ir.relation.object.text == "Luna"
    assert outcome.ir.relation.object.reference_kind.value == "named"
    assert outcome.ir.relation.object.type_hint is not None
    assert outcome.ir.relation.object.type_hint.key == "entity.learned.cat"


def test_class_query_survives_opaque_raw_input() -> None:
    proposal = _query(
        object=SemanticEntityMention(
            text="gata",
            kind_hint="thing",
            reference_kind="class",
            class_hint="cat",
            confidence=1.0,
        )
    )
    outcome = proposal_to_query_ir(proposal)
    assert outcome.query_ir is not None
    opaque = outcome.query_ir.model_copy(update={"raw_input": OPAQUE})
    assert opaque.query.entities
    assert any(e.reference_kind.value == "class" for e in opaque.query.entities)
    assert any(r.key == "relation.owns" for r in opaque.query.relation_types)
    class_ent = next(e for e in opaque.query.entities if e.reference_kind.value == "class")
    assert class_ent.type_hint is not None
    assert class_ent.type_hint.key == "entity.learned.cat"


def test_class_without_class_hint_is_insufficient() -> None:
    proposal = _query(
        object=SemanticEntityMention(
            text="gata", kind_hint="thing", reference_kind="class", confidence=1.0
        )
    )
    outcome = proposal_to_query_ir(proposal)
    assert outcome.query_ir is None
    assert "class_constraint_unresolved" in outcome.notes
