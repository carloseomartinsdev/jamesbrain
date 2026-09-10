"""I11.14 — CP1–CP30 + open cross-primitive corpus (deterministic SemanticProposals)."""

from __future__ import annotations

from pke.interpretation.semantic.models import (
    PrimitiveKind,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from tests.attribute_design import as_fixtures as asf
from tests.attribute_design import fixtures as af
from tests.event_roles import fixtures as erf
from tests.semantic_audit.harness import CorpusCase, GapKind
from tests.semantic_resolution.fixtures import pr3_employment, pr5_door_open


def _ongoing() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="ongoing")


def _happened() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="happened")


# --- mandatory CP factories ---


def cp1_tank_capacity() -> SemanticProposal:
    return af.at12_tank_capacity_50()


def cp2_tank_observed() -> SemanticProposal:
    return af.at11_tank_20_liters()


def cp3_corolla_silver() -> SemanticProposal:
    return af.at1_corolla_silver()


def cp4_corolla_dirty() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla está sujo.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        state_expression="sujo",
        condition_semantics=True,
        primitive_hint="state",
        temporal=_ongoing(),
    )


def cp5_corolla_is_car() -> SemanticProposal:
    return af.at14_corolla_is_car()


def cp6_employment() -> SemanticProposal:
    return pr3_employment()


def cp7_joao_doctor() -> SemanticProposal:
    return SemanticProposal(
        raw_input="João é médico.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        attribute_expression="médico",
        stable_property_semantics=True,
        classification_semantics=False,
        primitive_hint="attribute",
    )


def cp8_manufacturer() -> SemanticProposal:
    return af.at13_manufacturer_toyota()


def cp9_corolla_broke() -> SemanticProposal:
    return asf.as4_corolla_broke()


def cp10_corolla_broken() -> SemanticProposal:
    return asf.as3_corolla_broken()


def cp11_bill_overdue() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A conta está vencida.",
        subject=SemanticEntityMention(text="conta", kind_hint="document"),
        state_expression="vencida",
        condition_semantics=True,
        primitive_hint="state",
    )


def cp12_bill_due_day_10() -> SemanticProposal:
    """Descriptive due-date property — must NOT route as due_status=overdue."""
    return SemanticProposal(
        raw_input="A conta vence dia 10.",
        subject=SemanticEntityMention(text="conta", kind_hint="document"),
        attribute_expression="vence dia 10",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def cp13_warranty_december() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A garantia vence em dezembro.",
        subject=SemanticEntityMention(text="garantia", kind_hint="document"),
        attribute_expression="vence em dezembro",
        stable_property_semantics=True,
        primitive_hint="attribute",
        temporal=SemanticTime(original_text="dezembro", partial_month=12),
    )


def cp14_battery_80() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A bateria está com 80%.",
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


def cp15_battery_capacity() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A bateria tem capacidade de 5000 mAh.",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        attribute_expression="capacidade 5000 mAh",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def cp16_rent_amount() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O aluguel é R$ 550.",
        subject=SemanticEntityMention(text="aluguel", kind_hint="document"),
        attribute_expression="R$ 550",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def cp17_paid_rent() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Paguei R$ 550 no aluguel.",
        object=SemanticEntityMention(text="aluguel", kind_hint="document"),
        action_expression="paguei",
        change_semantics=True,
        event_expression="paguei aluguel",
        primitive_hint="event",
        temporal=_happened(),
    )


def cp18_corolla_mine() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla é meu.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        object=SemanticEntityMention(text="eu", kind_hint="person"),
        relation_expression="é meu",
        link_semantics=True,
        primitive_hint="relation",
    )


def cp19_corolla_garage() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla está na garagem.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        object=SemanticEntityMention(text="garagem", kind_hint="place"),
        relation_expression="está na",
        link_semantics=True,
        primitive_hint="relation",
    )


def cp20_resides_fortaleza() -> SemanticProposal:
    return SemanticProposal(
        raw_input="João mora em Fortaleza.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="Fortaleza", kind_hint="place"),
        relation_expression="mora em",
        link_semantics=True,
        primitive_hint="relation",
    )


def cp21_table_wood() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A mesa é de madeira.",
        subject=SemanticEntityMention(text="mesa", kind_hint="thing"),
        attribute_expression="madeira",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def cp22_file_pdf() -> SemanticProposal:
    return asf.tc_file_pdf()


def cp23_fridge_electrolux() -> SemanticProposal:
    return asf.tc_fridge_electrolux()


