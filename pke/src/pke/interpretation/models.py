"""Representação intermediária validável. A LLM (futura) só produz isto."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pke.domain.ontology import ConceptRef
from pke.domain.value_objects import (
    Confidence,
    DayPeriod,
    EpistemicStatus,
    EventStatus,
    Qualifier,
    Recurrence,
    RelativeDay,
    TimePrecision,
    WeekdayPolicy,
)
from pke.domain.temporal_knowledge import (
    OccurrenceStatus,
    RelationToReference,
    TemporalUnknownReason,
)


class IngestIntent(StrEnum):
    RECORD_EVENT = "record_event"
    RECORD_STATE = "record_state"
    RECORD_RELATION = "record_relation"
    RECORD_ATTRIBUTE = "record_attribute"
    RECORD_MEASUREMENT = "record_measurement"
    RECORD_OBLIGATION = "record_obligation"
    RECORD_INTENT = "record_intent"
    CORRECT = "correct"
    NONE = "none"


class CorrectionStrategy(StrEnum):
    """Estratégia contextual de resolução — não é conceito persistente."""

    LAST_EVENT = "last_event"
    EXPLICIT = "explicit"


class MentionReferenceKind(StrEnum):
    """Instance vs class/type constraint.

    NAMED is lexical identity. CONTEXTUAL is situational. POSSESSIVE is owned-by-speaker.
    CLASS is not an instance to resolve — it constrains targets by entity type.
    """

    NAMED = "named"
    CONTEXTUAL = "contextual"
    POSSESSIVE = "possessive"
    CLASS = "class"


class EntityMention(BaseModel):
    """Menção linguística. O Interpreter não inventa ID persistente."""

    model_config = ConfigDict(extra="forbid")

    text: str
    type_hint: ConceptRef | None = None
    role: ConceptRef | None = None
    suggested_aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    known_entity_id: str | None = None
    reference_kind: MentionReferenceKind = MentionReferenceKind.NAMED


MentionedEntity = EntityMention


class IrFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute: ConceptRef
    value: Any
    qualifier: Qualifier = Qualifier.EXACT
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    epistemic_status: EpistemicStatus = EpistemicStatus.EXPLICIT


class IrTime(BaseModel):
    """Tempo na IR: o texto original permanece mesmo com data absoluta."""

    model_config = ConfigDict(extra="forbid")

    original_text: str
    interpretation: str | None = None
    date: dt.date | None = None
    time_of_day: dt.time | None = None
    instant: dt.datetime | None = None
    period_start: dt.datetime | None = None
    period_end: dt.datetime | None = None
    recurrence: Recurrence | None = None
    precision: TimePrecision | None = None
    timezone: str | None = None
    confidence: Confidence | None = None
    reference_at: dt.datetime | None = None
    reference_timezone: str | None = None
    relative_day: RelativeDay | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    weekday_policy: WeekdayPolicy | None = None
    day_period: DayPeriod | None = None
    relation_to_reference: RelationToReference | None = None
    occurrence_status: OccurrenceStatus | None = None
    unknown_reason: TemporalUnknownReason | None = None
    tense_evidence: str | None = None
    partial_month: int | None = Field(default=None, ge=1, le=12)
    partial_year: int | None = None


class IrEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ConceptRef
    action: ConceptRef | None = None
    status: EventStatus
    time: IrTime
    participants: list[EntityMention] = Field(default_factory=list)
    facts: list[IrFact] = Field(default_factory=list)


class IrState(BaseModel):
    """Asserção de condição — value concept + dimensão opcional + payload."""

    model_config = ConfigDict(extra="forbid")

    value: ConceptRef
    dimension: ConceptRef | None = None
    payload: Any | None = None
    time: IrTime = Field(default_factory=lambda: IrTime(original_text=""))


class IrAttribute(BaseModel):
    """Descriptive EntityAttribute — dimension key + typed value (not State)."""

    model_config = ConfigDict(extra="forbid")

    subject: EntityMention
    dimension_key: str
    value_kind: Literal["text", "number", "year", "date", "concept"]
    text_value: str | None = None
    numeric_value: str | None = None
    unit: str | None = None
    year_value: int | None = None
    date_value: dt.date | None = None
    concept_value_id: str | None = None
    is_current: bool = True
    time: IrTime = Field(default_factory=lambda: IrTime(original_text=""))


class IrMeasurement(BaseModel):
    """Quantitative observation — dimension + Decimal value (not Attribute/State)."""

    model_config = ConfigDict(extra="forbid")

    subject: EntityMention
    context: EntityMention | None = None
    dimension_key: str
    numeric_value: str
    unit: str | None = None
    currency_code: str | None = None
    time: IrTime = Field(default_factory=lambda: IrTime(original_text=""))


class RelationAssertionMode(StrEnum):
    ASSERT = "assert"
    TERMINATE = "terminate"
    HISTORICAL = "historical"
    DENY_CURRENT = "deny_current"


class IrRelation(BaseModel):
    """Vínculo entre entidades — subject → relation → object."""

    model_config = ConfigDict(extra="forbid")

    type: ConceptRef
    subject: EntityMention
    object: EntityMention
    mode: RelationAssertionMode = RelationAssertionMode.ASSERT
    time: IrTime = Field(default_factory=lambda: IrTime(original_text=""))


class IrObligation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ConceptRef
    cadence: Recurrence
    due: IrTime | None = None
    facts: list[IrFact] = Field(default_factory=list)


class IrCorrectionTarget(BaseModel):
    """Semantic target description for Correction Engine — not trusted LLM DB ids."""

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


class IrCorrection(BaseModel):
    """Correção na IR.

    Legacy fact-correction: strategy + facts (+ optional event_id/fact_id).
    Correction Engine (I11.17+): operation + target (+ replacement via sibling IR fields).
    LAST_EVENT is compatibility-only and is never CorrectionTargetResolver authority.
    """

    model_config = ConfigDict(extra="forbid")

    strategy: CorrectionStrategy = CorrectionStrategy.LAST_EVENT
    event_id: str | None = None
    fact_id: str | None = None
    facts: list[IrFact] = Field(default_factory=list)
    operation: Literal["retract", "replace"] | None = None
    target: IrCorrectionTarget | None = None

    @model_validator(mode="after")
    def _resolved_target(self) -> IrCorrection:
        if self.operation is not None:
            return self
        if self.strategy is CorrectionStrategy.EXPLICIT and not (
            self.event_id or self.fact_id
        ):
            raise ValueError("correção explícita exige event_id ou fact_id")
        return self


class ClaimExecution(BaseModel):
    """Per-claim overlay outcome — identity after canonicalization, before persist."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    kind: str
    status: str
    predicate: str | None = None
    canonical_dimension: str | None = None
    dimension_source: str | None = None
    value: str | None = None
    reason: str | None = None
    materialized_as: str | None = None


