"""I11.15.1 — Measurement routing + multi-primitive + v9 contract freeze tests."""

from __future__ import annotations

import pytest

from pke.interpretation.semantic.measurement_contract import (
    CANONICAL_TABLE_NAME,
    CREATED_AT_IS_OBSERVATION_TIME,
    LEGACY_STATE_OBSERVED_QUANTITY_POLICY,
    MEASUREMENT_AUTO_SUPERSEDES,
    MEASUREMENT_HAS_IS_CURRENT,
    PARTIAL_MATERIALIZATION_POLICY,
    PERCENTAGE_AS_FRACTION,
    PRIMARY_ENTITY_REQUIRED_FOR_MATERIALIZATION,
    SCHEMA_V9_AUTHORIZED,
    SCHEMA_V9_REQUIRED,
    UNIT_AND_CURRENCY_COEXIST,
)
from pke.interpretation.semantic.models import PrimitiveKind, SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.persistability import assess_persistability
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.router import collect_assertions, route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from tests.attribute_design import fixtures as af
from tests.measurement_design import fixtures as mf


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _ongoing() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="ongoing")


def _happened() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="happened")


# --- MR fixtures ---


def mr1() -> SemanticProposal:
    return af.at2_house_area()


def mr2() -> SemanticProposal:
    return af.at3_notebook_weight()


def mr3() -> SemanticProposal:
    return mf.m5_battery_capacity()


def mr4() -> SemanticProposal:
    return mf.m13_rent_amount()


def mr5() -> SemanticProposal:
    return mf.m14_paid_rent()


def mr6() -> SemanticProposal:
    return mf.m16_purchase_price()


def mr7() -> SemanticProposal:
    return af.at11_tank_20_liters()


def mr8() -> SemanticProposal:
    return mf.m3_battery_charge()


def mr9() -> SemanticProposal:
    return mf.m6_odometer()


def mr10() -> SemanticProposal:
    return mf.m8_temperature()


def mr11() -> SemanticProposal:
    return mf.m12_account_balance()


def mr12() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Há 12 garrafas na geladeira.",
        object=SemanticEntityMention(text="garrafas", kind_hint="thing"),
        entities_mentioned=[SemanticEntityMention(text="geladeira", kind_hint="appliance")],
        measurement_expression="12",
        measurable_dimension_key="inventory_count",
        measurement_numeric_value="12",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def mr13() -> SemanticProposal:
    return mf.m4_battery_depleted()


def mr14() -> SemanticProposal:
    return mf.m9_motor_overheated()


def mr15() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O tanque está vazio.",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        state_expression="vazio",
        condition_semantics=True,
        primitive_hint="state",
    )


def mr16() -> SemanticProposal:
    return mf.m10_measure_temperature_event()


def mr17() -> SemanticProposal:
    return mf.mq13_weighed_package()


def mp1() -> SemanticProposal:
    return mf.m11_measure_and_result()


def mp2() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Olhei o tanque e ele estava com 20 litros.",
        object=SemanticEntityMention(text="tanque", kind_hint="thing"),
        action_expression="olhei",
        change_semantics=True,
        event_expression="olhei tanque",
        measurement_expression="20 litros",
        measurable_dimension_key="fuel_level",
        measurement_numeric_value="20",
        measurement_unit="L",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mp3() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Pesei a caixa: 10 kg.",
        object=SemanticEntityMention(text="caixa", kind_hint="thing"),
        action_expression="pesei",
        change_semantics=True,
        event_expression="pesei caixa",
        measurement_expression="10 kg",
        measurable_dimension_key="mass_reading",
        measurement_numeric_value="10",
        measurement_unit="kg",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mp4() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Consultei o saldo e tinha R$ 2500.",
        object=SemanticEntityMention(text="saldo", kind_hint="document"),
        action_expression="consultei",
        change_semantics=True,
        event_expression="consultei saldo",
        measurement_expression="2500",
        measurable_dimension_key="balance",
        measurement_numeric_value="2500",
        measurement_currency_code="BRL",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mp5() -> SemanticProposal:
    """Instrument reading — Measurement only (sensor as source/context, not measure Event)."""
    return SemanticProposal(
        raw_input="O sensor mediu 38 °C.",
        subject=SemanticEntityMention(text="sensor", kind_hint="thing"),
        measurement_expression="38 °C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="38",
        measurement_unit="°C",
        measurement_semantics=True,
        # No change_semantics — reading report, not user measurement act
        primitive_hint="measurement",
        temporal=_happened(),
    )


