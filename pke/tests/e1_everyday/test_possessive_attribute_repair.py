"""Registry-driven possessive repairs — any possessed noun, not vehicle-only."""

from __future__ import annotations

from pke.interpretation.semantic.possessive_attribute_repair import (
    SNAPSHOT_EXPRESSION,
    repair_possessive_attributes,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.semantic.self_repair import apply_e1_self_repairs
from pke.interpretation.semantic.models import SemanticProposal, SemanticTime
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry


def setup_module() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _blank(raw: str) -> SemanticProposal:
    return SemanticProposal(raw_input=raw, temporal=SemanticTime())


def test_year_query_any_noun() -> None:
    for raw in (
        "qual o ano do meu carro?",
        "qual o ano da minha moto?",
        "qual é o ano da minha casa?",
    ):
        repaired = apply_e1_self_repairs(_blank(raw))
        assert repaired.utterance_kind == "query"
        assert repaired.attribute_expression not in {None, "marca", SNAPSHOT_EXPRESSION}
        outcome = proposal_to_query_ir(repaired)
        assert outcome.query_ir is not None, (raw, outcome.status, outcome.notes)
        assert outcome.query_ir.query.attribute_dimension_key == "model_year"


def test_year_write_any_noun() -> None:
    for raw, noun in (
        ("o ano do meu carro é 2008", "carro"),
        ("o ano da minha casa é 2010", "casa"),
    ):
        repaired = apply_e1_self_repairs(_blank(raw))
        assert repaired.subject is not None and repaired.subject.text == noun
        outcome = proposal_to_canonical_ir(repaired)
        assert outcome.ir is not None, (raw, outcome.failure_stage, outcome.execution_reasons)
        assert outcome.ir.attribute is not None
        assert outcome.ir.attribute.dimension_key == "model_year"
        assert outcome.ir.attribute.year_value == (2008 if "2008" in raw else 2010)


def test_color_write_and_paint_any_noun() -> None:
    color = apply_e1_self_repairs(_blank("a cor da minha bicicleta é azul"))
    assert color.attribute_expression
    painted = apply_e1_self_repairs(_blank("pintei minha porta de cinza"))
    assert painted.change_semantics is False
    assert painted.primitive_hint == "attribute"
    outcome = proposal_to_canonical_ir(painted)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    assert outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "color"
    no_poss = apply_e1_self_repairs(_blank("pintei o carro de cinza"))
    outcome2 = proposal_to_canonical_ir(no_poss)
    assert outcome2.ir is not None, (outcome2.failure_stage, outcome2.execution_reasons)
    assert outcome2.ir.attribute is not None
    assert outcome2.ir.attribute.dimension_key == "color"


def test_overview_is_snapshot() -> None:
    repaired = apply_e1_self_repairs(_blank("o que você sabe sobre o meu telefone?"))
    assert repaired.attribute_expression == SNAPSHOT_EXPRESSION
    outcome = proposal_to_query_ir(repaired)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    assert outcome.query_ir.query.attribute_query_mode == "snapshot"


def test_possession_is_relation_query() -> None:
    repaired = apply_e1_self_repairs(_blank("james, eu tenho carro?"))
    assert repaired.primitive_hint == "relation"
    assert repaired.object is not None and repaired.object.text == "carro"
    outcome = proposal_to_query_ir(repaired)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    assert outcome.query_ir.query.intent == "relation"


def test_does_not_invent_preference_dimension() -> None:
    repaired = apply_e1_self_repairs(_blank("eu prefiro café com leite"))
    assert repaired.attribute_expression != "preferencia"
    outcome = proposal_to_canonical_ir(repaired)
    if outcome.ir is not None and getattr(outcome.ir, "attribute", None) is not None:
        assert outcome.ir.attribute.dimension_key != "preference"


def test_self_dimension_is_not_an_entity_named_nome() -> None:
    repaired = apply_e1_self_repairs(_blank("Qual é o meu nome?"))
    assert repaired.subject is not None
    assert repaired.subject.text == "eu"
    assert repaired.attribute_expression == "nome"
    outcome = proposal_to_query_ir(repaired)
    assert outcome.query_ir is not None
    assert outcome.query_ir.query.attribute_dimension_key == "name"


def test_keeps_well_formed_color_query_subject() -> None:
    from pke.interpretation.semantic.models import SemanticEntityMention

    proposal = SemanticProposal(
        raw_input="Qual é a cor do meu carro?",
        utterance_kind="query",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="carro", kind_hint="vehicle", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="cor",
        stable_property_semantics=True,
        temporal=SemanticTime(),
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.subject is not None
    assert repaired.subject.text == "carro"
    assert repaired.subject.kind_hint == "vehicle"
    assert repaired.attribute_expression == "cor"


def test_named_entity_year_copula_keeps_subject() -> None:
    from pke.interpretation.semantic.models import SemanticEntityMention

    proposal = SemanticProposal(
        raw_input="Meu Corolla é 2020.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="2020",
        stable_property_semantics=True,
        primitive_hint="attribute",
        temporal=SemanticTime(),
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.subject is not None
    assert repaired.subject.text == "Corolla"
    assert repaired.subject.kind_hint == "vehicle"
    outcome = proposal_to_canonical_ir(repaired)
    assert outcome.ir is not None
    assert outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "model_year"


def test_third_party_name_write_is_not_self() -> None:
    from pke.interpretation.semantic.models import SemanticEntityMention

    proposal = SemanticProposal(
        raw_input="O nome do meu amigo é João.",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="amigo", kind_hint="person", reference_kind="named", confidence=1.0
        ),
        attribute_expression="name is João",
        stable_property_semantics=True,
        temporal=SemanticTime(),
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.subject is not None
    assert repaired.subject.reference_kind == "named"
    assert repaired.subject.text == "amigo"


def test_llm_year_expression_with_alias_and_value() -> None:
    from pke.interpretation.semantic.models import SemanticEntityMention

    proposal = SemanticProposal(
        raw_input="o ano do meu carro é 2008",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="carro", kind_hint="vehicle", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="ano 2008",
        stable_property_semantics=True,
        temporal=SemanticTime(),
    )
    repaired = apply_e1_self_repairs(proposal)
    outcome = proposal_to_canonical_ir(repaired)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    assert outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "model_year"
    assert outcome.ir.attribute.year_value == 2008


def test_me_chamo_from_event_primitive() -> None:
    proposal = SemanticProposal(
        raw_input="me chamo carlos",
        utterance_kind="assert",
        primitive_hint="event",
        change_semantics=True,
        event_expression="me chamo carlos",
        temporal=SemanticTime(),
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.primitive_hint == "attribute"
    assert repaired.subject is not None and repaired.subject.text == "eu"
    outcome = proposal_to_canonical_ir(repaired)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    assert outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "name"


def test_value_continuation_after_dimension_query() -> None:
    year = apply_e1_self_repairs(
        _blank("é 2008"),
        prior_utterances=["qual o ano do meu carro?"],
    )
    assert year.subject is not None and year.subject.text == "carro"
    year_ir = proposal_to_canonical_ir(
        year, prior_utterances=["qual o ano do meu carro?"]
    )
    assert year_ir.ir is not None, (year_ir.failure_stage, year_ir.execution_reasons)
    assert year_ir.ir.attribute is not None
    assert year_ir.ir.attribute.dimension_key == "model_year"
    assert year_ir.ir.attribute.year_value == 2008

    color = apply_e1_self_repairs(
        _blank("é azul"),
        prior_utterances=["qual a cor da minha porta?"],
    )
    assert color.subject is not None and color.subject.text == "porta"
    color_ir = proposal_to_canonical_ir(
        color, prior_utterances=["qual a cor da minha porta?"]
    )
    assert color_ir.ir is not None
    assert color_ir.ir.attribute is not None
    assert color_ir.ir.attribute.dimension_key == "color"
