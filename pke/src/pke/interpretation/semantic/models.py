"""Modelos de SemanticProposal e resultados de resolução."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pke.interpretation.models import IngestIR, QueryIR


class PrimitiveKind(StrEnum):
    EVENT = "event"
    STATE = "state"
    RELATION = "relation"
    ATTRIBUTE = "attribute"
    TYPE = "type"
    """Entity classification / typing — routing only; not first-class Attribute storage."""
    MEASUREMENT = "measurement"
    """Quantitative observation — routing/resolution only until schema v9."""
    UNKNOWN = "unknown"


class ResolutionConfidence(StrEnum):
    EXACT = "exact"
    CONTEXTUAL = "contextual"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class ResolutionProvenance(StrEnum):
    CANONICAL = "canonical"
    ALIAS = "alias"
    CONTEXTUAL = "contextual"
    SEMANTIC = "semantic"
    HINT = "hint"


class SemanticEntityMention(BaseModel):
    """Menção sem exigir key canônica — kind hint semântico."""

    model_config = ConfigDict(extra="forbid")

    text: str
    kind_hint: (
        Literal[
            "person",
            "organization",
            "place",
            "thing",
            "appliance",
            "vehicle",
            "document",
            "medication",
            "unknown",
        ]
        | None
    ) = None
    role_hint: str | None = None
    reference_kind: Literal["named", "contextual", "possessive"] = "named"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SemanticTime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_text: str = ""
    relative_day: Literal["today", "yesterday", "tomorrow"] | None = None
    occurrence_aspect: Literal["happened", "ongoing", "planned", "habitual"] | None = None
    relation_to_reference: Literal["before", "after", "during", "habitual"] | None = None
    tense_evidence: str | None = None
    partial_month: int | None = Field(default=None, ge=1, le=12)
    partial_year: int | None = None
    unknown_reason: Literal["not_provided", "forgotten", "unresolved", "unknown"] | None = None


class SemanticProposal(BaseModel):
    """Proposta semântica do LLM — distinta do IR canônico."""

    model_config = ConfigDict(extra="forbid")

    raw_input: str
    utterance_kind: Literal["assert", "describe", "change", "query", "correct", "none"] = "assert"
    primitive_hint: Literal[
        "event", "state", "relation", "attribute", "type", "measurement", "unknown"
    ] = "unknown"

    subject: SemanticEntityMention | None = None
    object: SemanticEntityMention | None = None
    context: SemanticEntityMention | None = None
    """Optional context entity (e.g. Corolla for tank measurement) — not the measured subject."""
    participants: list[SemanticEntityMention] = Field(default_factory=list)
    entities_mentioned: list[SemanticEntityMention] = Field(default_factory=list)

    action_expression: str | None = None
    relation_expression: str | None = None
    state_expression: str | None = None
    attribute_expression: str | None = None
    event_expression: str | None = None
    measurement_expression: str | None = None
    """Surface quantity observation expression (e.g. '20 litros', '80%')."""

    measurable_dimension_key: str | None = None
    """LLM/cue dimension identity (fuel_level, battery_charge, …) — not a unit string."""
    measurement_numeric_value: str | None = None
    """Decimal as text when known structurally."""
    measurement_unit: str | None = None
    measurement_currency_code: str | None = None

    temporal: SemanticTime = Field(default_factory=SemanticTime)
    negation: bool = False
    lifecycle_cue: Literal["start", "end", "ongoing", "deny", "none"] | None = None

    change_semantics: bool = False
    condition_semantics: bool = False
    link_semantics: bool = False
    stable_property_semantics: bool = False
    classification_semantics: bool = False
    """Entity classification/type assertion (é um carro) — not a descriptive Attribute."""
    measurement_semantics: bool = False
    """Observed quantitative reading — not descriptive Attribute and not world-condition State."""

    domain_hints: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    assertion_confidence: dict[str, float] = Field(default_factory=dict)
    """Optional per-primitive confidence keyed by PrimitiveKind value."""

    correction_semantics: bool = False
    """Explicit epistemic correction intent — not negation/contradiction alone."""
    correction_operation: Literal["retract", "replace"] | None = None
    correction_target_kind: Literal[
        "event", "measurement", "relation", "state", "attribute"
    ] | None = None
    correction_target_entity_text: str | None = None
    correction_target_object_text: str | None = None
    correction_target_dimension_key: str | None = None
    correction_target_value_text: str | None = None
    correction_target_numeric_value: str | None = None
    correction_target_year: int | None = None
    correction_target_relation_key: str | None = None
    correction_target_state_value_key: str | None = None
    correction_target_action_key: str | None = None
    correction_target_assertion_id: str | None = None
    """Proposal-only; never trusted without controlled candidate membership validation."""
    correction_conversation_assertion_id: str | None = None
    """Application-supplied conversation binding — not DB insertion order."""


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"
    SAFE_PARTIAL = "safe_partial"
    ONTOLOGY_GAP = "ontology_gap"
    BLOCKED = "blocked"


class AttributeValueSlot(BaseModel):
    """Typed Attribute value ready for wire / companion materialization."""

    model_config = ConfigDict(extra="forbid")

    dimension_key: str
    value_kind: str
    text_value: str | None = None
    numeric_value: str | None = None
    unit: str | None = None
    year_value: int | None = None
    is_current: bool = True


class ResolvedConcepts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primitive: PrimitiveKind
    event_type: str | None = None
    action: str | None = None
    state_dimension: str | None = None
    state_value: str | None = None
    relation_type: str | None = None
    attribute: str | None = None
    attribute_dimension_key: str | None = None
    attribute_value_kind: str | None = None
    attribute_text_value: str | None = None
    attribute_numeric_value: str | None = None
    attribute_unit: str | None = None
    attribute_year_value: int | None = None
    attribute_is_current: bool | None = None
    attribute_companions: list[AttributeValueSlot] = Field(default_factory=list)
    measurement_dimension_key: str | None = None
    measurement_numeric_value: str | None = None
    measurement_unit: str | None = None
    measurement_currency_code: str | None = None
    domains: list[str] = Field(default_factory=list)
    confidence: ResolutionConfidence = ResolutionConfidence.UNRESOLVED
    provenance: ResolutionProvenance = ResolutionProvenance.SEMANTIC
    unresolved: bool = False
    resolution_status: ResolutionStatus = ResolutionStatus.UNRESOLVED
    recognized_sense: str | None = None
    surface_expression: str | None = None
    ontology_gap: bool = False
    safe_abstention: bool = False
    abstention_reason: str | None = None
    notes: list[str] = Field(default_factory=list)


class SemanticAssertionFrame(BaseModel):
    """One explicitly evidenced knowledge proposition from an utterance.

    Ordering in lists is transport-only — never epistemic priority.
    """

    model_config = ConfigDict(extra="forbid")

    primitive: PrimitiveKind
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class ResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal: SemanticProposal
    primitive: PrimitiveKind
    concepts: ResolvedConcepts
    primitive_routing_notes: list[str] = Field(default_factory=list)
    assertions: list[SemanticAssertionFrame] = Field(default_factory=list)
    """All explicitly evidenced primitives (Event+Measurement, etc.). Empty → treat as [primitive]."""
    non_materialized_primitives: list[PrimitiveKind] = Field(default_factory=list)
    """Semantically retained propositions that did not enter materialization IR."""
    non_materialized_reasons: list[str] = Field(default_factory=list)
    """Parallel reasons (e.g. measurement_entity_required) — not epistemic invalidation."""


class SemanticResolutionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: ResolutionResult
    ir: IngestIR | QueryIR | None = None
    wire_stage: Literal["proposal", "canonical", "unresolved"] = "proposal"
    failure_stage: str | None = None
    execution_outcome: str | None = None
    execution_reasons: list[str] = Field(default_factory=list)
    clarification_eligible: bool = False
    materializable_count: int = 0