MR_CASES = [
    ("MR1", mr1, PrimitiveKind.ATTRIBUTE),
    ("MR2", mr2, PrimitiveKind.ATTRIBUTE),
    ("MR3", mr3, PrimitiveKind.ATTRIBUTE),
    ("MR4", mr4, PrimitiveKind.ATTRIBUTE),
    ("MR5", mr5, PrimitiveKind.EVENT),
    ("MR6", mr6, PrimitiveKind.EVENT),
    ("MR7", mr7, PrimitiveKind.MEASUREMENT),
    ("MR8", mr8, PrimitiveKind.MEASUREMENT),
    ("MR9", mr9, PrimitiveKind.MEASUREMENT),
    ("MR10", mr10, PrimitiveKind.MEASUREMENT),
    ("MR11", mr11, PrimitiveKind.MEASUREMENT),
    ("MR12", mr12, PrimitiveKind.MEASUREMENT),
    ("MR13", mr13, PrimitiveKind.STATE),
    ("MR14", mr14, PrimitiveKind.STATE),
    ("MR15", mr15, PrimitiveKind.STATE),
    ("MR16", mr16, PrimitiveKind.EVENT),
    ("MR17", mr17, PrimitiveKind.EVENT),
]


@pytest.mark.parametrize("case_id,factory,expected", MR_CASES, ids=[c[0] for c in MR_CASES])
def test_mr_routing(case_id, factory, expected) -> None:
    routed, _ = route_primitive(factory())
    assert routed is expected


@pytest.mark.parametrize(
    "case_id,factory",
    [("MP1", mp1), ("MP2", mp2), ("MP3", mp3), ("MP4", mp4)],
)
def test_mp_event_plus_measurement(case_id, factory) -> None:
    proposal = factory()
    primary, _ = route_primitive(proposal)
    frames = collect_assertions(proposal)
    kinds = {f.primitive for f in frames}
    assert primary is PrimitiveKind.EVENT
    assert PrimitiveKind.EVENT in kinds
    assert PrimitiveKind.MEASUREMENT in kinds
    assert len(frames) == 2


def test_mp5_sensor_reading_is_measurement_only() -> None:
    primary, _ = route_primitive(mp5())
    frames = collect_assertions(mp5())
    assert primary is PrimitiveKind.MEASUREMENT
    assert [f.primitive for f in frames] == [PrimitiveKind.MEASUREMENT]


def test_number_unit_does_not_auto_route_to_measurement() -> None:
    """Attribute quantity must remain Attribute despite number+unit."""
    house = mr1()
    assert "200" in house.raw_input or "m" in (house.attribute_expression or "")
    assert not house.measurement_semantics
    assert route_primitive(house)[0] is PrimitiveKind.ATTRIBUTE


