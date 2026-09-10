"""I11.13 — Attribute query corpus fixtures (AQ1–AQ15)."""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from tests.attribute_design import fixtures as af
from tests.semantic_resolution.fixtures import pr4_color, pr5_door_open


def aq1_write() -> SemanticProposal:
    return pr4_color()


def aq1_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Qual a cor do Corolla?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="cor",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def aq2_write() -> SemanticProposal:
    return af.at2_house_area()


def aq2_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Quantos metros quadrados tem minha casa?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="casa", kind_hint="place"),
        attribute_expression="metros quadrados",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def aq3_write() -> SemanticProposal:
    return af.at3_notebook_weight()


def aq3_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Quanto pesa o notebook?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="notebook", kind_hint="thing"),
        attribute_expression="peso",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def aq4_write() -> SemanticProposal:
    return af.at8_joao_height()


def aq4_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Qual a altura do João?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        attribute_expression="altura",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def aq5_write() -> SemanticProposal:
    return af.at9_corolla_year()


def aq5_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Qual o ano do Corolla?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="ano",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def aq6_write() -> SemanticProposal:
    return af.at12_tank_capacity_50()


def aq6_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Qual a capacidade do tanque?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        attribute_expression="capacidade",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def aq7_query_unknown() -> SemanticProposal:
    return aq1_query()


def aq9_write_historical_black() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla era preto.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="preto",
        stable_property_semantics=True,
        primitive_hint="attribute",
        temporal=SemanticTime(original_text="era", tense_evidence="era"),
    )


def aq9_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla já foi preto?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="preto",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def aq10_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla era preto em 2022?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="preto",
        stable_property_semantics=True,
        primitive_hint="attribute",
        temporal=SemanticTime(original_text="em 2022", partial_year=2022),
    )


def aq12_state() -> SemanticProposal:
    return pr5_door_open().model_copy(
        update={"raw_input": "A porta está aberta?", "utterance_kind": "query"}
    )


def aq13_event() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Já troquei a embreagem?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="embreagem", kind_hint="thing"),
        action_expression="troquei",
        change_semantics=True,
        primitive_hint="event",
        temporal=SemanticTime(original_text="", occurrence_aspect="happened"),
    )


def aq14_relation() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Quem é o fabricante do Corolla?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        object=SemanticEntityMention(text="fabricante", kind_hint="organization"),
        relation_expression="fabricante",
        link_semantics=True,
        primitive_hint="relation",
    )


def aq15_type() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla é um carro?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="carro",
        classification_semantics=True,
        primitive_hint="attribute",
    )
