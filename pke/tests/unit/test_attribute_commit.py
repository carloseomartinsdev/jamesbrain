"""Attribute translation must drop competing primitive leftovers."""

from __future__ import annotations

from pke.interpretation.semantic.models import (
    PrimitiveKind,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.possessive_attribute_repair import SNAPSHOT_EXPRESSION
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.semantic.self_repair import apply_e1_self_repairs
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry


def setup_module() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def test_identity_query_clears_relation_leftovers() -> None:
    proposal = SemanticProposal(
        raw_input="qual é o meu carro?",
        utterance_kind="query",
        primitive_hint="relation",
        subject=SemanticEntityMention(
            text="eu", kind_hint="person", reference_kind="contextual", confidence=1.0
        ),
        object=SemanticEntityMention(
            text="carro", kind_hint="vehicle", reference_kind="possessive", confidence=1.0
        ),
        relation_expression="possui",
        link_semantics=True,
        temporal=SemanticTime(),
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.relation_expression is None
    assert repaired.link_semantics is False
    assert repaired.attribute_expression == SNAPSHOT_EXPRESSION
    primitive, _ = route_primitive(repaired)
    assert primitive is PrimitiveKind.ATTRIBUTE
    outcome = proposal_to_query_ir(repaired)
    assert outcome.query_ir is not None
    assert outcome.query_ir.query.attribute_query_mode == "snapshot"


def test_paint_assert_clears_event_leftovers() -> None:
    proposal = SemanticProposal(
        raw_input="pintei meu carro de cinza",
        utterance_kind="assert",
        primitive_hint="event",
        subject=SemanticEntityMention(text="eu", reference_kind="contextual", confidence=1.0),
        object=SemanticEntityMention(
            text="meu carro", kind_hint="vehicle", reference_kind="possessive", confidence=1.0
        ),
        action_expression="pintar",
        event_expression="pintar meu carro de cinza",
        attribute_expression="cinza",
        change_semantics=True,
        temporal=SemanticTime(occurrence_aspect="happened"),
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.action_expression is None
    assert repaired.event_expression is None
    assert repaired.temporal.occurrence_aspect is None
    primitive, _ = route_primitive(repaired)
    assert primitive is PrimitiveKind.ATTRIBUTE
    outcome = proposal_to_canonical_ir(repaired)
    assert outcome.ir is not None
    assert outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "color"


def test_paint_with_dimension_slot_accepts_color_outside_whitelist() -> None:
    """LLM already named the dimension (`cor = verde`); leftovers must not win."""
    proposal = SemanticProposal(
        raw_input="pintei meu carro de verde",
        utterance_kind="assert",
        primitive_hint="event",
        subject=SemanticEntityMention(
            text="carro", kind_hint="vehicle", reference_kind="possessive", confidence=1.0
        ),
        action_expression="pintar",
        attribute_expression="cor = verde",
        change_semantics=True,
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="happened"),
        confidence=0.9,
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.action_expression is None
    assert repaired.change_semantics is False
    assert repaired.temporal.occurrence_aspect is None
    primitive, _ = route_primitive(repaired)
    assert primitive is PrimitiveKind.ATTRIBUTE
    outcome = proposal_to_canonical_ir(repaired)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    assert outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "color"
    assert (outcome.ir.attribute.text_value or "").casefold() == "verde"


def test_event_without_dimension_slot_is_not_stolen() -> None:
    proposal = SemanticProposal(
        raw_input="eu viajei ontem",
        utterance_kind="assert",
        primitive_hint="event",
        subject=SemanticEntityMention(text="eu", reference_kind="contextual", confidence=1.0),
        action_expression="viajar",
        event_expression="viajar",
        change_semantics=True,
        temporal=SemanticTime(occurrence_aspect="happened"),
    )
    repaired = apply_e1_self_repairs(proposal)
    primitive, _ = route_primitive(repaired)
    assert primitive is PrimitiveKind.EVENT
    assert repaired.action_expression == "viajar"