def _materializable_event_plus_measurement() -> SemanticProposal:
    """Event with catalog-resolvable action + explicit Measurement (partial materialization).

    MP1 ('medi') is multi-primitive but Event action is not in CORE aliases yet —
    this fixture proves COMMIT_VALID_INDEPENDENTLY when Event *is* materializable.
    """
    return SemanticProposal(
        raw_input="Troquei a embreagem e o odômetro estava em 125000 km.",
        object=SemanticEntityMention(text="embreagem", kind_hint="thing"),
        entities_mentioned=[SemanticEntityMention(text="Corolla", kind_hint="vehicle")],
        action_expression="troquei",
        change_semantics=True,
        event_expression="troquei a embreagem",
        measurement_expression="125000 km",
        measurable_dimension_key="odometer",
        measurement_numeric_value="125000",
        measurement_unit="km",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def test_partial_materialization_event_and_measurement_both_wire() -> None:
    proposal = _materializable_event_plus_measurement()
    result = resolve_proposal(proposal)
    assert result.primitive is PrimitiveKind.EVENT
    frames = collect_assertions(proposal)
    assert {f.primitive for f in frames} == {PrimitiveKind.EVENT, PrimitiveKind.MEASUREMENT}
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert outcome.ir.event is not None
    assert outcome.ir.measurement is not None
    assessment = assess_persistability(result)
    assert assessment.wire_allowed is True


def test_measurement_alone_wires_when_entity_present() -> None:
    outcome = proposal_to_canonical_ir(mr7())
    assert outcome.ir is not None
    assert outcome.ir.measurement is not None
    result = resolve_proposal(mr7())
    assessment = assess_persistability(result)
    assert assessment.wire_allowed is True


def test_measurement_without_entity_not_materializable() -> None:
    from pke.interpretation.semantic.models import SemanticProposal

    bare = SemanticProposal(
        raw_input="Está 38 graus.",
        measurement_expression="38",
        measurable_dimension_key="temperature",
        measurement_numeric_value="38",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="measurement",
    )
    outcome = proposal_to_canonical_ir(bare)
    assert outcome.ir is None
    assessment = assess_persistability(resolve_proposal(bare))
    assert assessment.wire_allowed is False
    assert "measurement_entity_required" in assessment.notes


def test_v9_contract_freezes() -> None:
    assert MEASUREMENT_HAS_IS_CURRENT is False
    assert MEASUREMENT_AUTO_SUPERSEDES is False
    assert CREATED_AT_IS_OBSERVATION_TIME is False
    assert PERCENTAGE_AS_FRACTION is False
    assert UNIT_AND_CURRENCY_COEXIST is False
    assert PRIMARY_ENTITY_REQUIRED_FOR_MATERIALIZATION is True
    assert LEGACY_STATE_OBSERVED_QUANTITY_POLICY == "NO_BACKFILL"
    assert PARTIAL_MATERIALIZATION_POLICY == "COMMIT_VALID_INDEPENDENTLY"
    assert CANONICAL_TABLE_NAME == "measurements"
    assert SCHEMA_V9_REQUIRED is True
    assert SCHEMA_V9_AUTHORIZED is True


def test_schema_core_unchanged() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67


def test_primitive_kind_measurement_persistable_when_complete() -> None:
    assert PrimitiveKind.MEASUREMENT.value == "measurement"
    outcome = proposal_to_canonical_ir(mr8())
    assert outcome.ir is not None
    assert outcome.ir.measurement is not None


def test_multi_primitive_metrics_zero_false_extra() -> None:
    false_extra = 0
    missing = 0
    total = 0
    for factory in (mp1, mp2, mp3, mp4):
        total += 1
        frames = collect_assertions(factory())
        kinds = {f.primitive for f in frames}
        if PrimitiveKind.STATE in kinds or PrimitiveKind.ATTRIBUTE in kinds:
            false_extra += 1
        if PrimitiveKind.EVENT not in kinds or PrimitiveKind.MEASUREMENT not in kinds:
            missing += 1
    assert total == 4
    assert false_extra == 0
    assert missing == 0


# --- Additional ≥20 routing corpus (I11.15.1 §62) ---


def rc_attr_vehicle_engine() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O motor tem 2.0 litros de cilindrada.",
        subject=SemanticEntityMention(text="motor", kind_hint="thing"),
        attribute_expression="2.0 litros",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def rc_attr_home_ceiling() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O teto tem 2,70 m de altura.",
        subject=SemanticEntityMention(text="teto", kind_hint="thing"),
        attribute_expression="2,70 m",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def rc_attr_doc_pages() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O contrato tem 12 páginas.",
        subject=SemanticEntityMention(text="contrato", kind_hint="document"),
        attribute_expression="12 páginas",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def rc_attr_service_duration() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A consulta dura 30 minutos.",
        subject=SemanticEntityMention(text="consulta", kind_hint="document"),
        attribute_expression="30 minutos",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def rc_attr_device_screen() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A tela tem 15 polegadas.",
        subject=SemanticEntityMention(text="tela", kind_hint="thing"),
        attribute_expression="15 polegadas",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def rc_meas_vehicle_tire() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O pneu está com 2,2 bar.",
        subject=SemanticEntityMention(text="pneu", kind_hint="thing"),
        measurement_expression="2,2 bar",
        measurable_dimension_key="tire_pressure",
        measurement_numeric_value="2.2",
        measurement_unit="bar",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=_ongoing(),
    )


