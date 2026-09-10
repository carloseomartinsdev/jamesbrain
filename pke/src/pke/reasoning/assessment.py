"""Agrega validação e completude. Não persiste."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from pke.ontology.registry import OntologyRegistry
from pke.reasoning.candidate import KnowledgeCandidate
from pke.reasoning.completeness import (
    ClarificationCandidate,
    CompletenessEngine,
    CompletenessResult,
)
from pke.reasoning.schemas import CompletenessSchemaRegistry
from pke.reasoning.validation import KnowledgeValidator, ValidationResult
from pke.resolution.lookup import EntityLookup


class KnowledgeAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    validation: ValidationResult
    completeness: CompletenessResult
    persistable: bool
    """Sem impedimento epistemológico. Não implica dependências já materializadas."""
    clarification: ClarificationCandidate | None = None


class KnowledgeAssessor:
    def __init__(
        self,
        ontology: OntologyRegistry,
        lookup: EntityLookup,
        schemas: CompletenessSchemaRegistry | None = None,
    ) -> None:
        self._validator = KnowledgeValidator(ontology, lookup)
        self._completeness = CompletenessEngine(ontology, lookup, schemas)

    def assess(self, candidate: KnowledgeCandidate) -> KnowledgeAssessment:
        validation = self._validator.validate(candidate)
        completeness = self._completeness.evaluate(candidate)
        persistable = validation.valid and not completeness.blocking
        clarification = completeness.clarification if persistable or completeness.blocking else None
        if not validation.valid:
            persistable = False
        return KnowledgeAssessment(
            validation=validation,
            completeness=completeness,
            persistable=persistable,
            clarification=clarification,
        )
