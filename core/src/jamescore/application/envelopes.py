from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Outcome = Literal["answer", "clarification", "safe_abstain", "technical_error"]


class PublicEnvelope(BaseModel):
    """Single Portal contract. Portal does not route on internal capability."""

    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    james_conversation_id: str | None = None
    text: str = ""
    type: str = "answer"
    status: str = "ok"
    clarification: Any | None = None
    data: Any | None = None
    error: Any | None = None
    operation: Any | None = None
    message_id: str | None = None
    user_message_id: str | None = None
    client_request_id: str | None = None
    request_id: str | None = None
    trace: dict[str, Any] | None = None


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = ""
    james_conversation_id: str | None = None
    conversation_id: str | None = None
    title: str | None = None
    trace: bool = False
    user_id: Any | None = Field(default=None, description="Ignored. Never identity authority.")


class ClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    clarification_id: str
    text: str = ""
    option_id: str = ""
    trace: bool = False
    user_id: Any | None = None


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    user_id: Any | None = None
