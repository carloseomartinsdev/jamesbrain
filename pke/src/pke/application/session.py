"""Contexto de turno. Entidades só entram aqui depois do commit."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pke.resolution.context import PersonalContext


class SessionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    personal: PersonalContext
    recent_event_ids: list[str] = Field(default_factory=list)
    last_event_id: str | None = None
    last_fact_ids: dict[str, str] = Field(default_factory=dict)
    # Bounded conversational utterances for Correction Acceptance Guard (I12.4).
    # Not Knowledge Store rows; application may supply prior user turns only.
    recent_utterances: list[str] = Field(default_factory=list)

    @property
    def user_id(self) -> str:
        return self.personal.user_id
