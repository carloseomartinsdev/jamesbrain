"""Contratos do provider LLM. Sem persistência e sem motor de consulta."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LlmMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user"]
    content: str


class LlmStructuredRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[LlmMessage]
    json_schema: dict[str, Any]
    schema_name: str = "LlmIrEnvelope"


class LlmCallMetadata(BaseModel):
    """Metadados técnicos. Não entram no conhecimento do usuário."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    request_id: str | None = None
    latency_ms: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    attempts: int = 1


class LlmStructuredResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    metadata: LlmCallMetadata


class LlmMetrics:
    """Contadores em memória. Sem dashboard."""

    def __init__(self) -> None:
        self.interpret_attempts = 0
        self.calls = 0
        self.successes = 0
        self.schema_failures = 0
        self.provider_failures = 0
        self.provider_json_failures = 0
        self.wire_failures = 0
        self.canonical_failures = 0
        self.total_latency_ms = 0.0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def record_call(self, metadata: LlmCallMetadata) -> None:
        self.calls += 1
        self.total_latency_ms += metadata.latency_ms
        if metadata.prompt_tokens:
            self.prompt_tokens += metadata.prompt_tokens
        if metadata.completion_tokens:
            self.completion_tokens += metadata.completion_tokens

    @property
    def provider_valid_json_rate(self) -> float | None:
        """Taxa de respostas com JSON parseável após chamada ao provider."""
        if self.interpret_attempts == 0:
            return None
        valid = self.interpret_attempts - self.provider_json_failures
        return round(valid / self.interpret_attempts, 4)

    @property
    def wire_valid_rate(self) -> float | None:
        wire_attempts = self.calls + self.wire_failures
        if wire_attempts == 0:
            return None
        return round((wire_attempts - self.wire_failures) / wire_attempts, 4)

    @property
    def canonical_valid_rate(self) -> float | None:
        canonical_attempts = self.calls + self.canonical_failures
        if canonical_attempts == 0:
            return None
        return round((canonical_attempts - self.canonical_failures) / canonical_attempts, 4)
