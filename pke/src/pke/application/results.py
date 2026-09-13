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
    PARTIAL = "partial"
    DEFERRED = "deferred"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"
    UNSUPPORTED = "unsupported"


class ClaimTally(BaseModel):
    """Completeness of multi-claim ingest — committed ≠ semantically complete."""

    model_config = ConfigDict(extra="forbid")

    received: int = 0
    valid: int = 0
    committed: int = 0
    derived: int = 0
    rejected: int = 0
    deferred: int = 0


def interpreter_claims_present(ir: object | None) -> bool:
    report = getattr(ir, "claim_report", None) if ir is not None else None
    return report is not None and int(getattr(report, "received", 0) or 0) > 0


def ingest_status_from_tally(
    tally: ClaimTally,
    *,
    interpreter_claims: bool,
) -> IngestStatus:
    """Claim-aware write outcome. Entity reuse / raw_input / no-exception is not commit."""
    if not interpreter_claims:
        return IngestStatus.COMMITTED
    if tally.committed > 0 and tally.deferred == 0:
        return IngestStatus.COMMITTED
    if tally.committed > 0:
        return IngestStatus.PARTIAL
    if tally.deferred > 0:
        return IngestStatus.DEFERRED
    return IngestStatus.UNSUPPORTED


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
    claims: ClaimTally = Field(default_factory=ClaimTally)


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
    claims: ClaimTally = Field(default_factory=ClaimTally)
