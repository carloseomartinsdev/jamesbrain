"""Semantic proposal fixtures for Measurement query routing (MQ)."""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from tests.attribute_design import fixtures as af
from tests.measurement_design import fixtures as mf


def mq2_latest_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Qual foi a última leitura da bateria?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        measurement_expression="leitura",
        measurable_dimension_key="battery_charge",
        measurement_semantics=True,
        primitive_hint="measurement",
    )


def mq5_current_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Quanto está a bateria agora?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        measurement_expression="carga",
        measurable_dimension_key="battery_charge",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=SemanticTime(original_text="agora"),
    )


def mq6_yesterday_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Quanto estava a bateria ontem?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        measurable_dimension_key="battery_charge",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=SemanticTime(original_text="ontem", relative_day="yesterday"),
    )


def mq7_prop_yesterday() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A bateria estava em 80% ontem?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        measurable_dimension_key="battery_charge",
        measurement_numeric_value="80",
        measurement_unit="%",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=SemanticTime(original_text="ontem", relative_day="yesterday"),
    )


def mq8_prop_no_rows() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A bateria estava em 80%?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        measurable_dimension_key="battery_charge",
        measurement_numeric_value="80",
        measurement_unit="%",
        measurement_semantics=True,
        primitive_hint="measurement",
    )


def mq13_balance_prop() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O saldo era R$ 2500?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="conta", kind_hint="thing"),
        measurable_dimension_key="balance",
        measurement_numeric_value="2500",
        measurement_currency_code="BRL",
        measurement_semantics=True,
        primitive_hint="measurement",
    )


def mq18_capacity_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Qual a capacidade do tanque?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        attribute_expression="capacidade",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def mq19_fuel_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Quanto tinha no tanque?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        measurable_dimension_key="fuel_level",
        measurement_semantics=True,
        primitive_hint="measurement",
    )


def mq20_charge_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Qual era a carga da bateria?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        measurable_dimension_key="battery_charge",
        measurement_semantics=True,
        primitive_hint="measurement",
    )


def attribute_weight_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Quanto pesa o notebook?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="notebook", kind_hint="thing"),
        attribute_expression="peso",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def state_battery_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A bateria acabou?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        state_expression="acabou",
        condition_semantics=True,
        primitive_hint="state",
    )


def event_rent_query() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Quanto paguei de aluguel?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="eu", kind_hint="person"),
        action_expression="paguei",
        event_expression="aluguel",
        change_semantics=True,
        primitive_hint="event",
    )


def tank_write() -> SemanticProposal:
    return af.at11_tank_20_liters()


def tank_capacity_write() -> SemanticProposal:
    return af.at12_tank_capacity_50()


def battery_write() -> SemanticProposal:
    return mf.m3_battery_charge()
