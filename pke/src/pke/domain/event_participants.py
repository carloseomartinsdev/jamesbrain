"""Participante de Event — associação entity + papel semântico."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

KNOWN_EVENT_PARTICIPANT_ROLES = frozenset(
    {
        "role.actor",
        "role.object",
        "role.patient",
        "role.context",
        "role.unspecified",
    }
)


class EventParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    event_id: str
    entity_id: str
    role: str = Field(min_length=1)

    @field_validator("role")
    @classmethod
    def _known_role(cls, value: str) -> str:
        if value not in KNOWN_EVENT_PARTICIPANT_ROLES:
            raise ValueError(f"unknown event participant role: {value!r}")
        return value
