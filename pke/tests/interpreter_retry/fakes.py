"""I12.2 — Scripted provider + payload fixtures for interpreter retry."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from pke.llm.errors import LlmError
from pke.llm.models import LlmCallMetadata, LlmStructuredRequest, LlmStructuredResponse


def wire_ingest_ok(raw: str = "Troquei o óleo do Corolla hoje.") -> dict[str, Any]:
    return {
        "ir_kind": "ingest",
        "ir": {
            "intent": "record_event",
            "raw_input": raw,
            "domains": ["domain.vehicle"],
            "entities_mentioned": [{"text": "Corolla", "entity_type": "entity.automobile"}],
            "event": {
                "type": "event.vehicle_maintenance",
                "action": "action.oil_change",
                "status": "completed",
                "time": {"original_text": "hoje", "relative_day": "today"},
                "facts": [],
            },
        },
    }


def wire_query_ok(raw: str = "Quanto gastei com o Corolla este mês?") -> dict[str, Any]:
    return {
        "ir_kind": "query",
        "ir": {
            "intent": "query",
            "raw_input": raw,
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


def semantic_relation_ok(
    raw: str = "João trabalha na Acme.",
    *,
    subject: str = "João",
    obj: str = "Acme",
) -> dict[str, Any]:
    return {
        "ir_kind": "semantic_proposal",
        "ir": {
            "raw_input": raw,
            "subject": {"text": subject, "kind_hint": "person"},
            "object": {"text": obj, "kind_hint": "organization"},
            "relation_expression": "trabalha na",
            "link_semantics": True,
        },
    }


def semantic_measurement_ok(raw: str = "O sensor mediu 38°C.") -> dict[str, Any]:
    return {
        "ir_kind": "semantic_proposal",
        "ir": {
            "raw_input": raw,
            "subject": {"text": "sensor", "kind_hint": "thing"},
            "measurement_expression": "38°C",
            "measurable_dimension_key": "temperature",
            "measurement_numeric_value": "38",
            "measurement_unit": "°C",
            "measurement_semantics": True,
            "primitive_hint": "measurement",
            "temporal": {"original_text": "", "occurrence_aspect": "happened"},
        },
    }


def semantic_event_measurement_ok(raw: str = "Medi a temperatura e deu 95°C.") -> dict[str, Any]:
    return {
        "ir_kind": "semantic_proposal",
        "ir": {
            "raw_input": raw,
            "action_expression": "medi",
            "event_expression": "medi a temperatura",
            "change_semantics": True,
            "measurement_expression": "95°C",
            "measurable_dimension_key": "temperature",
            "measurement_numeric_value": "95",
            "measurement_unit": "°C",
            "measurement_semantics": True,
            "subject": {"text": "temperatura", "kind_hint": "thing"},
            "primitive_hint": "event",
            "temporal": {"original_text": "", "occurrence_aspect": "happened"},
        },
    }


def semantic_correction_replace(raw: str = "Corrigindo: o Corolla é preto.") -> dict[str, Any]:
    return {
        "ir_kind": "semantic_proposal",
        "ir": {
            "raw_input": raw,
            "utterance_kind": "correct",
            "correction_semantics": True,
            "correction_operation": "replace",
            "correction_target_kind": "attribute",
            "correction_target_entity_text": "Corolla",
            "correction_target_dimension_key": "color",
            "correction_target_value_text": "azul",
            "subject": {"text": "Corolla", "kind_hint": "vehicle"},
            "attribute_expression": "preto",
            "stable_property_semantics": True,
            "primitive_hint": "attribute",
        },
    }


def semantic_correction_retract(raw: str = "Desconsidere o que eu disse sobre o Corolla.") -> dict[str, Any]:
    return {
        "ir_kind": "semantic_proposal",
        "ir": {
            "raw_input": raw,
            "utterance_kind": "correct",
            "correction_semantics": True,
            "correction_operation": "retract",
            "correction_target_kind": "attribute",
            "correction_target_entity_text": "Corolla",
            "correction_target_dimension_key": "color",
            "subject": {"text": "Corolla", "kind_hint": "vehicle"},
            "primitive_hint": "attribute",
        },
    }

def semantic_insufficient(raw: str = "algo") -> dict[str, Any]:
    return {"ir_kind": "semantic_proposal", "ir": {"raw_input": raw}}


def schema_invalid_envelope() -> dict[str, Any]:
    # Missing required raw_input inside ir — fails wire proposal schema
    return {"ir_kind": "semantic_proposal", "ir": {"link_semantics": True}}


Outcome = dict[str, Any] | str | LlmError | Callable[[], dict[str, Any] | str | LlmError]


@dataclass
class ScriptedProvider:
    """Deterministic fault injection. No network."""

    outcomes: list[Outcome]
    calls: list[LlmStructuredRequest] = field(default_factory=list)
    _index: int = 0

    def generate_structured(self, request: LlmStructuredRequest) -> LlmStructuredResponse:
        self.calls.append(request)
        if self._index >= len(self.outcomes):
            raise RuntimeError("ScriptedProvider exhausted outcomes")
        outcome = self.outcomes[self._index]
        self._index += 1
        if callable(outcome):
            outcome = outcome()
        if isinstance(outcome, LlmError):
            raise outcome
        content = outcome if isinstance(outcome, str) else json.dumps(outcome, ensure_ascii=False)
        return LlmStructuredResponse(
            content=content,
            metadata=LlmCallMetadata(
                provider="scripted",
                model="test",
                request_id=f"prov-{self._index}",
                attempts=1,
            ),
        )

    @property
    def call_count(self) -> int:
        return len(self.calls)
