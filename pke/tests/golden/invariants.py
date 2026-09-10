"""Invariantes semânticas A–F. Não exigem igualdade byte a byte."""

from __future__ import annotations

from decimal import Decimal

from pke.interpretation.models import IngestIR, QueryIR


def assert_case_a(ir: IngestIR) -> None:
    assert ir.intent.value == "record_event"
    assert ir.event is not None
    assert ir.event.type.key == "event.vehicle_maintenance"
    assert ir.event.action is not None
    assert ir.event.action.key == "action.oil_change"
    assert any(item.text.lower() == "corolla" for item in ir.entities_mentioned)
    assert ir.event.time.original_text
    assert ir.event.time.relative_day is not None
    assert ir.event.time.instant is None
    amount = next(f for f in ir.event.facts if f.attribute.key == "attribute.amount")
    value = amount.value
    raw = value["amount"] if isinstance(value, dict) else value
    assert Decimal(str(raw)) == Decimal("320")
    assert not any(f.attribute.key == "attribute.mileage" for f in ir.event.facts)


def assert_case_b(ir: IngestIR) -> None:
    assert ir.event is not None
    assert ir.event.type.key == "event.appointment"
    assert ir.event.status.value == "scheduled"
    assert ir.event.time.weekday == 3
    assert ir.event.time.time_of_day is not None
    assert ir.event.time.time_of_day.hour == 15
    assert any("ana" in item.text.lower() for item in ir.entities_mentioned)
    assert ir.event.time.instant is None


def assert_case_c(ir: IngestIR) -> None:
    assert ir.obligation is not None
    assert ir.obligation.type.key == "event.recurring_bill"
    assert ir.obligation.cadence.freq == "monthly"
    assert ir.obligation.cadence.by_monthday == 10
    amount = next(f for f in ir.obligation.facts if f.attribute.key == "attribute.amount")
    raw = amount.value["amount"] if isinstance(amount.value, dict) else amount.value
    assert Decimal(str(raw)) == Decimal("129.90")


def assert_case_d1(ir: IngestIR) -> None:
    assert ir.event is not None
    assert any(item.text.lower() == "corolla" for item in ir.entities_mentioned)
    assert ir.event.time.relative_day is not None
    assert ir.event.time.relative_day.value == "today"
    assert ir.event.time.original_text
    amount = next(f for f in ir.event.facts if f.attribute.key == "attribute.amount")
    assert amount.qualifier.value == "approximately"
    assert amount.epistemic_status.value != "explicit" or amount.confidence < 0.8
    assert amount.qualifier.value != "exact"
    assert amount.epistemic_status.value != "confirmed"
    raw = amount.value["amount"] if isinstance(amount.value, dict) else amount.value
    assert Decimal(str(raw)) == Decimal("180")
    assert amount.confidence < 0.8


def assert_case_d2(ir: IngestIR) -> None:
    assert ir.event is not None
    amount = next(f for f in ir.event.facts if f.attribute.key == "attribute.amount")
    assert amount.qualifier.value == "approximately"
    assert amount.epistemic_status.value != "explicit" or amount.confidence < 0.8
    assert amount.qualifier.value != "exact"
    assert amount.epistemic_status.value != "confirmed"
    raw = amount.value["amount"] if isinstance(amount.value, dict) else amount.value
    assert Decimal(str(raw)) == Decimal("180")
    assert amount.confidence < 0.8
    assert ir.event.time.relative_day is None
    assert ir.event.time.instant is None
    assert ir.event.time.date is None
    if ir.event.time.original_text:
        assert "hoje" not in ir.event.time.original_text.lower()


def assert_case_e(ir: IngestIR) -> None:
    assert ir.intent.value == "correct"
    assert ir.correction is not None
    assert ir.correction.strategy.value == "last_event"
    assert ir.correction.fact_id is None
    amount = ir.correction.facts[0]
    raw = amount.value["amount"] if isinstance(amount.value, dict) else amount.value
    assert Decimal(str(raw)) == Decimal("186.50")


def assert_case_f(ir: QueryIR) -> None:
    assert ir.intent == "query"
    assert ir.query.aggregate == "sum"
    assert ir.query.version_policy == "current"
    assert any(item.text.lower() == "corolla" for item in ir.query.entities)
    assert ir.query.entity_association == "subject"
    assert any(ref.key == "event.vehicle_maintenance" for ref in ir.query.event_types)
    assert any(ref.key == "attribute.amount" for ref in ir.query.facts)
    assert ir.query.time is not None
    assert ir.query.time.relative_period is not None
    assert ir.query.time.relative_period.value == "this_month"
    assert ir.query.time.start is None
    assert "506" not in ir.model_dump_json()
