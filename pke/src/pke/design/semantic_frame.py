"""SemanticFrame — modelo experimental I11.2. Isolado do pipeline produtivo."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pke.design.temporal_knowledge import TemporalKnowledge


class SlotStatus(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    MISSING = "missing"
    INFERRED = "inferred"
    AMBIGUOUS = "ambiguous"
    NOT_APPLICABLE = "not_applicable"
    PARTIALLY_KNOWN = "partially_known"


class EvidenceSourceKind(StrEnum):
    EXPLICIT = "explicit"
    CONTEXTUAL = "contextual"
    BEHAVIORAL = "behavioral"
    SEMANTIC = "semantic"
    DERIVED = "derived"
    USER_CONFIRMATION = "user_confirmation"


class EpistemicStatus(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    UNCERTAIN = "uncertain"
    CONFIRMED = "confirmed"
    CONTRADICTED = "contradicted"
    HYPOTHESIZED = "hypothesized"


class SemanticInformationLoss(StrEnum):
    LOSSLESS = "lossless"
    ACCEPTABLE_LOSS = "acceptable_loss"
    DESTRUCTIVE = "destructive"


class DimensionSlot(BaseModel):
    """Uma dimensão do frame — opcional e independente."""

    model_config = ConfigDict(extra="forbid")

    status: SlotStatus = SlotStatus.MISSING
    value: Any | None = None
    concept_keys: list[str] = Field(default_factory=list)
    surface_forms: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    epistemic_status: EpistemicStatus = EpistemicStatus.EXPLICIT
    evidence_source: EvidenceSourceKind = EvidenceSourceKind.EXPLICIT
    broader_concepts: list[str] = Field(default_factory=list)
    generalization_loss: SemanticInformationLoss | None = None


class SemanticFrame(BaseModel):
    """Quadro semântico composicional — não é formulário fechado."""

    model_config = ConfigDict(extra="forbid")

    actor: DimensionSlot = Field(default_factory=DimensionSlot)
    action: DimensionSlot = Field(default_factory=DimensionSlot)
    subject: DimensionSlot = Field(default_factory=DimensionSlot)
    object: DimensionSlot = Field(default_factory=DimensionSlot)
    participants: DimensionSlot = Field(default_factory=DimensionSlot)
    time: DimensionSlot = Field(default_factory=DimensionSlot)
    place: DimensionSlot = Field(default_factory=DimensionSlot)
    manner: DimensionSlot = Field(default_factory=DimensionSlot)
    cause: DimensionSlot = Field(default_factory=DimensionSlot)
    purpose: DimensionSlot = Field(default_factory=DimensionSlot)
    quantity: DimensionSlot = Field(default_factory=DimensionSlot)
    value: DimensionSlot = Field(default_factory=DimensionSlot)
    result: DimensionSlot = Field(default_factory=DimensionSlot)
    state_transition: DimensionSlot = Field(default_factory=DimensionSlot)
    event_type: DimensionSlot = Field(default_factory=DimensionSlot)
    relation: DimensionSlot = Field(default_factory=DimensionSlot)

    def coverage_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in SemanticFrame.model_fields:
            slot: DimensionSlot = getattr(self, name)
            if slot.status is not SlotStatus.NOT_APPLICABLE:
                out[name.upper()] = slot.status.value
        return out


class EpistemicMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EpistemicStatus = EpistemicStatus.EXPLICIT
    evidence_source: EvidenceSourceKind = EvidenceSourceKind.EXPLICIT
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_chain: list[str] = Field(default_factory=list)


class EnrichmentState(BaseModel):
    """O que falta e o que vale a pena perguntar — sem bloquear validade."""

    model_config = ConfigDict(extra="forbid")

    known_dimensions: list[str] = Field(default_factory=list)
    unknown_dimensions: list[str] = Field(default_factory=list)
    inferred_dimensions: list[str] = Field(default_factory=list)
    high_value_missing: list[str] = Field(default_factory=list)
    blocking_missing: list[str] = Field(default_factory=list)


class Occurrence(BaseModel):
    """Unidade episódica proposta — Event/Action/State/Relation coexistem."""

    model_config = ConfigDict(extra="forbid")

    frame: SemanticFrame = Field(default_factory=SemanticFrame)
    temporal: TemporalKnowledge = Field(default_factory=TemporalKnowledge)
    epistemic: EpistemicMetadata = Field(default_factory=EpistemicMetadata)
    enrichment: EnrichmentState = Field(default_factory=EnrichmentState)
    occurrence_id: str | None = None
    session_links: list[str] = Field(default_factory=list)

    @property
    def is_valid_incomplete(self) -> bool:
        """Conhecimento válido mesmo sem completude."""
        return not self.enrichment.blocking_missing
