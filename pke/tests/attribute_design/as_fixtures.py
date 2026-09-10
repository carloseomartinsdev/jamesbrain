"""I11.12.1 — AS1–AS8 attribute routing safety fixtures."""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from tests.attribute_design.fixtures import (
    at1_corolla_silver,
    at2_house_area,
    at11_tank_20_liters,
    at12_tank_capacity_50,
    at14_corolla_is_car,
)


def _happened() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="happened")


def as1_corolla_silver() -> SemanticProposal:
    return at1_corolla_silver()


def as2_corolla_is_car() -> SemanticProposal:
    return at14_corolla_is_car()


def as3_corolla_broken() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla está quebrado.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        state_expression="quebrado",
        condition_semantics=True,
        primitive_hint="state",
    )


def as4_corolla_broke() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla quebrou.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        event_expression="quebrou",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def as5_corolla_belongs_joao() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla pertence a João.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        object=SemanticEntityMention(text="João", kind_hint="person"),
        relation_expression="pertence",
        link_semantics=True,
        primitive_hint="relation",
    )


def as6_house_area() -> SemanticProposal:
    return at2_house_area()


def as7_tank_20_liters() -> SemanticProposal:
    return at11_tank_20_liters()


def as8_tank_capacity() -> SemanticProposal:
    return at12_tank_capacity_50()


def tc_rex_dog() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Rex é um cachorro.",
        subject=SemanticEntityMention(text="Rex", kind_hint="thing"),
        attribute_expression="cachorro",
        classification_semantics=True,
        primitive_hint="type",
    )


def tc_ana_doctor() -> SemanticProposal:
    """Occupation — not entity species classification; safe unresolved / Relation candidate."""
    return SemanticProposal(
        raw_input="A Ana é médica.",
        subject=SemanticEntityMention(text="Ana", kind_hint="person"),
        attribute_expression="médica",
        stable_property_semantics=True,
        classification_semantics=False,
        primitive_hint="attribute",
    )


def tc_file_pdf() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O arquivo é um PDF.",
        subject=SemanticEntityMention(text="arquivo", kind_hint="document"),
        attribute_expression="PDF",
        classification_semantics=True,
        primitive_hint="type",
    )


def tc_fridge_electrolux() -> SemanticProposal:
    """Brand/manufacturer — Relation candidate, not Attribute text by default."""
    return SemanticProposal(
        raw_input="Minha geladeira é Electrolux.",
        subject=SemanticEntityMention(text="geladeira", kind_hint="appliance"),
        object=SemanticEntityMention(text="Electrolux", kind_hint="organization"),
        relation_expression="fabricante",
        link_semantics=True,
        primitive_hint="relation",
    )
