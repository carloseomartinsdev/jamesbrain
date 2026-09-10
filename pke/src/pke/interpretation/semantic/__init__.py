"""Semantic resolution — proposal, primitive routing, concept resolution."""

from pke.interpretation.semantic.models import (
    PrimitiveKind,
    ResolutionConfidence,
    ResolutionProvenance,
    ResolutionResult,
    SemanticProposal,
    SemanticResolutionOutcome,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal

__all__ = [
    "PrimitiveKind",
    "ResolutionConfidence",
    "ResolutionProvenance",
    "ResolutionResult",
    "SemanticProposal",
    "SemanticResolutionOutcome",
    "proposal_to_canonical_ir",
    "resolve_proposal",
]