class ClaimReport(BaseModel):
    """Interpreter-side claim accounting — Engine does not re-read raw_input."""

    model_config = ConfigDict(extra="forbid")

    received: int = 0
    assumed_dropped: int = 0
    derived_deferred: int = 0
    unsupported: int = 0
    notes: list[str] = Field(default_factory=list)
    executions: list[ClaimExecution] = Field(default_factory=list)


class IngestIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IngestIntent
    raw_input: str
    domains: list[ConceptRef] = Field(default_factory=list)
    entities_mentioned: list[EntityMention] = Field(default_factory=list)
    event: IrEvent | None = None
    state: IrState | None = None
    attribute: IrAttribute | None = None
    additional_attributes: list[IrAttribute] = Field(default_factory=list)
    """Companion Attribute writes (e.g. model alongside brand) — same subject."""
    measurement: IrMeasurement | None = None
    additional_measurements: list[IrMeasurement] = Field(default_factory=list)
    relation: IrRelation | None = None
    additional_relations: list[IrRelation] = Field(default_factory=list)
    obligation: IrObligation | None = None
    correction: IrCorrection | None = None
    missing_hints: list[ConceptRef] = Field(default_factory=list)
    claim_report: ClaimReport | None = None
    discourse_decision: Literal["continue", "new_topic", "ambiguous", "none"] | None = None


