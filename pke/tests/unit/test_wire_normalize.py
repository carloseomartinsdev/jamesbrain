"""Testes I10.2 — normalização wire determinística."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pke.interpretation.models import IngestIR
from pke.interpretation.transport import WireEnvelope, normalize_wire_shape, wire_to_canonical
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _ingest(payload: dict) -> IngestIR:
    normalized = normalize_wire_shape(payload)
    wire = WireEnvelope.model_validate(normalized)
    ir = wire_to_canonical(wire)
    return IngestIR.model_validate(ir.model_dump())


def test_missing_event_time_becomes_empty_original_text() -> None:
    payload = {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "Acho que uns 180",
            "event": {
                "type": "event.vehicle_maintenance",
                "status": "completed",
                "facts": [
                    {
                        "attribute": "attribute.amount",
                        "money": {"amount": 180, "currency": "BRL"},
                        "qualifier": "approximately",
                        "epistemic_status": "uncertain",
                        "confidence": 0.45,
                    }
                ],
            },
        },
    }
    ir = _ingest(payload)
    assert ir.event is not None
    assert ir.event.time.original_text == ""


def test_null_time_object_normalized() -> None:
    payload = {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "x",
            "event": {
                "type": "event.vehicle_maintenance",
                "status": "completed",
                "time": None,
                "facts": [
                    {
                        "attribute": "attribute.amount",
                        "money": {"amount": 180, "currency": "BRL"},
                        "qualifier": "approximately",
                        "epistemic_status": "uncertain",
                        "confidence": 0.5,
                    }
                ],
            },
        },
    }
    ir = _ingest(payload)
    assert ir.event is not None
    assert ir.event.time.original_text == ""


def test_empty_time_dict_gets_original_text() -> None:
    payload = {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "x",
            "event": {
                "type": "event.vehicle_maintenance",
                "status": "completed",
                "time": {},
                "facts": [
                    {
                        "attribute": "attribute.amount",
                        "money": {"amount": 180, "currency": "BRL"},
                        "qualifier": "approximately",
                        "epistemic_status": "uncertain",
                        "confidence": 0.5,
                    }
                ],
            },
        },
    }
    ir = _ingest(payload)
    assert ir.event.time.original_text == ""


def test_null_original_text_not_from_raw_input() -> None:
    payload = {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "Troquei o óleo hoje por 320 reais.",
            "event": {
                "type": "event.vehicle_maintenance",
                "status": "completed",
                "time": {"original_text": None},
                "facts": [
                    {
                        "attribute": "attribute.amount",
                        "money": {"amount": 320, "currency": "BRL"},
                        "qualifier": "exact",
                        "epistemic_status": "explicit",
                        "confidence": 1.0,
                    }
                ],
            },
        },
    }
    ir = _ingest(payload)
    assert ir.event.time.original_text == ""
    assert ir.event.time.original_text != ir.raw_input


def test_money_string_amount_lossless() -> None:
    payload = {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "x",
            "event": {
                "type": "event.vehicle_maintenance",
                "status": "completed",
                "facts": [
                    {
                        "attribute": "attribute.amount",
                        "money": {"amount": "180.50", "currency": "BRL"},
                        "qualifier": "exact",
                        "epistemic_status": "explicit",
                        "confidence": 1.0,
                    }
                ],
            },
        },
    }
    ir = _ingest(payload)
    assert Decimal(str(ir.event.facts[0].value["amount"])) == Decimal("180.50")


def test_linguistic_money_still_rejected() -> None:
    payload = {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "x",
            "event": {
                "type": "event.vehicle_maintenance",
                "status": "completed",
                "facts": [
                    {
                        "attribute": "attribute.amount",
                        "money": {"amount": "uns 180 reais", "currency": "BRL"},
                        "qualifier": "approximately",
                        "epistemic_status": "uncertain",
                        "confidence": 0.4,
                    }
                ],
            },
        },
    }
    with pytest.raises(ValidationError):
        _ingest(payload)


def test_weekday_case_normalization() -> None:
    payload = {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "x",
            "event": {
                "type": "event.appointment",
                "status": "scheduled",
                "time": {"original_text": "quinta", "weekday": "Thursday", "time_of_day": "15:00"},
            },
        },
    }
    ir = _ingest(payload)
    assert ir.event.time.weekday == 3


def test_contradictory_uncertainty_still_rejected() -> None:
    payload = {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "x",
            "event": {
                "type": "event.vehicle_maintenance",
                "status": "completed",
                "facts": [
                    {
                        "attribute": "attribute.amount",
                        "money": {"amount": 180, "currency": "BRL"},
                        "qualifier": "exact",
                        "epistemic_status": "uncertain",
                        "confidence": 0.4,
                    }
                ],
            },
        },
    }
    with pytest.raises(ValidationError):
        _ingest(payload)


def test_value_alias_to_money() -> None:
    payload = {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "x",
            "event": {
                "type": "event.vehicle_maintenance",
                "status": "completed",
                "facts": [
                    {
                        "attribute": "attribute.amount",
                        "value": {"amount": "320", "currency": "BRL"},
                        "qualifier": "exact",
                        "epistemic_status": "explicit",
                        "confidence": 1.0,
                    }
                ],
            },
        },
    }
    ir = _ingest(payload)
    assert Decimal(str(ir.event.facts[0].value["amount"])) == Decimal("320")


def test_reference_kind_explicit_alias_to_named() -> None:
    payload = {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "x",
            "entities_mentioned": [
                {
                    "text": "Dra. Ana",
                    "entity_type": "entity.person",
                    "role": "role.provider",
                    "reference_kind": "explicit",
                }
            ],
            "event": {
                "type": "event.appointment",
                "status": "scheduled",
                "time": {"original_text": "quinta", "weekday": "thursday", "time_of_day": "15:00"},
            },
        },
    }
    ir = _ingest(payload)
    assert ir.entities_mentioned[0].reference_kind.value == "named"


def test_reference_kind_specific_alias_to_named() -> None:
    payload = {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "x",
            "entities_mentioned": [
                {
                    "text": "Corolla",
                    "entity_type": "entity.automobile",
                    "role": "role.subject",
                    "reference_kind": "specific",
                }
            ],
            "event": {
                "type": "event.vehicle_maintenance",
                "status": "completed",
                "time": {"original_text": "hoje", "relative_day": "today"},
                "facts": [
                    {
                        "attribute": "attribute.amount",
                        "money": {"amount": 320, "currency": "BRL"},
                        "qualifier": "exact",
                        "epistemic_status": "explicit",
                        "confidence": 1.0,
                    }
                ],
            },
        },
    }
    ir = _ingest(payload)
    assert ir.entities_mentioned[0].reference_kind.value == "named"


def test_parse_json_applies_normalization() -> None:
    raw = json.dumps(
        {
            "ir_kind": "ingest",
            "ir": {
                "intent": "record_event",
                "raw_input": "x",
                "event": {"type": "event.vehicle_maintenance", "status": "completed"},
            },
        }
    )
    wire = WireEnvelope.parse_json(raw)
    assert wire.parsed_ingest().event is not None
    assert wire.parsed_ingest().event.time.original_text == ""
