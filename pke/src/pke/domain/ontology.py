"""Conceito ontológico aberto — CORE / EXTENDED / PERSONAL."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONCEPT_KEY_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"


class ConceptScope(StrEnum):
    CORE = "core"
    EXTENDED = "extended"
    PERSONAL = "personal"


class ConceptStatus(StrEnum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


class ConceptKind(StrEnum):
    """Metaclasse do conceito. Não fecha o conjunto de tipos do cotidiano."""

    ENTITY_TYPE = "entity_type"
    EVENT_TYPE = "event_type"
    STATE_DIMENSION = "state_dimension"
    STATE_VALUE = "state_value"
    RELATION_TYPE = "relation_type"
    ACTION = "action"
    ATTRIBUTE = "attribute"
    DOMAIN = "domain"
    ROLE = "role"


class ConceptRef(BaseModel):
    """Identidade conceitual. `key` é o identificador do registry, não texto do usuário.

    Antes da resolução: só `key`. Depois: `concept_id` preenchido.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, pattern=CONCEPT_KEY_PATTERN)
    concept_id: str | None = None


class ConceptPresentation(BaseModel):
    """Metadados de UI. Nunca usados como identidade nem como chave de lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str | None = None
    description: str | None = None


class OntologyConcept(BaseModel):
    """Tipo/ação/relação/atributo/domínio identificável e hierarquizável.

    CORE é seedado e protegido em código. EXTENDED/PERSONAL existem no modelo
    para não exigir remodelagem. A Onda 1 não promove nem deixa a LLM criar
    conceitos.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    key: str = Field(min_length=1, pattern=CONCEPT_KEY_PATTERN)
    kind: ConceptKind
    scope: ConceptScope
    status: ConceptStatus = ConceptStatus.ACTIVE
    parent_id: str | None = None
    owner_user_id: str | None = None
    created_at: dt.datetime
    presentation: ConceptPresentation | None = None

    @model_validator(mode="after")
    def _scope_isolation(self) -> OntologyConcept:
        if self.scope is ConceptScope.PERSONAL and not self.owner_user_id:
            raise ValueError("conceito PERSONAL exige owner_user_id")
        if self.scope is not ConceptScope.PERSONAL and self.owner_user_id is not None:
            raise ValueError("conceito CORE/EXTENDED não pode ter owner_user_id")
        return self

    def as_ref(self) -> ConceptRef:
        return ConceptRef(key=self.key, concept_id=self.id)
