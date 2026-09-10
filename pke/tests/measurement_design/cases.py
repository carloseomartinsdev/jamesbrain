"""I11.15 — Measurement design case matrix."""

from __future__ import annotations

from dataclasses import dataclass

from tests.measurement_design import fixtures as mf
from tests.measurement_design.fixtures import DesignPrimitive, InformationLoss


@dataclass(frozen=True)
class MeasurementDesignCase:
    id: str
    factory: object
    design: DesignPrimitive
    # secondary design when utterance is multi-primitive (e.g. Event + Measurement)
    secondary: DesignPrimitive | None = None
    # loss if CURRENT model has no Measurement and forces State/Attribute/Event only
    current_model_loss: InformationLoss = InformationLoss.NONE
    notes: str = ""
    category: str = "mandatory"


MANDATORY: list[MeasurementDesignCase] = [
    MeasurementDesignCase(
        "M1",
        mf.m1_tank_content,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        notes="fuel/content level 20L — not capacity Attribute; State loses observation series",
    ),
    MeasurementDesignCase(
        "M2",
        mf.m2_tank_capacity,
        DesignPrimitive.ATTRIBUTE,
        notes="capacity descriptive property",
    ),
    MeasurementDesignCase(
        "M3",
        mf.m3_battery_charge,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        notes="battery_charge=80%",
    ),
    MeasurementDesignCase(
        "M4",
        mf.m4_battery_depleted,
        DesignPrimitive.STATE,
        notes="depleted condition — not a quantity observation",
    ),
    MeasurementDesignCase(
        "M5",
        mf.m5_battery_capacity,
        DesignPrimitive.ATTRIBUTE,
        current_model_loss=InformationLoss.NON_CRITICAL,
        notes="capacity Attribute (mAh); may lack unit canon today",
    ),
    MeasurementDesignCase(
        "M6",
        mf.m6_odometer,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        notes="odometer reading",
    ),
    MeasurementDesignCase(
        "M7",
        mf.m7_fuel_efficiency,
        DesignPrimitive.ATTRIBUTE,
        notes="habitual efficiency property — not a single observation",
    ),
    MeasurementDesignCase(
        "M8",
        mf.m8_temperature,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        notes="temperature observation",
    ),
    MeasurementDesignCase(
        "M9",
        mf.m9_motor_overheated,
        DesignPrimitive.STATE,
        notes="condition; Measurement≠State",
    ),
    MeasurementDesignCase(
        "M10",
        mf.m10_measure_temperature_event,
        DesignPrimitive.EVENT,
        notes="measure act without result → Event only",
    ),
    MeasurementDesignCase(
        "M11",
        mf.m11_measure_and_result,
        DesignPrimitive.EVENT,
        secondary=DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        notes="same utterance may assert Event + Measurement (no enrichment required)",
    ),
    MeasurementDesignCase(
        "M12",
        mf.m12_account_balance,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        notes="reported balance observation (not contractual Attribute)",
    ),
    MeasurementDesignCase(
        "M13",
        mf.m13_rent_amount,
        DesignPrimitive.ATTRIBUTE,
        notes="contractual rent property — not Measurement",
    ),
    MeasurementDesignCase(
        "M14",
        mf.m14_paid_rent,
        DesignPrimitive.EVENT,
        notes="payment Event quantity — not Measurement",
    ),
    MeasurementDesignCase(
        "M15",
        mf.m15_bill_came,
        DesignPrimitive.ATTRIBUTE,
        notes="bill amount as document property (Attribute); not observation series",
    ),
    MeasurementDesignCase(
        "M16",
        mf.m16_purchase_price,
        DesignPrimitive.EVENT,
        notes="acquisition Event value / historical cost — not Measurement",
    ),
    MeasurementDesignCase(
        "M17",
        mf.m17_inventory_bottles,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        notes="count observation quantity_on_hand",
    ),
    MeasurementDesignCase(
        "M18",
        mf.m18_table_width,
        DesignPrimitive.ATTRIBUTE,
        notes="descriptive width",
    ),
    MeasurementDesignCase(
        "M19",
        mf.m19_joao_height,
        DesignPrimitive.ATTRIBUTE,
        notes="height remains Attribute — Measurement would damage semantics",
    ),
    MeasurementDesignCase(
        "M20",
        mf.m20_notebook_weight,
        DesignPrimitive.ATTRIBUTE,
        notes="descriptive weight Attribute",
    ),
]


