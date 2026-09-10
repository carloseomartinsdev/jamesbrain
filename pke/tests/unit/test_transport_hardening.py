"""Testes offline I10.1 — transport wire, prompt v2, hardening."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext
from pke.interpretation.models import IngestIR, QueryIR
from pke.interpretation.prompts import (
    PROMPT_VERSION_V1,
    PROMPT_VERSION_V2,
    PROMPT_VERSION_V3,
    PROMPT_VERSION_V4,
    build_messages,
    resolve_prompt_module,
)
from pke.interpretation.prompts_v3 import build_messages as build_v3
from pke.interpretation.prompts_v1 import build_messages as build_v1
from pke.interpretation.prompts_v2 import build_messages as build_v2
from pke.interpretation.ontology_view import InterpreterOntologyView
from pke.interpretation.transport import WireEnvelope, WireWeekday, wire_to_canonical
from pke.interpretation.transport.wire import WIRE_WEEKDAY_TO_INT, WireEntityMention
from pke.llm import LlmCallMetadata, LlmStructuredRequest, LlmStructuredResponse
from pke.ontology import OntologyRegistry

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)


@pytest.fixture
def registry() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def view(registry: OntologyRegistry) -> InterpreterOntologyView:
    return InterpreterOntologyView.from_registry(registry)


@pytest.fixture
def ctx() -> InterpretationContext:
    return InterpretationContext(
        user=UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)
    )


def _wire_ingest(*, approximate: bool = False) -> dict:
    fact = {
        "attribute": "attribute.amount",
        "money": {"amount": 180 if approximate else 320, "currency": "BRL"},
        "qualifier": "approximately" if approximate else "exact",
        "epistemic_status": "uncertain" if approximate else "explicit",
        "confidence": 0.45 if approximate else 1.0,
    }
    return {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "placeholder",
            "domains": ["domain.vehicle"],
            "entities_mentioned": [
                {"text": "Corolla", "entity_type": "entity.automobile", "role": "role.subject"}
            ],
            "event": {
                "type": "event.vehicle_maintenance",
                "action": "action.oil_change",
                "status": "completed",
                "time": {"original_text": "hoje", "relative_day": "today"},
                "facts": [fact],
            },
        },
    }


def _wire_query() -> dict:
    return {
        "ir_kind": "query",
        "ir": {
            "intent": "query",
            "raw_input": "placeholder",
            "query": {
                "intent": "aggregate",
                "entities": [{"text": "Corolla", "entity_type": "entity.automobile"}],
                "entity_association": "subject",
                "event_types": ["event.vehicle_maintenance"],
                "facts": ["attribute.amount"],
                "aggregate": "sum",
                "version_policy": "current",
                "time": {"relative_period": "this_month", "original_text": "este mês"},
            },
        },
    }


def _wire_appointment() -> dict:
    return {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": "Tenho dentista quinta às 15h com a Dra. Ana.",
            "entities_mentioned": [
                {"text": "Dra. Ana", "entity_type": "entity.person", "role": "role.provider"}
            ],
            "event": {
                "type": "event.appointment",
                "status": "scheduled",
                "time": {
                    "original_text": "quinta às 15h",
                    "weekday": "thursday",
                    "time_of_day": "15:00",
                },
                "participants": [
                    {"text": "Dra. Ana", "entity_type": "entity.person", "role": "role.provider"}
                ],
            },
        },
    }


class StubProvider:
    def __init__(self, payload: dict | str) -> None:
        self.payload = payload
        self.last_request: LlmStructuredRequest | None = None

    def generate_structured(self, request: LlmStructuredRequest) -> LlmStructuredResponse:
        self.last_request = request
        content = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return LlmStructuredResponse(
            content=content,
            metadata=LlmCallMetadata(provider="stub", model="stub", request_id="stub-1", latency_ms=3),
        )


def test_thursday_maps_to_canonical_weekday_3(registry: OntologyRegistry) -> None:
    envelope = WireEnvelope.model_validate(_wire_appointment())
    ir = wire_to_canonical(envelope)
    assert isinstance(ir, IngestIR)
    assert ir.event is not None
    assert ir.event.time.weekday == 3
    assert WIRE_WEEKDAY_TO_INT[WireWeekday.THURSDAY] == 3


def test_invalid_weekday_rejected(registry: OntologyRegistry) -> None:
    payload = _wire_appointment()
    payload["ir"]["event"]["time"]["weekday"] = "notaday"
    with pytest.raises(ValidationError):
        WireEnvelope.model_validate(payload)


def test_entity_type_hint_rejects_event_concept(registry: OntologyRegistry) -> None:
    with pytest.raises(ValidationError):
        WireEntityMention(text="x", entity_type="event.appointment")


def test_profession_fixture_no_dentista_entity(registry: OntologyRegistry) -> None:
    envelope = WireEnvelope.model_validate(_wire_appointment())
    ir = wire_to_canonical(envelope)
    texts = [m.text.lower() for m in ir.entities_mentioned]
    assert "dentista" not in texts


def test_approximate_money_is_numeric(registry: OntologyRegistry) -> None:
    envelope = WireEnvelope.model_validate(_wire_ingest(approximate=True))
    ir = wire_to_canonical(envelope)
    fact = ir.event.facts[0]
    assert Decimal(str(fact.value["amount"])) == Decimal("180")
    assert fact.value["currency"] == "BRL"


def test_acho_fixture_not_exact_confirmed(registry: OntologyRegistry) -> None:
    envelope = WireEnvelope.model_validate(_wire_ingest(approximate=True))
    ir = wire_to_canonical(envelope)
    fact = ir.event.facts[0]
    assert fact.qualifier.value == "approximately"
    assert fact.epistemic_status.value == "uncertain"
    assert fact.confidence < 0.8


def test_transport_invalid_blocked(registry: OntologyRegistry) -> None:
    bad = _wire_ingest()
    bad["ir"]["event"]["facts"][0]["money"]["amount"] = "uns 180 reais"
    with pytest.raises(ValidationError):
        WireEnvelope.model_validate(bad)


def test_transport_to_canonical_passes_pydantic(registry: OntologyRegistry) -> None:
    envelope = WireEnvelope.model_validate(_wire_ingest())
    ir = wire_to_canonical(envelope)
    canonical = IngestIR.model_validate(ir.model_dump())
    assert canonical.event is not None


def test_prompt_v1_identifiable(view: InterpreterOntologyView, ctx: InterpretationContext) -> None:
    msgs = build_v1("oi", ctx, view)
    assert "pke.interpret.v1" in msgs[1].content
    assert resolve_prompt_module(PROMPT_VERSION_V1).PROMPT_VERSION == "pke.interpret.v1"


def test_prompt_v4_selected_by_default_and_v2_v3_explicit(
    registry: OntologyRegistry, ctx: InterpretationContext, view: InterpreterOntologyView
) -> None:
    msgs = build_v3("oi", ctx, view)
    assert "pke.interpret.v3" in msgs[1].content
    assert "semantic_proposal" in msgs[0].content
    interpreter = DeepSeekInterpreter(StubProvider(_wire_ingest()), registry)
    assert interpreter.prompt_version == PROMPT_VERSION_V4
    assert "measurement_semantics" in build_messages(
        "oi", ctx, view, prompt_version=PROMPT_VERSION_V4
    )[0].content
    interpreter_v3 = DeepSeekInterpreter(
        StubProvider(_wire_ingest()), registry, prompt_version=PROMPT_VERSION_V3
    )
    assert interpreter_v3.prompt_version == PROMPT_VERSION_V3
    interpreter_v2 = DeepSeekInterpreter(
        StubProvider(_wire_ingest()), registry, prompt_version=PROMPT_VERSION_V2
    )
    assert interpreter_v2.prompt_version == PROMPT_VERSION_V2


def test_compact_ontology_keeps_keys(view: InterpreterOntologyView) -> None:
    compact = view.compact_grouped()
    assert "event.vehicle_maintenance" in compact["event_types"]
    assert compact["event_types"]["event.vehicle_maintenance"]


def test_v2_prompt_smaller_than_v1(view: InterpreterOntologyView, ctx: InterpretationContext) -> None:
    v1_len = len(build_v1("teste", ctx, view)[1].content)
    v2_len = len(build_v2("teste", ctx, view)[1].content)
    assert v2_len < v1_len


def test_deepseek_v2_interpreter_end_to_end(registry: OntologyRegistry, ctx: InterpretationContext) -> None:
    raw = "Troquei o óleo do Corolla hoje por 320 reais."
    ir = DeepSeekInterpreter(StubProvider(_wire_ingest()), registry).interpret(raw, ctx)
    assert ir.raw_input == raw
    assert ir.event is not None


def test_deepseek_v1_still_works(registry: OntologyRegistry, ctx: InterpretationContext) -> None:
    v1_payload = {
        "ir_kind": "ingest",
        "ingest": {
            "intent": "record_event",
            "raw_input": "x",
            "domains": [{"key": "domain.vehicle"}],
            "entities_mentioned": [{"text": "Corolla", "type_hint": {"key": "entity.automobile"}}],
            "event": {
                "type": {"key": "event.vehicle_maintenance"},
                "action": {"key": "action.oil_change"},
                "status": "completed",
                "time": {"original_text": "hoje", "relative_day": "today"},
                "facts": [
                    {
                        "attribute": {"key": "attribute.amount"},
                        "value": {"amount": "320", "currency": "BRL"},
                        "qualifier": "exact",
                        "epistemic_status": "explicit",
                        "confidence": 1.0,
                    }
                ],
            },
        },
    }
    ir = DeepSeekInterpreter(
        StubProvider(v1_payload), registry, prompt_version=PROMPT_VERSION_V1
    ).interpret("x", ctx)
    assert isinstance(ir, IngestIR)


def test_llm_layer_no_core_runtime_imports() -> None:
    roots = [
        Path(__file__).parents[2] / "src" / "pke" / "llm",
        Path(__file__).parents[2] / "src" / "pke" / "interpretation",
    ]
    files: list[Path] = []
    for root in roots:
        files.extend(root.rglob("*.py"))
    for path in files:
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        assert "pke.persist" not in text
        assert "from pke.query" not in text
        assert "import pke.query" not in text
        assert "open_sqlite" not in text


def test_wire_query_maps_to_query_ir(registry: OntologyRegistry) -> None:
    ir = wire_to_canonical(WireEnvelope.model_validate(_wire_query()))
    assert isinstance(ir, QueryIR)
    assert ir.query.aggregate == "sum"
