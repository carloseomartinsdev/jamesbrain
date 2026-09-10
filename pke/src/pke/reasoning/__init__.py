"""Reasoning do PKE — validação e completude, sem persistência."""

from pke.reasoning.assessment import KnowledgeAssessment, KnowledgeAssessor
from pke.reasoning.candidate import KnowledgeCandidate, MentionBinding
from pke.reasoning.completeness import (
    ClarificationCandidate,
    CompletenessEngine,
    CompletenessResult,
    Presence,
    RequirementEvaluation,
)
from pke.reasoning.issues import Issue, Severity
from pke.reasoning.schemas import (
    CORE_COMPLETENESS_VERSION,
    CompletenessSchema,
    CompletenessSchemaRegistry,
    Importance,
    Requirement,
    SlotKind,
)
from pke.reasoning.validation import KnowledgeValidator, ValidationResult

__all__ = [
    "CORE_COMPLETENESS_VERSION",
    "ClarificationCandidate",
    "CompletenessEngine",
    "CompletenessResult",
    "CompletenessSchema",
    "CompletenessSchemaRegistry",
    "Importance",
    "Issue",
    "KnowledgeAssessment",
    "KnowledgeAssessor",
    "KnowledgeCandidate",
    "KnowledgeValidator",
    "MentionBinding",
    "Presence",
    "Requirement",
    "RequirementEvaluation",
    "Severity",
    "SlotKind",
    "ValidationResult",
]
