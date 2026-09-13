"""DTOs públicos da PKE API v1. Não reutilizar IR/resultados internos do Engine."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiResponseType(StrEnum):
    ANSWER = "answer"
    ACKNOWLEDGEMENT = "acknowledgement"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class ApiMessageStatus(StrEnum):
    SENDING = "sending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CLARIFICATION_REQUIRED = "clarification_required"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApiOperationKind(StrEnum):
    KNOWLEDGE_WRITE = "knowledge_write"
    KNOWLEDGE_QUERY = "knowledge_query"
    KNOWLEDGE_CORRECTION = "knowledge_correction"
    CLARIFICATION = "clarification"
    NONE = "none"


class ApiOperationOutcome(StrEnum):
    COMMITTED = "committed"
    PARTIAL = "partial"
    DEFERRED = "deferred"
    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class ApiClarificationMode(StrEnum):
    CHOICE = "choice"
    TEXT = "text"


class ApiMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ApiErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool | None = None


class ApiClarificationOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str


class ApiClarification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    mode: ApiClarificationMode
    options: list[ApiClarificationOption] = Field(default_factory=list)


class ApiOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ApiOperationKind
    outcome: ApiOperationOutcome


class ApiMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    client_request_id: str | None = Field(default=None, max_length=80)


class ApiClarificationAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=8000)
    option_id: str | None = Field(default=None, max_length=120)
    client_request_id: str | None = Field(default=None, max_length=80)


class ApiCreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)


class ApiMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    message_id: str
    type: ApiResponseType
    status: ApiMessageStatus
    text: str
    clarification: ApiClarification | None = None
    error: ApiErrorBody | None = None
    data: dict[str, Any] | None = None
    operation: ApiOperation | None = None
    request_id: str | None = None
    client_request_id: str | None = None
    user_message_id: str | None = None
    debug: dict[str, Any] | None = None


class ApiMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str
    role: ApiMessageRole
    type: str
    text: str
    status: ApiMessageStatus | None = None
    created_at: str
    clarification: ApiClarification | None = None
    error: ApiErrorBody | None = None
    data: dict[str, Any] | None = None
    operation: ApiOperation | None = None


class ApiConversationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    created_at: str
    updated_at: str
    last_message_preview: str | None = None
    status: Literal["active", "archived"] | str = "active"


class ApiConversation(ApiConversationSummary):
    messages: list[ApiMessage] | None = None
    pending_clarification: ApiClarification | None = None


class ApiCurrentUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    auth_mode: Literal["session", "dev"] | str
    username: str | None = None


class ApiAuthRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=8, max_length=200)
    display_name: str | None = Field(default=None, max_length=80)


class ApiAuthLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class ApiAuthSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: str
    user: ApiCurrentUser


class ApiHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    version: str


class ApiCatalogCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    core: int
    trained: int
    learned: int
    extended: int = 0


class ApiCatalogConcept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    kind: str
    scope: str
    source: Literal["core", "trained", "learned", "extended"]
    label: str | None = None
    meaning: str | None = None
    lemmas: list[str] = Field(default_factory=list)
    extends_core: bool = False


class ApiCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_schema_version: str
    counts: ApiCatalogCounts
    concepts: list[ApiCatalogConcept]