def cp24_house_new() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A casa é nova.",
        subject=SemanticEntityMention(text="casa", kind_hint="place"),
        attribute_expression="nova",
        stable_property_semantics=True,
        classification_semantics=False,
        primitive_hint="attribute",
    )


def cp25_door_open() -> SemanticProposal:
    return pr5_door_open()


def cp26_joao_opened_door() -> SemanticProposal:
    return erf.er3_joao_open_door()


def cp27_door_opened() -> SemanticProposal:
    return erf.er4_door_opened_intransitive()


def cp28_historical_employment() -> SemanticProposal:
    return SemanticProposal(
        raw_input="João já trabalhou na Acme.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="Acme", kind_hint="organization"),
        relation_expression="trabalhou na",
        link_semantics=True,
        primitive_hint="relation",
        temporal=SemanticTime(original_text="já", occurrence_aspect="happened"),
        lifecycle_cue="end",
    )


def cp29_employment_termination() -> SemanticProposal:
    return SemanticProposal(
        raw_input="João não trabalha mais na Acme.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="Acme", kind_hint="organization"),
        relation_expression="trabalha na",
        link_semantics=True,
        negation=True,
        lifecycle_cue="end",
        primitive_hint="relation",
    )


def cp30_never_worked() -> SemanticProposal:
    """Denial/correction of prior relation — not ordinary termination."""
    return SemanticProposal(
        raw_input="João nunca trabalhou na Acme.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="Acme", kind_hint="organization"),
        relation_expression="trabalhou na",
        link_semantics=True,
        negation=True,
        lifecycle_cue="deny",
        primitive_hint="relation",
    )


# --- open corpus (≥20) ---


def op1_odometer() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O odômetro marca 125000 km.",
        subject=SemanticEntityMention(text="odômetro", kind_hint="thing"),
        state_expression="125000 km",
        measurement_expression="125000 km",
        measurable_dimension_key="odometer",
        measurement_numeric_value="125000",
        measurement_unit="km",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def op2_temperature() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A temperatura está em 38°C.",
        subject=SemanticEntityMention(text="temperatura", kind_hint="thing"),
        state_expression="38°C",
        measurement_expression="38°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="38",
        measurement_unit="°C",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def op3_account_balance() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A conta está com saldo de R$ 1200.",
        subject=SemanticEntityMention(text="conta", kind_hint="document"),
        state_expression="saldo R$ 1200",
        measurement_expression="R$ 1200",
        measurable_dimension_key="balance",
        measurement_numeric_value="1200",
        measurement_currency_code="BRL",
        measurement_semantics=True,
        condition_semantics=True,
        primitive_hint="measurement",
    )


def op4_appointment() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Tenho consulta amanhã.",
        action_expression="consulta",
        change_semantics=True,
        event_expression="consulta",
        primitive_hint="event",
        temporal=SemanticTime(original_text="amanhã", occurrence_aspect="planned"),
    )


def op5_paid_bill() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Paguei a conta de luz.",
        object=SemanticEntityMention(text="conta de luz", kind_hint="document"),
        action_expression="paguei",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def op6_bought_laptop() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Comprei um notebook.",
        object=SemanticEntityMention(text="notebook", kind_hint="thing"),
        action_expression="comprei",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def op7_studies_at() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Maria estuda na UFC.",
        subject=SemanticEntityMention(text="Maria", kind_hint="person"),
        object=SemanticEntityMention(text="UFC", kind_hint="organization"),
        relation_expression="estuda na",
        link_semantics=True,
        primitive_hint="relation",
    )


def op8_battery_low() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A bateria do celular está fraca.",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        state_expression="fraca",
        condition_semantics=True,
        primitive_hint="state",
    )


def op9_wifi_connected() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Wi-Fi está conectado.",
        subject=SemanticEntityMention(text="Wi-Fi", kind_hint="thing"),
        state_expression="conectado",
        condition_semantics=True,
        primitive_hint="state",
    )


def op10_doc_valid_until() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O documento é válido até 2028.",
        subject=SemanticEntityMention(text="documento", kind_hint="document"),
        attribute_expression="válido até 2028",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def op11_doc_expired() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O documento está vencido.",
        subject=SemanticEntityMention(text="documento", kind_hint="document"),
        state_expression="vencido",
        condition_semantics=True,
        primitive_hint="state",
    )


