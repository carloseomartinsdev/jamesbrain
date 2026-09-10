"""Experimental OpenAI-compatible LlmProvider for I12.6 evaluation only.

Not production default. Same semantic contract as DeepSeekProvider:
json_object structured output, max_retries=0 at adapter layer.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from typing import Any

import httpx
import truststore
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from pke.llm.errors import (
    LlmAuthenticationError,
    LlmConfigurationError,
    LlmInvalidResponseError,
    LlmProviderError,
    LlmRateLimitError,
    LlmTimeoutError,
)
from pke.llm.models import LlmCallMetadata, LlmStructuredRequest, LlmStructuredResponse

truststore.inject_into_ssl()
_LOG = logging.getLogger("pke.llm.eval")


class OpenAICompatibleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr
    base_url: str
    model: str
    provider_name: str = "openai_compatible"
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=0, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.2, ge=0)

    @classmethod
    def from_env(
        cls,
        *,
        api_key_env: str,
        model: str,
        base_url: str,
        provider_name: str = "openai_compatible",
        max_retries: int = 0,
    ) -> OpenAICompatibleConfig:
        raw = os.environ.get(api_key_env, "").strip()
        if not raw:
            raise LlmConfigurationError(f"{api_key_env} ausente")
        return cls(
            api_key=raw,
            base_url=base_url,
            model=model,
            provider_name=provider_name,
            max_retries=max_retries,
        )

    @property
    def api_key_value(self) -> str:
        return self.api_key.get_secret_value()

    def __repr__(self) -> str:
        return (
            f"OpenAICompatibleConfig(provider={self.provider_name!r}, model={self.model!r}, "
            f"base_url={self.base_url!r}, api_key=***)"
        )


class OpenAICompatibleProvider:
    """Evaluation adapter — OpenAI chat.completions + json_object."""

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._sleeper = sleeper or time.sleep
        self._clock = clock or time.monotonic
        self._client = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=httpx.Timeout(config.timeout_seconds),
            transport=transport,
            headers={
                "Authorization": f"Bearer {config.api_key_value}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def generate_structured(self, request: LlmStructuredRequest) -> LlmStructuredResponse:
        body = {
            "model": self._config.model,
            "messages": [m.model_dump() for m in request.messages],
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        attempts = 0
        last_error: Exception | None = None
        started = self._clock()
        max_tries = self._config.max_retries + 1
        while attempts < max_tries:
            attempts += 1
            try:
                response = self._post(body)
                metadata = self._metadata(response, started, attempts)
                content = self._extract_json_text(response)
                return LlmStructuredResponse(content=content, metadata=metadata)
            except (LlmTimeoutError, LlmRateLimitError) as exc:
                last_error = exc
                if attempts >= max_tries:
                    raise
                self._sleeper(self._config.retry_backoff_seconds * (2 ** (attempts - 1)))
            except LlmProviderError as exc:
                last_error = exc
                if not getattr(exc, "retryable", False) or attempts >= max_tries:
                    raise
                self._sleeper(self._config.retry_backoff_seconds * (2 ** (attempts - 1)))
        assert last_error is not None
        raise last_error

    def _post(self, body: dict[str, Any]) -> httpx.Response:
        try:
            response = self._client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise LlmTimeoutError("timeout no provider") from exc
        except httpx.RequestError as exc:
            err = LlmProviderError("falha de rede no provider")
            err.retryable = True
            raise err from exc
        return self._raise_status(response)

    def _raise_status(self, response: httpx.Response) -> httpx.Response:
        status = response.status_code
        if status in {401, 403}:
            raise LlmAuthenticationError("autenticação recusada")
        if status == 429:
            raise LlmRateLimitError("rate limit")
        if status >= 500:
            err = LlmProviderError(f"provider {status}")
            err.retryable = True
            raise err
        if status >= 400:
            raise LlmProviderError(f"provider {status}")
        return response

    def _extract_json_text(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise LlmInvalidResponseError("resposta não é JSON") from exc
        choices = payload.get("choices") or []
        if not choices:
            raise LlmInvalidResponseError("resposta sem choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not content or not str(content).strip():
            raise LlmInvalidResponseError("conteúdo vazio")
        if choices[0].get("finish_reason") == "length":
            raise LlmInvalidResponseError("resposta truncada")
        text = str(content).strip()
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise LlmInvalidResponseError("conteúdo não é JSON") from exc
        return text

    def _metadata(self, response: httpx.Response, started: float, attempts: int) -> LlmCallMetadata:
        latency = (self._clock() - started) * 1000
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = {}
        usage = payload.get("usage") or {}
        choices = payload.get("choices") or [{}]
        finish = choices[0].get("finish_reason") if choices else None
        return LlmCallMetadata(
            provider=self._config.provider_name,
            model=payload.get("model") or self._config.model,
            request_id=payload.get("id"),
            latency_ms=latency,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            finish_reason=finish,
            attempts=attempts,
        )
