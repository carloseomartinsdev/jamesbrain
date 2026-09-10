"""Snapshot de leitura. Sem SQLAlchemy."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pke.domain.attributes import EntityAttribute
from pke.domain.corrections import Correction
from pke.domain.entities import Entity
from pke.domain.events import Event
from pke.domain.facts import Fact
from pke.domain.measurements import Measurement
from pke.domain.relations import Relation
from pke.domain.states import State


class UserKnowledgeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    user_id: str
    entities: dict[str, Entity] = Field(default_factory=dict)
    events: list[Event] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    states: list[State] = Field(default_factory=list)
    attributes: list[EntityAttribute] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    corrections: list[Correction] = Field(default_factory=list)
    principal_entity_id: str | None = None