def rc_meas_battery_device() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O celular está em 40%.",
        subject=SemanticEntityMention(text="celular", kind_hint="thing"),
        measurement_expression="40%",
        measurable_dimension_key="battery_charge",
        measurement_numeric_value="40",
        measurement_unit="%",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=_ongoing(),
    )


def rc_meas_temp_env() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A temperatura do quarto está em 24 °C.",
        subject=SemanticEntityMention(text="quarto", kind_hint="place"),
        context=SemanticEntityMention(text="quarto", kind_hint="place"),
        measurement_expression="24 °C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="24",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=_ongoing(),
    )


def rc_meas_utility_water() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O hidrômetro está em 4521 m³.",
        subject=SemanticEntityMention(text="hidrômetro", kind_hint="thing"),
        measurement_expression="4521 m³",
        measurable_dimension_key="water_meter",
        measurement_numeric_value="4521",
        measurement_unit="m³",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=_ongoing(),
    )


def rc_meas_health_reading() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A pressão está em 12/8.",
        subject=SemanticEntityMention(text="pressão", kind_hint="thing"),
        measurement_expression="12/8",
        measurable_dimension_key="blood_pressure",
        measurement_numeric_value="12",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=_ongoing(),
    )


def rc_evt_finance_paid() -> SemanticProposal:
    return mf.m14_paid_rent()


def rc_evt_vehicle_fuel() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Abasteci 40 litros.",
        action_expression="abasteci",
        change_semantics=True,
        event_expression="abasteci 40 litros",
        primitive_hint="event",
        temporal=_happened(),
    )


def rc_evt_service_paid() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Paguei R$ 200 pela revisão.",
        object=SemanticEntityMention(text="revisão", kind_hint="document"),
        action_expression="paguei",
        change_semantics=True,
        event_expression="paguei revisão",
        primitive_hint="event",
        temporal=_happened(),
    )


def rc_evt_inventory_bought() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Comprei 6 garrafas de água.",
        object=SemanticEntityMention(text="garrafas", kind_hint="thing"),
        action_expression="comprei",
        change_semantics=True,
        event_expression="comprei garrafas",
        primitive_hint="event",
        temporal=_happened(),
    )


def rc_evt_home_installed() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Instalei o ar-condicionado de 12000 BTUs.",
        object=SemanticEntityMention(text="ar-condicionado", kind_hint="appliance"),
        action_expression="instalei",
        change_semantics=True,
        event_expression="instalei ar-condicionado",
        primitive_hint="event",
        temporal=_happened(),
    )


def rc_amb_finance_balance_prop() -> SemanticProposal:
    """Borderline: balance as Measurement observation (MR11 decision)."""
    return mr11()


def rc_amb_inventory_count() -> SemanticProposal:
    """Borderline: count observation → Measurement when measurement_semantics."""
    return mr12()


def rc_amb_bill_amount() -> SemanticProposal:
    return mf.m15_bill_came()


def rc_amb_number_without_obs() -> SemanticProposal:
    """Surface number+unit in raw text only — must not auto-route Measurement."""
    return SemanticProposal(
        raw_input="Tem 200 m² mencionados no anúncio.",
        # no attribute/measurement/state cues — number+unit alone is not Measurement
        primitive_hint="unknown",
    )


def rc_amb_state_vs_level() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A bateria está fraca.",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        state_expression="fraca",
        condition_semantics=True,
        primitive_hint="state",
    )