def op12_corolla_cost() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla custou R$ 80 mil.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        action_expression="custou",
        change_semantics=True,
        event_expression="custou",
        primitive_hint="event",
        temporal=_happened(),
    )


def op13_bill_came_550() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A conta veio R$ 550.",
        subject=SemanticEntityMention(text="conta", kind_hint="document"),
        attribute_expression="R$ 550",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def op14_oil_change_due() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A troca de óleo está atrasada.",
        subject=SemanticEntityMention(text="troca de óleo", kind_hint="thing"),
        state_expression="atrasada",
        condition_semantics=True,
        primitive_hint="state",
    )


def op15_lives_with_parents() -> SemanticProposal:
    return SemanticProposal(
        raw_input="João mora com os pais.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="pais", kind_hint="person"),
        relation_expression="mora com",
        link_semantics=True,
        primitive_hint="relation",
    )


def op16_parked_mall() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O carro está estacionado no shopping.",
        subject=SemanticEntityMention(text="carro", kind_hint="vehicle"),
        object=SemanticEntityMention(text="shopping", kind_hint="place"),
        relation_expression="estacionado no",
        link_semantics=True,
        primitive_hint="relation",
    )


def op17_fridge_white() -> SemanticProposal:
    return af.at10_fridge_white()


def op18_replaced_brakes() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei as pastilhas de freio.",
        object=SemanticEntityMention(text="pastilhas de freio", kind_hint="thing"),
        action_expression="troquei",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def op19_has_two_kids() -> SemanticProposal:
    """Borderline: family relation vs quantity attribute — prefer Relation."""
    return SemanticProposal(
        raw_input="João tem dois filhos.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="filhos", kind_hint="person"),
        relation_expression="tem",
        link_semantics=True,
        primitive_hint="relation",
    )


def op20_meeting_3pm() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Reunião às 15h.",
        event_expression="reunião",
        change_semantics=True,
        primitive_hint="event",
        temporal=SemanticTime(original_text="15h", occurrence_aspect="planned"),
    )


def op21_password_expired() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A senha está expirada.",
        subject=SemanticEntityMention(text="senha", kind_hint="thing"),
        state_expression="expirada",
        condition_semantics=True,
        primitive_hint="state",
    )


def op22_screen_cracked() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A tela está rachada.",
        subject=SemanticEntityMention(text="tela", kind_hint="thing"),
        state_expression="rachada",
        condition_semantics=True,
        primitive_hint="state",
    )


def op23_person_weight() -> SemanticProposal:
    return SemanticProposal(
        raw_input="João pesa 70 kg.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        attribute_expression="70 kg",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def op24_is_brazilian() -> SemanticProposal:
    """Borderline nationality — classification-like; prefer TYPE routing-only."""
    return SemanticProposal(
        raw_input="João é brasileiro.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        attribute_expression="brasileiro",
        classification_semantics=True,
        primitive_hint="type",
    )


def op25_owns_two_cars() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Eu tenho dois carros.",
        subject=SemanticEntityMention(text="eu", kind_hint="person"),
        object=SemanticEntityMention(text="carros", kind_hint="vehicle"),
        relation_expression="tenho",
        link_semantics=True,
        primitive_hint="relation",
    )


def _pk(*kinds: PrimitiveKind) -> tuple[PrimitiveKind, ...]:
    return kinds


