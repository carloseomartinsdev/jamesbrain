"""Modelos wire LLM-facing. Integração — não IR canônica do PKE."""

from __future__ import annotations

import datetime as dt
import json
import re
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pke.interpretation.transport.catalog import ConceptCatalog
from pke.interpretation.transport.normalize import normalize_wire_shape


class WireWeekday(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


WIRE_WEEKDAY_TO_INT: dict[WireWeekday, int] = {
    WireWeekday.MONDAY: 0,
    WireWeekday.TUESDAY: 1,
    WireWeekday.WEDNESDAY: 2,
    WireWeekday.THURSDAY: 3,
    WireWeekday.FRIDAY: 4,
    WireWeekday.SATURDAY: 5,
    WireWeekday.SUNDAY: 6,
}


class WireMoney(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal
    currency: str = "BRL"

    @field_validator("amount", mode="before")
    @classmethod
    def _numeric_amount(cls, value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            cleaned = value.strip().replace(",", ".")
            if re.search(r"[a-zA-Z]", cleaned):
                raise ValueError("amount deve ser numérico, sem texto linguístico")
            try:
                return Decimal(cleaned)
            except InvalidOperation as exc:
                raise ValueError("amount inválido") from exc
        raise ValueError("amount deve ser numérico")


class WireEntityMention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    entity_type: str | None = None
    role: str | None = None
    reference_kind: Literal["named", "contextual", "possessive"] = "named"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _entity_type_kind(self) -> WireEntityMention:
        if self.entity_type is not None and self.entity_type not in ConceptCatalog.entity_types:
            raise ValueError(f"entity_type inválido: {self.entity_type}")
        if self.role is not None and self.role not in ConceptCatalog.roles:
            raise ValueError(f"role inválido: {self.role}")
        return self


class WireIrTime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_text: str = ""
    relative_day: Literal["today", "yesterday", "tomorrow"] | None = None
    weekday: WireWeekday | None = None
    weekday_policy: Literal["next", "previous", "next_strict", "previous_strict"] | None = None
    time_of_day: str | None = None
    precision: str | None = None
    timezone: str | None = None
    relation_to_reference: Literal["before", "after", "during", "habitual"] | None = None
    occurrence_status: Literal["happened", "ongoing", "planned", "habitual"] | None = None
    unknown_reason: Literal["not_provided", "forgotten", "unresolved", "unknown"] | None = None
    tense_evidence: str | None = None
    partial_month: int | None = Field(default=None, ge=1, le=12)
    partial_year: int | None = None


class WireIrFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute: str
    money: WireMoney | None = None
    qualifier: Literal["exact", "approximately", "unknown"] = "exact"
    epistemic_status: Literal["explicit", "inferred", "confirmed", "uncertain", "contradicted"] = (
        "explicit"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def _normalize_money(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if data.get("money") is None and isinstance(data.get("value"), dict):
            value = data["value"]
            if "amount" in value:
                data = {**data, "money": value}
        return data

    @field_validator("attribute")
    @classmethod
    def _attribute_kind(cls, value: str) -> str:
        if value not in ConceptCatalog.attributes:
            raise ValueError(f"attribute inválido: {value}")
        return value

    @model_validator(mode="after")
    def _uncertainty_rubric(self) -> WireIrFact:
        if self.money is None:
            raise ValueError("fact monetário exige money.amount e money.currency")
        approx = self.qualifier == "approximately"
        uncertain = self.epistemic_status == "uncertain"
        if approx and self.qualifier == "exact":
            raise ValueError("approximate/uncertain não pode usar exact")
        if uncertain and self.epistemic_status == "confirmed":
            raise ValueError("uncertain não pode ser confirmed")
        if approx and self.epistemic_status == "confirmed":
            raise ValueError("approximate não pode ser confirmed")
        if uncertain and self.qualifier == "exact":
            raise ValueError("uncertain não pode usar exact")
        if (approx or uncertain) and self.confidence >= 0.8:
            raise ValueError("linguagem incerta exige confidence < 0.8")
        return self


class WireIrState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    dimension: str | None = None
    payload: dict[str, Any] | None = None
    time: WireIrTime = Field(default_factory=WireIrTime)

    @field_validator("value")
    @classmethod
    def _state_value(cls, value: str) -> str:
        if value not in ConceptCatalog.state_values:
            raise ValueError(f"state value inválido: {value}")
        return value

    @field_validator("dimension")
    @classmethod
    def _state_dimension(cls, value: str | None) -> str | None:
        if value is not None and value not in ConceptCatalog.state_dimensions:
            raise ValueError(f"state dimension inválida: {value}")
        return value


class WireIrAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: WireEntityMention
    dimension_key: str
    value_kind: Literal["text", "number", "year", "date", "concept"]
    text_value: str | None = None
    numeric_value: str | None = None
    unit: str | None = None
    year_value: int | None = None
    date_value: str | None = None
    concept_value_id: str | None = None
    is_current: bool = True
    time: WireIrTime = Field(default_factory=WireIrTime)


class WireIrMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: WireEntityMention
    context: WireEntityMention | None = None
    dimension_key: str
    numeric_value: str
    unit: str | None = None
    currency_code: str | None = None
    time: WireIrTime = Field(default_factory=WireIrTime)


class WireIrRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    subject: WireEntityMention
    object: WireEntityMention
    mode: Literal["assert", "terminate", "historical", "deny_current"] = "assert"
    time: WireIrTime = Field(default_factory=WireIrTime)

    @field_validator("type")
    @classmethod
    def _relation_type(cls, value: str) -> str:
        if value not in ConceptCatalog.relation_types:
            raise ValueError(f"relation type inválido: {value}")
        return value


class WireIrEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    action: str | None = None
    status: Literal["scheduled", "completed", "cancelled", "pending"]
    time: WireIrTime = Field(default_factory=WireIrTime)
    participants: list[WireEntityMention] = Field(default_factory=list)
    facts: list[WireIrFact] = Field(default_factory=list)

    @field_validator("type")
    @classmethod
    def _event_type(cls, value: str) -> str:
        if value not in ConceptCatalog.event_types:
            raise ValueError(f"event type inválido: {value}")
        return value

    @field_validator("action")
    @classmethod
    def _action_kind(cls, value: str | None) -> str | None:
        if value is not None and value not in ConceptCatalog.actions:
            raise ValueError(f"action inválida: {value}")
        return value


class WireIrObligation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    cadence: dict[str, Any]
    due: WireIrTime | None = None
    facts: list[WireIrFact] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_cadence(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        cadence = data.get("cadence")
        if isinstance(cadence, dict) and "by_monthday" not in cadence:
            if "by_month_day" in cadence:
                cadence = {**cadence, "by_monthday": cadence.pop("by_month_day")}
                data = {**data, "cadence": cadence}
        return data

    @field_validator("type")
    @classmethod
    def _obligation_type(cls, value: str) -> str:
        if value not in ConceptCatalog.event_types:
            raise ValueError(f"obligation type inválido: {value}")
        return value


class WireIrCorrectionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["event", "measurement", "relation", "state", "attribute"] | None = None
    entity_text: str | None = None
    object_text: str | None = None
    dimension_key: str | None = None
    value_text: str | None = None
    numeric_value: str | None = None
    year: int | None = None
    relation_concept_key: str | None = None
    state_value_key: str | None = None
    action_key: str | None = None
    explicit_assertion_id: str | None = None
    conversation_assertion_id: str | None = None


class WireIrCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["last_event", "explicit"] = "last_event"
    event_id: str | None = None
    fact_id: str | None = None
    facts: list[WireIrFact] = Field(default_factory=list)
    operation: Literal["retract", "replace"] | None = None
    target: WireIrCorrectionTarget | None = None


class WireIngestIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal[
        "record_event",
        "record_state",
        "record_relation",
        "record_attribute",
        "record_measurement",
        "record_obligation",
        "record_intent",
        "correct",
        "none",
    ]
    raw_input: str
    domains: list[str] = Field(default_factory=list)
    entities_mentioned: list[WireEntityMention] = Field(default_factory=list)
    event: WireIrEvent | None = None
    state: WireIrState | None = None
    attribute: WireIrAttribute | None = None
    additional_attributes: list[WireIrAttribute] = Field(default_factory=list)
    measurement: WireIrMeasurement | None = None
    relation: WireIrRelation | None = None
    obligation: WireIrObligation | None = None
    correction: WireIrCorrection | None = None
    missing_hints: list[str] = Field(default_factory=list)

    @field_validator("domains")
    @classmethod
    def _domains(cls, values: list[str]) -> list[str]:
        for key in values:
            if key not in ConceptCatalog.domains:
                raise ValueError(f"domain inválido: {key}")
        return values


class WireQueryTime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_text: str | None = None
    relative_period: (
        Literal[
            "this_month",
            "last_month",
            "this_week",
            "last_week",
            "today",
            "yesterday",
            "now",
        ]
        | None
    ) = None


class WireQuerySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["list", "aggregate", "state", "relation"] = "list"
    entities: list[WireEntityMention] = Field(default_factory=list)
    entity_association: Literal[
        "actor",
        "subject",
        "relation_endpoint",
        "relation_subject",
        "relation_object",
        "event_context",
    ] | None = None
    event_types: list[str] = Field(default_factory=list)
    state_dimensions: list[str] = Field(default_factory=list)
    state_values: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    relation_scope: Literal["current", "historical", "any"] = "current"
    relation_query_kind: (
        Literal[
            "current_boolean",
            "historical_existence",
            "termination_date",
            "held_during",
        ]
        | None
    ) = None
    actions: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    aggregate: Literal["sum", "count", "latest", "none"] = "none"
    hierarchy: Literal["exact", "include_descendants"] = "exact"
    version_policy: Literal["current", "history"] = "current"
    currency: str | None = None
    time: WireQueryTime | None = None
    sort: Literal[
        "event_time_desc",
        "event_time_asc",
        "created_at_desc",
        "created_at_asc",
    ] = "event_time_desc"
    limit: int | None = None

    @field_validator("event_types")
    @classmethod
    def _event_types(cls, values: list[str]) -> list[str]:
        for key in values:
            if key not in ConceptCatalog.event_types:
                raise ValueError(f"query event_type inválido: {key}")
        return values

    @field_validator("facts")
    @classmethod
    def _facts(cls, values: list[str]) -> list[str]:
        for key in values:
            if key not in ConceptCatalog.attributes:
                raise ValueError(f"query fact inválido: {key}")
        return values

    @field_validator("actions")
    @classmethod
    def _actions(cls, values: list[str]) -> list[str]:
        for key in values:
            if key not in ConceptCatalog.actions:
                raise ValueError(f"query action inválida: {key}")
        return values

    @field_validator("relation_types")
    @classmethod
    def _relation_types(cls, values: list[str]) -> list[str]:
        for key in values:
            if key not in ConceptCatalog.relation_types:
                raise ValueError(f"query relation_type inválido: {key}")
        return values

    @field_validator("domains")
    @classmethod
    def _query_domains(cls, values: list[str]) -> list[str]:
        for key in values:
            if key not in ConceptCatalog.domains:
                raise ValueError(f"query domain inválido: {key}")
        return values


class WireQueryIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["query"] = "query"
    raw_input: str
    query: WireQuerySpec


class WireEnvelope(BaseModel):
    """Envelope wire: {ir_kind, ir}. Não é IR canônica."""

    model_config = ConfigDict(extra="forbid")

    ir_kind: Literal["ingest", "query"]
    ir: dict[str, Any]

    @classmethod
    def parse_json(cls, content: str) -> WireEnvelope:
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("envelope deve ser objeto JSON")
        normalized = normalize_wire_shape(payload)
        return cls.model_validate(normalized)

    def parsed_ingest(self) -> WireIngestIR:
        return WireIngestIR.model_validate(self.ir)

    def parsed_query(self) -> WireQueryIR:
        return WireQueryIR.model_validate(self.ir)

    @model_validator(mode="after")
    def _kind_payload(self) -> WireEnvelope:
        if self.ir_kind == "ingest":
            WireIngestIR.model_validate(self.ir)
        else:
            WireQueryIR.model_validate(self.ir)
        return self


def parse_time_of_day(value: str) -> dt.time:
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return dt.datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"time_of_day inválido: {value}")