OPEN: list[MeasurementDesignCase] = [
    MeasurementDesignCase("MQ1", mf.mq1_house_area, DesignPrimitive.ATTRIBUTE, category="open"),
    MeasurementDesignCase("MQ2", mf.mq2_model_year, DesignPrimitive.ATTRIBUTE, category="open"),
    MeasurementDesignCase("MQ3", mf.mq3_fridge_white, DesignPrimitive.ATTRIBUTE, category="open"),
    MeasurementDesignCase("MQ4", mf.mq4_person_weight, DesignPrimitive.ATTRIBUTE, category="open"),
    MeasurementDesignCase("MQ5", mf.mq5_tank_capacity_alt, DesignPrimitive.ATTRIBUTE, category="open"),
    MeasurementDesignCase(
        "MQ6",
        mf.mq6_fuel_level_yesterday,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        category="open",
        notes="historical observation time",
    ),
    MeasurementDesignCase(
        "MQ7",
        mf.mq7_battery_40,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        category="open",
    ),
    MeasurementDesignCase(
        "MQ8",
        mf.mq8_speed,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        category="open",
    ),
    MeasurementDesignCase(
        "MQ9",
        mf.mq9_water_pressure,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        category="open",
    ),
    MeasurementDesignCase(
        "MQ10",
        mf.mq10_stock_count,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        category="open",
    ),
    MeasurementDesignCase("MQ11", mf.mq11_paid_electricity, DesignPrimitive.EVENT, category="open"),
    MeasurementDesignCase("MQ12", mf.mq12_bought_milk, DesignPrimitive.EVENT, category="open"),
    MeasurementDesignCase("MQ13", mf.mq13_weighed_package, DesignPrimitive.EVENT, category="open"),
    MeasurementDesignCase(
        "MQ14",
        mf.mq14_scale_marked,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        category="open",
        notes="instrument reading observation",
    ),
    MeasurementDesignCase(
        "MQ15",
        mf.mq15_box_weighs,
        DesignPrimitive.ATTRIBUTE,
        category="open",
        notes="descriptive weight — contrast MQ14",
    ),
    MeasurementDesignCase("MQ16", mf.mq16_owns_50_percent, DesignPrimitive.RELATION, category="open"),
    MeasurementDesignCase(
        "MQ17",
        mf.mq17_room_temperature,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        category="open",
        notes="entity=temperature reading, context=room",
    ),
    MeasurementDesignCase(
        "MQ18",
        mf.mq18_data_usage,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        category="open",
    ),
    MeasurementDesignCase(
        "MQ19",
        mf.mq19_invoice_balance_due,
        DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.NON_CRITICAL,
        category="open",
        notes="remaining amount observation; could shade Attribute of bill",
    ),
    MeasurementDesignCase("MQ20", mf.mq20_screen_size, DesignPrimitive.ATTRIBUTE, category="open"),
    MeasurementDesignCase("MQ21", mf.mq21_water_bill_amount, DesignPrimitive.ATTRIBUTE, category="open"),
    MeasurementDesignCase("MQ22", mf.mq22_class_hours, DesignPrimitive.ATTRIBUTE, category="open"),
    MeasurementDesignCase(
        "MQ23",
        mf.mq23_tank_and_measure,
        DesignPrimitive.EVENT,
        secondary=DesignPrimitive.MEASUREMENT,
        current_model_loss=InformationLoss.CRITICAL,
        category="open",
    ),
    MeasurementDesignCase("MQ24", mf.mq24_color_regression, DesignPrimitive.ATTRIBUTE, category="open"),
    MeasurementDesignCase("MQ25", mf.mq25_tank_full_state, DesignPrimitive.STATE, category="open"),
    MeasurementDesignCase(
        "MQ26",
        mf.mq26_filled_tank_event,
        DesignPrimitive.EVENT,
        category="open",
        notes="fill Event with quantity as Event payload — not Measurement supersession",
    ),
]


ALL_CASES = MANDATORY + OPEN