MANDATORY_CASES: list[CorpusCase] = [
    CorpusCase("CP1", cp1_tank_capacity, PrimitiveKind.ATTRIBUTE, _pk(PrimitiveKind.STATE)),
    CorpusCase("CP2", cp2_tank_observed, PrimitiveKind.MEASUREMENT, _pk(PrimitiveKind.ATTRIBUTE), gap=GapKind.MEASUREMENT),
    CorpusCase("CP3", cp3_corolla_silver, PrimitiveKind.ATTRIBUTE, _pk(PrimitiveKind.STATE, PrimitiveKind.TYPE)),
    CorpusCase(
        "CP4",
        cp4_corolla_dirty,
        PrimitiveKind.STATE,
        _pk(PrimitiveKind.ATTRIBUTE),
        allow_unresolved_persist=True,
        gap=GapKind.ONTOLOGY,
        notes="condition dirty — not color Attribute",
    ),
    CorpusCase(
        "CP5",
        cp5_corolla_is_car,
        PrimitiveKind.TYPE,
        _pk(PrimitiveKind.ATTRIBUTE),
        must_not_wire=True,
        gap=GapKind.REPRESENTATION,
    ),
    CorpusCase("CP6", cp6_employment, PrimitiveKind.RELATION, _pk(PrimitiveKind.STATE, PrimitiveKind.ATTRIBUTE)),
    CorpusCase(
        "CP7",
        cp7_joao_doctor,
        PrimitiveKind.ATTRIBUTE,
        _pk(PrimitiveKind.TYPE, PrimitiveKind.STATE),
        allow_unresolved_persist=True,
        must_not_wire=True,
        gap=GapKind.REPRESENTATION,
        notes="occupation — Attribute-shaped route, non-materializable",
    ),
    CorpusCase("CP8", cp8_manufacturer, PrimitiveKind.RELATION, _pk(PrimitiveKind.ATTRIBUTE)),
    CorpusCase("CP9", cp9_corolla_broke, PrimitiveKind.EVENT, _pk(PrimitiveKind.STATE)),
    CorpusCase("CP10", cp10_corolla_broken, PrimitiveKind.STATE, _pk(PrimitiveKind.EVENT)),
    CorpusCase("CP11", cp11_bill_overdue, PrimitiveKind.STATE, _pk(PrimitiveKind.ATTRIBUTE)),
    CorpusCase(
        "CP12",
        cp12_bill_due_day_10,
        PrimitiveKind.ATTRIBUTE,
        _pk(PrimitiveKind.STATE),
        allow_unresolved_persist=True,
        gap=GapKind.REPRESENTATION,
        notes="due-date property ≠ overdue State",
    ),
    CorpusCase(
        "CP13",
        cp13_warranty_december,
        PrimitiveKind.ATTRIBUTE,
        _pk(PrimitiveKind.EVENT, PrimitiveKind.STATE),
        allow_unresolved_persist=True,
        gap=GapKind.TEMPORAL,
    ),
    CorpusCase(
        "CP14",
        cp14_battery_80,
        PrimitiveKind.MEASUREMENT,
        _pk(PrimitiveKind.ATTRIBUTE),
        allow_unresolved_persist=True,
        gap=GapKind.MEASUREMENT,
    ),
    CorpusCase(
        "CP15",
        cp15_battery_capacity,
        PrimitiveKind.ATTRIBUTE,
        _pk(PrimitiveKind.STATE),
        allow_unresolved_persist=True,
        gap=GapKind.MEASUREMENT,
        notes="mAh capacity — Attribute intent; unit may block materialization",
    ),
    CorpusCase(
        "CP16",
        cp16_rent_amount,
        PrimitiveKind.ATTRIBUTE,
        _pk(PrimitiveKind.EVENT),
        allow_unresolved_persist=True,
        gap=GapKind.REPRESENTATION,
    ),
    CorpusCase("CP17", cp17_paid_rent, PrimitiveKind.EVENT, _pk(PrimitiveKind.ATTRIBUTE)),
    CorpusCase("CP18", cp18_corolla_mine, PrimitiveKind.RELATION, _pk(PrimitiveKind.ATTRIBUTE)),
    CorpusCase(
        "CP19",
        cp19_corolla_garage,
        PrimitiveKind.RELATION,
        _pk(PrimitiveKind.ATTRIBUTE),
        allow_unresolved_persist=True,
        gap=GapKind.ONTOLOGY,
    ),
    CorpusCase("CP20", cp20_resides_fortaleza, PrimitiveKind.RELATION, _pk(PrimitiveKind.STATE, PrimitiveKind.ATTRIBUTE)),
    CorpusCase(
        "CP21",
        cp21_table_wood,
        PrimitiveKind.ATTRIBUTE,
        _pk(PrimitiveKind.RELATION, PrimitiveKind.TYPE),
        allow_unresolved_persist=True,
        gap=GapKind.REPRESENTATION,
    ),
    CorpusCase(
        "CP22",
        cp22_file_pdf,
        PrimitiveKind.TYPE,
        _pk(PrimitiveKind.ATTRIBUTE),
        must_not_wire=True,
        gap=GapKind.REPRESENTATION,
    ),
    CorpusCase(
        "CP23",
        cp23_fridge_electrolux,
        PrimitiveKind.RELATION,
        _pk(PrimitiveKind.ATTRIBUTE),
        allow_unresolved_persist=True,
        gap=GapKind.ONTOLOGY,
        notes="brand≠manufacturer identity not proven",
    ),
    CorpusCase(
        "CP24",
        cp24_house_new,
        PrimitiveKind.ATTRIBUTE,
        _pk(PrimitiveKind.STATE),
        allow_unresolved_persist=True,
        gap=GapKind.ONTOLOGY,
    ),
    CorpusCase("CP25", cp25_door_open, PrimitiveKind.STATE, _pk(PrimitiveKind.EVENT, PrimitiveKind.ATTRIBUTE)),
    CorpusCase("CP26", cp26_joao_opened_door, PrimitiveKind.EVENT, _pk(PrimitiveKind.STATE)),
    CorpusCase("CP27", cp27_door_opened, PrimitiveKind.EVENT, _pk(PrimitiveKind.STATE)),
    CorpusCase(
        "CP28",
        cp28_historical_employment,
        PrimitiveKind.RELATION,
        _pk(PrimitiveKind.EVENT, PrimitiveKind.STATE),
        allow_unresolved_persist=True,
    ),
    CorpusCase(
        "CP29",
        cp29_employment_termination,
        PrimitiveKind.RELATION,
        _pk(PrimitiveKind.STATE, PrimitiveKind.EVENT),
        allow_unresolved_persist=True,
    ),
    CorpusCase(
        "CP30",
        cp30_never_worked,
        PrimitiveKind.RELATION,
        _pk(PrimitiveKind.EVENT, PrimitiveKind.STATE),
        allow_unresolved_persist=True,
        gap=GapKind.CORRECTION,
        notes="deny ≠ termination — CORRECTION_ENGINE_DEBT",
    ),
]


