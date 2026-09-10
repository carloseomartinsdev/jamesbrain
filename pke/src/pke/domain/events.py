"""Evento — âncora temporal. type_id/action_id/domain_ids → OntologyConcept."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pke.domain.event_participants import EventParticipant
from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import EventStatus, TimeValue


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    type_id: str
    action_id: str | None = None
    actor_id: str | None = None
    subject_id: str | None = None
    participants: list[EventParticipant] = Field(default_factory=list)
    temporal: TemporalKnowledge
    status: EventStatus
    domain_ids: list[str] = Field(default_factory=list)
    raw_input_id: str
    created_at: dt.datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_time(cls, data: Any) -> Any:
        if isinstance(data, dict) and "time" in data and "temporal" not in data:
            time = data.pop("time")
            if isinstance(time, TimeValue):
                data["temporal"] = TemporalKnowledge.from_calendar(time)
        return data

    @property
    def time(self) -> TimeValue:
        if self.temporal.calendar is not None:
            return self.temporal.calendar
        raise AttributeError("evento com tempo parcial sem calendário")

    def participant_entity_ids(self) -> set[str]:
        if self.participants:
            return {p.entity_id for p in self.participants}
        return {eid for eid in (self.actor_id, self.subject_id) if eid}

    def participant_ids_for_role(self, *roles: str) -> set[str]:
        wanted = set(roles)
        return {p.entity_id for p in self.participants if p.role in wanted}
