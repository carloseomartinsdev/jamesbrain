"""I11.15 — Measurement design corpus (M1–M20 + open quantitative cases). Design-only."""

from __future__ import annotations

from enum import StrEnum

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from tests.attribute_design import fixtures as af
from tests.semantic_resolution.fixtures import pr4_color


class DesignPrimitive(StrEnum):
    """Design-target classification — not necessarily current PrimitiveKind."""

    MEASUREMENT = "measurement"
    ATTRIBUTE = "attribute"
    STATE = "state"
    EVENT = "event"
    RELATION = "relation"
    TYPE = "type"
    AMBIGUOUS = "ambiguous"


class InformationLoss(StrEnum):
    NONE = "none"
    NON_CRITICAL = "non_critical"
    CRITICAL = "critical"


def _ongoing() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="ongoing")


def _happened() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="happened")


def m1_tank_content() -> SemanticProposal:
    return af.at11_tank_20_liters()


def m2_tank_capacity() -> SemanticProposal:
    return af.at12_tank_capacity_50()


def m3_battery_charge() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A bateria está em 80%.",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        state_expression="80%",
        measurement_expression="80%",
        measurable_dimension_key="battery_charge",
        measurement_numeric_value="80",
        measurement_unit="%",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
        temporal=_ongoing(),
    )


def m4_battery_depleted() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A bateria acabou.",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        state_expression="acabou",
        condition_semantics=True,
        primitive_hint="state",
    )


def m5_battery_capacity() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A bateria tem 5000 mAh.",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        attribute_expression="capacidade 5000 mAh",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def m6_odometer() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla está com 125.000 km.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        state_expression="125000 km",
        measurement_expression="125000 km",
        measurable_dimension_key="odometer",
        measurement_numeric_value="125000",
        measurement_unit="km",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
        temporal=_ongoing(),
    )


def m7_fuel_efficiency() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla faz 12 km/L.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="12 km/L",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def m8_temperature() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A temperatura está em 38 °C.",
        subject=SemanticEntityMention(text="temperatura", kind_hint="thing"),
        state_expression="38 °C",
        measurement_expression="38 °C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="38",
        measurement_unit="°C",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
        temporal=_ongoing(),
    )


def m9_motor_overheated() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O motor está superaquecido.",
        subject=SemanticEntityMention(text="motor", kind_hint="thing"),
        state_expression="superaquecido",
        condition_semantics=True,
        primitive_hint="state",
    )


def m10_measure_temperature_event() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Medi a temperatura do motor.",
        object=SemanticEntityMention(text="temperatura", kind_hint="thing"),
        entities_mentioned=[SemanticEntityMention(text="motor", kind_hint="thing")],
        action_expression="medi",
        change_semantics=True,
        event_expression="medi temperatura",
        primitive_hint="event",
        temporal=_happened(),
    )


def m11_measure_and_result() -> SemanticProposal:
    """Multi-primitive: Event(measure) + Measurement(95°C) — design only."""
    return SemanticProposal(
        raw_input="Medi a temperatura e deu 95 °C.",
        object=SemanticEntityMention(text="temperatura", kind_hint="thing"),
        action_expression="medi",
        change_semantics=True,
        event_expression="medi temperatura",
        state_expression="95 °C",
        measurement_expression="95 °C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="95",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def m12_account_balance() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O saldo da conta é R$ 2.500.",
        subject=SemanticEntityMention(text="conta", kind_hint="document"),
        state_expression="R$ 2500",
        measurement_expression="R$ 2500",
        measurable_dimension_key="balance",
        measurement_numeric_value="2500",
        measurement_currency_code="BRL",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def m13_rent_amount() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O aluguel é R$ 550.",
        subject=SemanticEntityMention(text="aluguel", kind_hint="document"),
        attribute_expression="R$ 550",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def m14_paid_rent() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Paguei R$ 550 de aluguel.",
        object=SemanticEntityMention(text="aluguel", kind_hint="document"),
        action_expression="paguei",
        change_semantics=True,
        event_expression="paguei aluguel",
        primitive_hint="event",
        temporal=_happened(),
    )


def m15_bill_came() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A conta veio R$ 550.",
        subject=SemanticEntityMention(text="conta", kind_hint="document"),
        attribute_expression="R$ 550",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def m16_purchase_price() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla custou R$ 80 mil.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        action_expression="custou",
        change_semantics=True,
        event_expression="custou",
        primitive_hint="event",
        temporal=_happened(),
    )


def m17_inventory_bottles() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Tem 12 garrafas na geladeira.",
        object=SemanticEntityMention(text="garrafas", kind_hint="thing"),
        entities_mentioned=[SemanticEntityMention(text="geladeira", kind_hint="appliance")],
        state_expression="12",
        measurement_expression="12",
        measurable_dimension_key="inventory_count",
        measurement_numeric_value="12",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def m18_table_width() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A mesa tem 1,20 m de largura.",
        subject=SemanticEntityMention(text="mesa", kind_hint="thing"),
        attribute_expression="1,20 m largura",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def m19_joao_height() -> SemanticProposal:
    return af.at8_joao_height()


def m20_notebook_weight() -> SemanticProposal:
    return af.at3_notebook_weight()


def mq1_house_area() -> SemanticProposal:
    return af.at2_house_area()


def mq2_model_year() -> SemanticProposal:
    return af.at9_corolla_year()


def mq3_fridge_white() -> SemanticProposal:
    return af.at10_fridge_white()


