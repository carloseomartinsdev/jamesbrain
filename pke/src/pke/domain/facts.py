"""Fact — unidade de verdade persistente, versionada por supersession."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pke.domain.ontology import CONCEPT_KEY_PATTERN
from pke.domain.value_objects import (
    AnchorKind,
    Confidence,
    EpistemicStatus,
    Qualifier,
    Source,
)


class Fact(BaseModel):
    """Predicado auditável sobre Entity, Event ou Relation.

    `concept_id` é a identidade do predicado (OntologyConcept).
    `key` é a chave estável desse conceito — não texto livre do usuário.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    about_kind: AnchorKind
    about_id: str
    concept_id: str
    key: str = Field(pattern=CONCEPT_KEY_PATTERN)
    value: Any
    qualifier: Qualifier = Qualifier.EXACT
    epistemic_status: EpistemicStatus = EpistemicStatus.EXPLICIT
    source: Source
    confidence: Confidence
    supersedes_id: str | None = None
    created_at: datetime
    superseded_at: datetime | None = None

    @property
    def is_current(self) -> bool:
        return self.superseded_at is None

    def mark_superseded(self, at: datetime) -> Fact:
        """Marca este fact como histórico. Não apaga valor nem source."""
        if self.superseded_at is not None:
            raise ValueError("fact já foi substituído")
        return self.model_copy(update={"superseded_at": at})
