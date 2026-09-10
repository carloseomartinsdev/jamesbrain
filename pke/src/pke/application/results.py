"""Resultados de ingestão. Sem copy de UI."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pke.application.pending_operation import PendingSemanticOperation
from pke.reasoning.assessment import KnowledgeAssessment
from pke.reasoning.completeness import ClarificationCandidate
from pke.reasoning.issues import Issue


class IngestStatus(StrEnum):
    COMMITTED = "committed"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"
    UNSUPPORTED = "unsupported"


class CorrectionIngestOutcome(StrEnum):
    """Semantic correction ingest outcome — distinct from ordinary commit success."""

    CORRECTION_APPLIED = "correction_applied"
    CORRECTION_TARGET_UNRESOLVED = "correction_target_unresolved"
    CORRECTION_TARGET_AMBIGUOUS = "correction_target_ambiguous"
    CORRECTION_REPLACEMENT_UNRESOLVED = "correction_replacement_unresolved"
    CORRECTION_REPLACEMENT_NON_MATERIALIZABLE = "correction_replacement_non_materializable"
    CORRECTION_REJECTED = "correction_rejected"
    CORRECTION_UNSUPPORTED = "correction_unsupported"


class MaterializationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_entity_ids: list[str] = Field(default_factory=list)
    reused_entity_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    state_ids: list[str] = Field(default_factory=list)
    attribute_ids: list[str] = Field(default_factory=list)
    measurement_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    raw_input_id: str | None = None
    correction_ids: list[str] = Field(default_factory=list)


class IngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    status: IngestStatus
    raw_text: str
    assessment: KnowledgeAssessment | None = None
    materialization: MaterializationResult | None = None
    clarification: ClarificationCandidate | None = None
    pending_operation: PendingSemanticOperation | None = None
    issues: list[Issue] = Field(default_factory=list)
    bound_entity_ids: list[str] = Field(default_factory=list)
    context_updated: bool = False
    correction_outcome: CorrectionIngestOutcome | None = None