class RelativePeriod(StrEnum):
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    TODAY = "today"
    YESTERDAY = "yesterday"
    NOW = "now"
    """Present/reference instant — NOT the calendar day (≠ TODAY)."""


class IrQueryTime(BaseModel):
    """Tempo de consulta já estruturado. O resolver não parseia português.

    Três camadas — não misturar:

    * datetime boundary: `start`/`end` já são o intervalo de execução `[start, end)`.
    * civil date boundary: `date_from` inclusivo, `date_to` exclusivo
      (`date_to=2026-09-03` → fim `2026-09-03T00:00`; o dia 03 não participa).
    * intervalo linguístico inclusivo: “de 1 a 3 de setembro” inclui três dias
      civis e deve chegar aqui como `date_from=2026-09-01`, `date_to=2026-09-04`
      (ou `end` equivalente). Essa expansão é do Interpreter, não do QueryEngine.
    """

    model_config = ConfigDict(extra="forbid")

    original_text: str | None = None
    relative_period: RelativePeriod | None = None
    partial_month: int | None = Field(default=None, ge=1, le=12)
    partial_year: int | None = None
    start: dt.datetime | None = None
    end: dt.datetime | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None


class QuerySpec(BaseModel):
    """IR de consulta. Sem IDs persistentes inventados pelo Interpreter."""

    model_config = ConfigDict(extra="forbid")

    intent: Literal["list", "aggregate", "state", "relation", "attribute", "measurement"] = "list"
    entities: list[EntityMention] = Field(default_factory=list)
    entity_association: Literal[
        "actor",
        "subject",
        "relation_endpoint",
        "relation_subject",
        "relation_object",
        "event_context",
    ] | None = None
    event_types: list[ConceptRef] = Field(default_factory=list)
    state_dimensions: list[ConceptRef] = Field(default_factory=list)
    state_values: list[ConceptRef] = Field(default_factory=list)
    relation_types: list[ConceptRef] = Field(default_factory=list)
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
    attribute_dimension_key: str | None = None
    attribute_query_mode: Literal[
        "value_lookup", "proposition", "historical_existence", "snapshot"
    ] | None = None
    attribute_value_kind: (
        Literal["text", "number", "year", "date", "concept"] | None
    ) = None
    attribute_text_value: str | None = None
    attribute_numeric_value: str | None = None  # Decimal as string for IR stability
    attribute_unit: str | None = None
    attribute_year_value: int | None = None
    attribute_concept_value_id: str | None = None
    measurement_dimension_key: str | None = None
    measurement_query_mode: Literal[
        "latest_observation",
        "observation_at_time",
        "observations_in_range",
        "value_proposition",
    ] | None = None
    measurement_numeric_value: str | None = None
    measurement_unit: str | None = None
    measurement_currency_code: str | None = None
    actions: list[ConceptRef] = Field(default_factory=list)
    facts: list[ConceptRef] = Field(default_factory=list)
    domains: list[ConceptRef] = Field(default_factory=list)
    aggregate: Literal["sum", "count", "latest", "none"] = "none"
    hierarchy: Literal["exact", "include_descendants"] = "exact"
    version_policy: Literal["current", "history"] = "current"
    currency: str | None = None
    time: IrQueryTime | None = None
    sort: Literal["event_time_desc", "event_time_asc", "created_at_desc", "created_at_asc"] = (
        "event_time_desc"
    )
    limit: int | None = None


class QueryIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["query"] = "query"
    raw_input: str
    query: QuerySpec
    discourse_decision: Literal["continue", "new_topic", "ambiguous", "none"] | None = None


InterpretationResult = IngestIR | QueryIR
