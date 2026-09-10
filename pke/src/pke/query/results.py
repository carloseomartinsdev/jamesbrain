"""Resultado estruturado. Sem texto de UI."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pke.query.spec import AggregateKind, FactVersionPolicy, HierarchyMode, SortKey


class TemporalCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INDETERMINATE = "indeterminate"


class UnknownTemporalContributor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    fact_id: str | None = None
    value: Any = None
    currency: str | None = None


class QueryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str | None = None
    fact_id: str | None = None
    entity_ids: list[str] = Field(default_factory=list)
    value: Any = None
    currency: str | None = None
    event_time: str | None = None
    created_at: str | None = None
    source_id: str | None = None
    supersedes_id: str | None = None
    is_current: bool = True


class AggregateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AggregateKind
    value: Decimal | int | None = None
    currency: str | None = None
    contributing_fact_ids: list[str] = Field(default_factory=list)
    contributing_event_ids: list[str] = Field(default_factory=list)
    temporal_completeness: TemporalCompleteness = TemporalCompleteness.COMPLETE
    unknown_temporal_contributors: list[UnknownTemporalContributor] = Field(default_factory=list)
    latest_known_event_id: str | None = None
    latest_known_event_time: str | None = None
    indeterminate_event_count: int = 0


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sets: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    expanded_event_type_ids: list[str] = Field(default_factory=list)
    expanded_action_ids: list[str] = Field(default_factory=list)
    version_policy: FactVersionPolicy
    aggregation: AggregateKind
    ordering: SortKey
    hierarchy: HierarchyMode
    time_interval: str = "[start, end)"


class CurrentStateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_id: str
    dimension_key: str
    value_key: str
    payload: Any = None


class CurrentRelationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation_id: str
    relation_key: str
    subject_entity_id: str
    object_entity_id: str
    is_current: bool = True
    object_label: str | None = None


class AttributeValueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value_kind: str
    text_value: str | None = None
    numeric_value: Decimal | None = None
    unit: str | None = None
    year_value: int | None = None
    date_value: Any = None
    concept_value_id: str | None = None
    support_count: int = 1
    assertion_ids: list[str] = Field(default_factory=list)
    dimension_key: str | None = None


class MeasurementValueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numeric_value: Decimal
    unit: str | None = None
    currency_code: str | None = None
    support_count: int = 1
    measurement_ids: list[str] = Field(default_factory=list)
    observed_at: str | None = None


class QueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[QueryItem] = Field(default_factory=list)
    aggregate: AggregateResult | None = None
    matched_count: int = 0
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    plan: QueryPlan
    warnings: list[str] = Field(default_factory=list)
    provenance_fact_ids: list[str] = Field(default_factory=list)
    temporal_completeness: TemporalCompleteness = TemporalCompleteness.COMPLETE
    temporal_membership_unknown: bool = False
    current_state_id: str | None = None
    current_state_value: str | None = None
    state_dimension_key: str | None = None
    state_value_key: str | None = None
    current_states: list[CurrentStateItem] = Field(default_factory=list)
    indeterminate_state_count: int = 0
    current_relations: list[CurrentRelationItem] = Field(default_factory=list)
    relation_answer: Literal["yes", "no", "unknown"] | None = None
    indeterminate_relation_count: int = 0
    attribute_status: str | None = None
    attribute_dimension_key: str | None = None
    attribute_values: list[AttributeValueItem] = Field(default_factory=list)
    attribute_proposition_answer: (
        Literal["yes", "no", "unknown", "ambiguous", "temporally_unknown"] | None
    ) = None
    attribute_assertion_ids: list[str] = Field(default_factory=list)
    measurement_status: str | None = None
    measurement_dimension_key: str | None = None
    measurement_query_mode: str | None = None
    measurement_values: list[MeasurementValueItem] = Field(default_factory=list)
    measurement_proposition_answer: (
        Literal["yes", "unknown", "ambiguous", "temporally_unknown"] | None
    ) = None
    measurement_ids: list[str] = Field(default_factory=list)
    measurement_unknown_temporal_count: int = 0
