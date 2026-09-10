"""Entidade persistente — âncora. O tipo é um OntologyConcept, não um enum fechado."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    type_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    created_at: datetime