def mq4_person_weight() -> SemanticProposal:
    return SemanticProposal(
        raw_input="João pesa 70 kg.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        attribute_expression="70 kg",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def mq5_tank_capacity_alt() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O tanque do Corolla tem capacidade para 45 litros.",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        entities_mentioned=[SemanticEntityMention(text="Corolla", kind_hint="vehicle")],
        attribute_expression="capacidade 45 litros",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def mq6_fuel_level_yesterday() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Ontem o tanque estava com 10 litros.",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        state_expression="10 litros",
        measurement_expression="10 litros",
        measurable_dimension_key="fuel_level",
        measurement_numeric_value="10",
        measurement_unit="L",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
        temporal=SemanticTime(original_text="ontem", occurrence_aspect="happened"),
    )


def mq7_battery_40() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A bateria do notebook está em 40%.",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        entities_mentioned=[SemanticEntityMention(text="notebook", kind_hint="thing")],
        state_expression="40%",
        measurement_expression="40%",
        measurable_dimension_key="battery_charge",
        measurement_numeric_value="40",
        measurement_unit="%",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def mq8_speed() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O carro estava a 80 km/h.",
        subject=SemanticEntityMention(text="carro", kind_hint="vehicle"),
        state_expression="80 km/h",
        measurement_expression="80 km/h",
        measurable_dimension_key="speed",
        measurement_numeric_value="80",
        measurement_unit="km/h",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
        temporal=_happened(),
    )


def mq9_water_pressure() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A pressão da água está em 3 bar.",
        subject=SemanticEntityMention(text="pressão da água", kind_hint="thing"),
        state_expression="3 bar",
        measurement_expression="3 bar",
        measurable_dimension_key="pressure",
        measurement_numeric_value="3",
        measurement_unit="bar",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def mq10_stock_count() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Temos 30 unidades em estoque.",
        subject=SemanticEntityMention(text="estoque", kind_hint="place"),
        state_expression="30 unidades",
        measurement_expression="30",
        measurable_dimension_key="inventory_count",
        measurement_numeric_value="30",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def mq11_paid_electricity() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Paguei R$ 220 de luz.",
        object=SemanticEntityMention(text="luz", kind_hint="document"),
        action_expression="paguei",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mq12_bought_milk() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Comprei 2 litros de leite.",
        object=SemanticEntityMention(text="leite", kind_hint="thing"),
        action_expression="comprei",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mq13_weighed_package() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Pesei o pacote.",
        object=SemanticEntityMention(text="pacote", kind_hint="thing"),
        action_expression="pesei",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mq14_scale_marked() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A balança marcou 10 kg.",
        subject=SemanticEntityMention(text="balança", kind_hint="thing"),
        state_expression="10 kg",
        measurement_expression="10 kg",
        measurable_dimension_key="mass_reading",
        measurement_numeric_value="10",
        measurement_unit="kg",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
        temporal=_happened(),
    )


def mq15_box_weighs() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A caixa pesa 10 kg.",
        subject=SemanticEntityMention(text="caixa", kind_hint="thing"),
        attribute_expression="10 kg",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def mq16_owns_50_percent() -> SemanticProposal:
    return SemanticProposal(
        raw_input="João possui 50% da empresa.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="empresa", kind_hint="organization"),
        relation_expression="possui",
        link_semantics=True,
        primitive_hint="relation",
    )


def mq17_room_temperature() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A temperatura do quarto está em 24 °C.",
        subject=SemanticEntityMention(text="temperatura", kind_hint="thing"),
        context=SemanticEntityMention(text="quarto", kind_hint="place"),
        entities_mentioned=[SemanticEntityMention(text="quarto", kind_hint="place")],
        state_expression="24 °C",
        measurement_expression="24 °C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="24",
        measurement_unit="°C",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def mq18_data_usage() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O consumo de dados está em 8 GB.",
        subject=SemanticEntityMention(text="consumo de dados", kind_hint="thing"),
        state_expression="8 GB",
        measurement_expression="8 GB",
        measurable_dimension_key="data_usage",
        measurement_numeric_value="8",
        measurement_unit="GB",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def mq19_invoice_balance_due() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Falta pagar R$ 90 da fatura.",
        subject=SemanticEntityMention(text="fatura", kind_hint="document"),
        state_expression="R$ 90",
        measurement_expression="R$ 90",
        measurable_dimension_key="balance",
        measurement_numeric_value="90",
        measurement_currency_code="BRL",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def mq20_screen_size() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A tela tem 15,6 polegadas.",
        subject=SemanticEntityMention(text="tela", kind_hint="thing"),
        attribute_expression="15,6 polegadas",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def mq21_water_bill_amount() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A conta de água veio R$ 87.",
        subject=SemanticEntityMention(text="conta de água", kind_hint="document"),
        attribute_expression="R$ 87",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def mq22_class_hours() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A disciplina tem 60 horas.",
        subject=SemanticEntityMention(text="disciplina", kind_hint="thing"),
        attribute_expression="60 horas",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def mq23_tank_and_measure() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Medi o tanque e tinha 20 L.",
        object=SemanticEntityMention(text="tanque", kind_hint="thing"),
        action_expression="medi",
        change_semantics=True,
        event_expression="medi tanque",
        state_expression="20 L",
        measurement_expression="20 L",
        measurable_dimension_key="fuel_level",
        measurement_numeric_value="20",
        measurement_unit="L",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mq24_color_regression() -> SemanticProposal:
    return pr4_color()


def mq25_tank_full_state() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O tanque está cheio.",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        state_expression="cheio",
        condition_semantics=True,
        primitive_hint="state",
    )


def mq26_filled_tank_event() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Enchi o tanque com 40 litros.",
        object=SemanticEntityMention(text="tanque", kind_hint="thing"),
        action_expression="enchi",
        change_semantics=True,
        event_expression="enchi tanque",
        primitive_hint="event",
        temporal=_happened(),
    )
