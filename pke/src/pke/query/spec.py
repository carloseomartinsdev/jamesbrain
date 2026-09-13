"""Consulta já resolvida. QueryEngine não recebe texto."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

from pke.domain.attributes import AttributeValueKind


class FactVersionPolicy(StrEnum):
    CURRENT = "current"
    HISTORY = "history"


class AttributeQueryMode(StrEnum):
    VALUE_LOOKUP = "value_lookup"
    PROPOSITION = "proposition"
    HISTORICAL_EXISTENCE = "historical_existence"
    SNAPSHOT = "snapshot"


class MeasurementQueryMode(StrEnum):
    LATEST_OBSERVATION = "latest_observation"
    OBSERVATION_AT_TIME = "observation_at_time"
    OBSERVATIONS_IN_RANGE = "observations_in_range"
    VALUE_PROPOSITION = "value_proposition"


class MeasurementValueFilter(BaseModel):
    """Proposition filter for Measurement — Decimal + unit XOR currency."""

    model_config = ConfigDict(extra="forbid")

    numeric_value: Decimal
    unit: str | None = None
    currency_code: str | None = None

    @field_validator("numeric_value", mode="before")
    @classmethod
    def _coerce_numeric(cls, value: object) -> object:
        if value is None or isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float, str)):
            return Decimal(str(value))
        return value

    @model_validator(mode="after")
    def _xor_unit_currency(self) -> MeasurementValueFilter:
        if self.unit is not None and self.currency_code is not None:
            raise ValueError("unit and currency_code must not coexist")
        return self


class AttributeValueFilter(BaseModel):
    """Optional proposition / existence value constraint (semantic equality)."""

    model_config = ConfigDict(extra="forbid")

    value_kind: AttributeValueKind
    text_value: str | None = None
    numeric_value: Decimal | None = None
    unit: str | None = None
    year_value: int | None = None
    date_value: dt.date | None = None
    concept_value_id: str | None = None

    @field_validator("numeric_value", mode="before")
    @classmethod
    def _coerce_numeric(cls, value: object) -> object:
        if value is None or isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float, str)):
            return Decimal(str(value))
        return value


class AggregateKind(StrEnum):
    SUM = "sum"
    COUNT = "count"
    LATEST = "latest"
    NONE = "none"


class HierarchyMode(StrEnum):
    EXACT = "exact"
    INCLUDE_DESCENDANTS = "include_descendants"


class EntityAssociation(StrEnum):
    ACTOR = "actor"
    SUBJECT = "subject"
    RELATION_ENDPOINT = "relation_endpoint"
    RELATION_SUBJECT = "relation_subject"
    RELATION_OBJECT = "relation_object"
    EVENT_CONTEXT = "event_context"


class RelationScope(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"
    ANY = "any"


class RelationQueryKind(StrEnum):
    CURRENT_BOOLEAN = "current_boolean"
    HISTORICAL_EXISTENCE = "historical_existence"
    TERMINATION_DATE = "termination_date"
    HELD_DURING = "held_during"


class SortKey(StrEnum):
    EVENT_TIME_ASC = "event_time_asc"
    EVENT_TIME_DESC = "event_time_desc"
    CREATED_AT_ASC = "created_at_asc"
    CREATED_AT_DESC = "created_at_desc"


class TimeRange(BaseModel):
    """Intervalo absoluto [start, end). Sem 'este mês'."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: dt.datetime
    end: dt.datetime

    @model_validator(mode="after")
    def _half_open(self) -> TimeRange:
        if self.start >= self.end:
            raise ValueError("[start, end) exige start < end")
        return self


class ResolvedQuerySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    event_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    entity_association: EntityAssociation | None = None
    event_type_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    fact_concept_ids: list[str] = Field(default_factory=list)
    domain_ids: list[str] = Field(default_factory=list)
    state_dimension_ids: list[str] = Field(default_factory=list)
    state_value_ids: list[str] = Field(default_factory=list)
    relation_type_ids: list[str] = Field(default_factory=list)
    object_entity_type_ids: list[str] = Field(default_factory=list)
    """Type constraint on the relation object — not an instance id to resolve."""
    relation_scope: RelationScope = RelationScope.CURRENT
    relation_query_kind: RelationQueryKind | None = None
    attribute_dimension_key: str | None = None
    attribute_query_mode: AttributeQueryMode | None = None
    attribute_value_filter: AttributeValueFilter | None = None
    measurement_dimension_key: str | None = None
    measurement_query_mode: MeasurementQueryMode | None = None
    measurement_value_filter: MeasurementValueFilter | None = None
    context_entity_ids: list[str] = Field(default_factory=list)
    event_statuses: list[str] = Field(default_factory=list)
    time_range: TimeRange | None = None
    fact_version_policy: FactVersionPolicy = FactVersionPolicy.CURRENT
    hierarchy: HierarchyMode = HierarchyMode.EXACT
    aggregate: AggregateKind = AggregateKind.NONE
    currency: str | None = None
    sort: SortKey = SortKey.EVENT_TIME_DESC
    limit: int | None = None
