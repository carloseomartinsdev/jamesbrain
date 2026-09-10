"""I11.12 — Attribute design corpus fixtures (AT1–AT14). Design-only; no Attribute persistence."""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from tests.semantic_resolution.fixtures import (
    pr1_fridge_broken,
    pr3_employment,
    pr4_color,
    pr5_door_open,
    px2_facilities_new,
    sc6_overdue,
)


def _ongoing() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="ongoing")


def at1_corolla_silver() -> SemanticProposal:
    return pr4_color()


def at2_house_area() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Minha casa tem 200 m².",
        subject=SemanticEntityMention(text="casa", kind_hint="place"),
        attribute_expression="200 m²",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def at3_notebook_weight() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O notebook pesa 1,5 kg.",
        subject=SemanticEntityMention(text="notebook", kind_hint="thing"),
        attribute_expression="1,5 kg",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def at4_door_open() -> SemanticProposal:
    return pr5_door_open()


def at5_phone_broken() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O celular está quebrado.",
        subject=SemanticEntityMention(text="celular", kind_hint="appliance"),
        state_expression="quebrado",
        condition_semantics=True,
        primitive_hint="state",
    )


def at6_bill_overdue() -> SemanticProposal:
    return sc6_overdue()


def at7_facilities_new() -> SemanticProposal:
    return px2_facilities_new()


def at8_joao_height() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O João tem 1,80 m.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        attribute_expression="1,80 m",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def at9_corolla_year() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Meu Corolla é 2020.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="2020",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def at10_fridge_white() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A geladeira é branca.",
        subject=SemanticEntityMention(text="geladeira", kind_hint="appliance"),
        attribute_expression="branca",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def at11_tank_20_liters() -> SemanticProposal:
    """Observed fill level — Measurement (not capacity Attribute)."""
    return SemanticProposal(
        raw_input="O tanque está com 20 litros.",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        state_expression="20 litros",
        measurement_expression="20 litros",
        measurable_dimension_key="fuel_level",
        measurement_numeric_value="20",
        measurement_unit="L",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
        temporal=_ongoing(),
    )


def at12_tank_capacity_50() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O tanque tem capacidade para 50 litros.",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        attribute_expression="capacidade 50 litros",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def at13_manufacturer_toyota() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O fabricante do Corolla é Toyota.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        object=SemanticEntityMention(text="Toyota", kind_hint="organization"),
        relation_expression="fabricante",
        link_semantics=True,
        primitive_hint="relation",
    )


def at14_corolla_is_car() -> SemanticProposal:
    """Entity typing / classification — not Attribute."""
    return SemanticProposal(
        raw_input="O Corolla é um carro.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="carro",
        classification_semantics=True,
        stable_property_semantics=False,
        primitive_hint="type",
    )


def fridge_broken_regression() -> SemanticProposal:
    return pr1_fridge_broken()


def employment_regression() -> SemanticProposal:
    return pr3_employment()