EXTRA_RC_CASES = [
    ("RC1", rc_attr_vehicle_engine, PrimitiveKind.ATTRIBUTE),
    ("RC2", rc_attr_home_ceiling, PrimitiveKind.ATTRIBUTE),
    ("RC3", rc_attr_doc_pages, PrimitiveKind.ATTRIBUTE),
    ("RC4", rc_attr_service_duration, PrimitiveKind.ATTRIBUTE),
    ("RC5", rc_attr_device_screen, PrimitiveKind.ATTRIBUTE),
    ("RC6", rc_meas_vehicle_tire, PrimitiveKind.MEASUREMENT),
    ("RC7", rc_meas_battery_device, PrimitiveKind.MEASUREMENT),
    ("RC8", rc_meas_temp_env, PrimitiveKind.MEASUREMENT),
    ("RC9", rc_meas_utility_water, PrimitiveKind.MEASUREMENT),
    ("RC10", rc_meas_health_reading, PrimitiveKind.MEASUREMENT),
    ("RC11", rc_evt_finance_paid, PrimitiveKind.EVENT),
    ("RC12", rc_evt_vehicle_fuel, PrimitiveKind.EVENT),
    ("RC13", rc_evt_service_paid, PrimitiveKind.EVENT),
    ("RC14", rc_evt_inventory_bought, PrimitiveKind.EVENT),
    ("RC15", rc_evt_home_installed, PrimitiveKind.EVENT),
    ("RC16", rc_amb_finance_balance_prop, PrimitiveKind.MEASUREMENT),
    ("RC17", rc_amb_inventory_count, PrimitiveKind.MEASUREMENT),
    ("RC18", rc_amb_bill_amount, PrimitiveKind.ATTRIBUTE),
    ("RC19", rc_amb_number_without_obs, PrimitiveKind.UNKNOWN),
    ("RC20", rc_amb_state_vs_level, PrimitiveKind.STATE),
]


@pytest.mark.parametrize("case_id,factory,expected", EXTRA_RC_CASES, ids=[c[0] for c in EXTRA_RC_CASES])
def test_extra_routing_corpus(case_id, factory, expected) -> None:
    routed, _ = route_primitive(factory())
    assert routed is expected


def test_routing_safety_metrics_zero() -> None:
    """§64–65: no false collapses; number+unit never auto-routes Measurement."""
    false_attr = false_state = false_event = false_rel = false_type = 0
    attr_false_m = state_false_m = event_false_m = rel_false_m = type_false_m = 0
    auto_nu = 0
    for case_id, factory, expected in MR_CASES + EXTRA_RC_CASES:
        got, _ = route_primitive(factory())
        p = factory()
        if expected is PrimitiveKind.MEASUREMENT and got is PrimitiveKind.ATTRIBUTE:
            false_attr += 1
        if expected is PrimitiveKind.MEASUREMENT and got is PrimitiveKind.STATE:
            false_state += 1
        if expected is PrimitiveKind.MEASUREMENT and got is PrimitiveKind.EVENT:
            false_event += 1
        if expected is PrimitiveKind.ATTRIBUTE and got is PrimitiveKind.MEASUREMENT:
            attr_false_m += 1
        if expected is PrimitiveKind.STATE and got is PrimitiveKind.MEASUREMENT:
            state_false_m += 1
        if expected is PrimitiveKind.EVENT and got is PrimitiveKind.MEASUREMENT:
            event_false_m += 1
        if (
            not p.measurement_semantics
            and (p.measurement_numeric_value or p.measurement_unit)
            and got is PrimitiveKind.MEASUREMENT
        ):
            auto_nu += 1
        # number+unit in attribute expression without measurement_semantics
        if (
            not p.measurement_semantics
            and expected is PrimitiveKind.ATTRIBUTE
            and got is PrimitiveKind.MEASUREMENT
        ):
            auto_nu += 1
    assert false_attr == false_state == false_event == 0
    assert attr_false_m == state_false_m == event_false_m == 0
    assert auto_nu == 0
    _ = (false_rel, false_type, rel_false_m, type_false_m)  # reserved categories unused here
