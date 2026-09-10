"""Modelos experimentais I11.2 — NÃO importar em produção."""

from pke.design.semantic_frame import (
    DimensionSlot,
    EnrichmentState,
    EpistemicMetadata,
    Occurrence,
    SemanticFrame,
)
from pke.design.temporal_knowledge import TemporalKnowledge, TemporalUnknownReason

__all__ = [
    "DimensionSlot",
    "EnrichmentState",
    "EpistemicMetadata",
    "Occurrence",
    "SemanticFrame",
    "TemporalKnowledge",
    "TemporalUnknownReason",
]