OPEN_CASES: list[CorpusCase] = [
    CorpusCase("OP1", op1_odometer, PrimitiveKind.MEASUREMENT, _pk(PrimitiveKind.ATTRIBUTE), True, gap=GapKind.MEASUREMENT, category="open"),
    CorpusCase("OP2", op2_temperature, PrimitiveKind.MEASUREMENT, _pk(PrimitiveKind.ATTRIBUTE), True, gap=GapKind.MEASUREMENT, category="open"),
    CorpusCase("OP3", op3_account_balance, PrimitiveKind.MEASUREMENT, _pk(PrimitiveKind.ATTRIBUTE), True, gap=GapKind.MEASUREMENT, category="open"),
    CorpusCase("OP4", op4_appointment, PrimitiveKind.EVENT, _pk(PrimitiveKind.STATE), True, gap=GapKind.TEMPORAL, category="open"),
    CorpusCase("OP5", op5_paid_bill, PrimitiveKind.EVENT, _pk(PrimitiveKind.ATTRIBUTE), category="open"),
    CorpusCase("OP6", op6_bought_laptop, PrimitiveKind.EVENT, _pk(PrimitiveKind.RELATION), category="open"),
    CorpusCase("OP7", op7_studies_at, PrimitiveKind.RELATION, _pk(PrimitiveKind.STATE), True, gap=GapKind.ONTOLOGY, category="open"),
    CorpusCase("OP8", op8_battery_low, PrimitiveKind.STATE, _pk(PrimitiveKind.ATTRIBUTE), True, gap=GapKind.ONTOLOGY, category="open"),
    CorpusCase("OP9", op9_wifi_connected, PrimitiveKind.STATE, _pk(PrimitiveKind.ATTRIBUTE), True, gap=GapKind.ONTOLOGY, category="open"),
    CorpusCase("OP10", op10_doc_valid_until, PrimitiveKind.ATTRIBUTE, _pk(PrimitiveKind.STATE), True, gap=GapKind.TEMPORAL, category="open"),
    CorpusCase("OP11", op11_doc_expired, PrimitiveKind.STATE, _pk(PrimitiveKind.ATTRIBUTE), True, gap=GapKind.ONTOLOGY, category="open"),
    CorpusCase("OP12", op12_corolla_cost, PrimitiveKind.EVENT, _pk(PrimitiveKind.ATTRIBUTE), category="open"),
    CorpusCase("OP13", op13_bill_came_550, PrimitiveKind.ATTRIBUTE, _pk(PrimitiveKind.EVENT), True, gap=GapKind.REPRESENTATION, category="open"),
    CorpusCase("OP14", op14_oil_change_due, PrimitiveKind.STATE, _pk(PrimitiveKind.EVENT), True, gap=GapKind.ONTOLOGY, category="open"),
    CorpusCase("OP15", op15_lives_with_parents, PrimitiveKind.RELATION, _pk(PrimitiveKind.ATTRIBUTE), True, gap=GapKind.ONTOLOGY, category="open"),
    CorpusCase("OP16", op16_parked_mall, PrimitiveKind.RELATION, _pk(PrimitiveKind.STATE, PrimitiveKind.ATTRIBUTE), True, gap=GapKind.ONTOLOGY, category="open"),
    CorpusCase("OP17", op17_fridge_white, PrimitiveKind.ATTRIBUTE, _pk(PrimitiveKind.STATE, PrimitiveKind.TYPE), category="open"),
    CorpusCase("OP18", op18_replaced_brakes, PrimitiveKind.EVENT, _pk(PrimitiveKind.STATE), category="open"),
    CorpusCase("OP19", op19_has_two_kids, PrimitiveKind.RELATION, _pk(PrimitiveKind.ATTRIBUTE), True, gap=GapKind.ONTOLOGY, category="open"),
    CorpusCase("OP20", op20_meeting_3pm, PrimitiveKind.EVENT, _pk(PrimitiveKind.STATE), True, gap=GapKind.TEMPORAL, category="open"),
    CorpusCase("OP21", op21_password_expired, PrimitiveKind.STATE, _pk(PrimitiveKind.ATTRIBUTE), True, gap=GapKind.ONTOLOGY, category="open"),
    CorpusCase("OP22", op22_screen_cracked, PrimitiveKind.STATE, _pk(PrimitiveKind.EVENT, PrimitiveKind.ATTRIBUTE), True, gap=GapKind.ONTOLOGY, category="open"),
    CorpusCase("OP23", op23_person_weight, PrimitiveKind.ATTRIBUTE, _pk(PrimitiveKind.STATE), category="open"),
    CorpusCase(
        "OP24",
        op24_is_brazilian,
        PrimitiveKind.TYPE,
        _pk(PrimitiveKind.ATTRIBUTE, PrimitiveKind.STATE),
        must_not_wire=True,
        gap=GapKind.REPRESENTATION,
        category="open",
    ),
    CorpusCase("OP25", op25_owns_two_cars, PrimitiveKind.RELATION, _pk(PrimitiveKind.ATTRIBUTE), True, gap=GapKind.ONTOLOGY, category="open"),
]


