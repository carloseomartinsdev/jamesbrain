"""Contexto pessoal de sessão — isolamento por usuário, sem persistir aliases."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pke.domain.entities import Entity


class ResolutionPurpose(StrEnum):
    INGEST = "ingest"
    QUERY = "query"


class PersonalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    recent_entity_ids: list[str] = Field(default_factory=list)
    last_by_type_id: dict[str, str] = Field(default_factory=dict)
    last_by_role_key: dict[str, str] = Field(default_factory=dict)
    confirmed_aliases: dict[str, str] = Field(default_factory=dict)

    def record_mention(self, entity: Entity, role_key: str | None = None) -> None:
        """Atualiza sessão. Não grava alias contextual."""
        if entity.user_id != self.user_id:
            raise ValueError("contexto pessoal não aceita entidade de outro usuário")
        self.recent_entity_ids.append(entity.id)
        self.last_by_type_id[entity.type_id] = entity.id
        if role_key:
            self.last_by_role_key[role_key] = entity.id


class ResolutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    personal: PersonalContext
    allow_type_descendants: bool = True
    purpose: ResolutionPurpose = ResolutionPurpose.INGEST
    principal_entity_id: str | None = None
    owned_vehicle_entity_ids: list[str] = Field(default_factory=list)
    """Current vehicles owned by principal (E1.2 contextual 'meu carro')."""

    def model_post_init(self, __context: object) -> None:
        if self.personal.user_id != self.user_id:
            raise ValueError("ResolutionContext.user_id deve coincidir com PersonalContext")
        if self.principal_entity_id is not None and self.principal_entity_id == self.user_id:
            raise ValueError("principal_entity_id must not equal AuthUser.id")