ALL_CASES: list[CorpusCase] = MANDATORY_CASES + OPEN_CASES


# Query safety probes (utterance_kind forced to query in harness)
QUERY_PROBES: list[tuple[str, object, PrimitiveKind]] = [
    ("Q_ATTR", cp3_corolla_silver, PrimitiveKind.ATTRIBUTE),  # rewritten below
    ("Q_STATE", cp10_corolla_broken, PrimitiveKind.STATE),
    ("Q_REL", cp8_manufacturer, PrimitiveKind.RELATION),
    ("Q_EVENT", cp26_joao_opened_door, PrimitiveKind.EVENT),
    ("Q_TYPE", cp5_corolla_is_car, PrimitiveKind.TYPE),
]


def query_attr_color() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Qual a cor do Corolla?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="cor",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def query_state_broken() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla está quebrado?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        state_expression="quebrado",
        condition_semantics=True,
        primitive_hint="state",
    )


def query_rel_manufacturer() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Quem é o fabricante do Corolla?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        object=SemanticEntityMention(text="fabricante", kind_hint="organization"),
        relation_expression="fabricante",
        link_semantics=True,
        primitive_hint="relation",
    )


def query_event_clutch() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Já troquei a embreagem?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="embreagem", kind_hint="thing"),
        action_expression="troquei",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def query_type_car() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla é um carro?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="carro",
        classification_semantics=True,
        primitive_hint="type",
    )


QUERY_SAFETY_CASES: list[CorpusCase] = [
    CorpusCase("QS1", query_attr_color, PrimitiveKind.ATTRIBUTE, _pk(PrimitiveKind.STATE, PrimitiveKind.EVENT)),
    CorpusCase("QS2", query_state_broken, PrimitiveKind.STATE, _pk(PrimitiveKind.ATTRIBUTE, PrimitiveKind.EVENT)),
    CorpusCase("QS3", query_rel_manufacturer, PrimitiveKind.RELATION, _pk(PrimitiveKind.ATTRIBUTE)),
    CorpusCase("QS4", query_event_clutch, PrimitiveKind.EVENT, _pk(PrimitiveKind.STATE, PrimitiveKind.ATTRIBUTE)),
    CorpusCase("QS5", query_type_car, PrimitiveKind.TYPE, _pk(PrimitiveKind.ATTRIBUTE), must_not_wire=True),
]
