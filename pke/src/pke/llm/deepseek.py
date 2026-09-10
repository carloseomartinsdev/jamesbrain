"""DeepSeek via httpx. JSON mode + validação local. Sem persist/query."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx
import truststore

truststore.inject_into_ssl()

from pke.llm.config import DeepSeekConfig
from pke.llm.errors import (
    LlmAuthenticationError,
    LlmInvalidResponseError,
    LlmProviderError,
    LlmRateLimitError,
    LlmTimeoutError,
)
from pke.llm.models import LlmCallMetadata, LlmStructuredRequest, LlmStructuredResponse

_LOG = logging.getLogger("pke.llm")


class DeepSeekProvider:
    def __init__(
        self,
        config: DeepSeekConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._sleeper = sleeper or time.sleep
        self._clock = clock or time.monotonic
        timeout = httpx.Timeout(config.timeout_seconds)
        self._client = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {config.api_key_value}",
                "Content-Type": "application/json",
            },
        )
        self.last_request_body: dict[str, Any] | None = None

    def close(self) -> None:
        self._client.close()

    def generate_structured(self, request: LlmStructuredRequest) -> LlmStructuredResponse:
        body = {
            "model": self._config.model,
            "messages": [m.model_dump() for m in request.messages],
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        self.last_request_body = body
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
                self._log_ok(metadata, len(content))
                return LlmStructuredResponse(content=content, metadata=metadata)
            except (LlmTimeoutError, LlmRateLimitError) as exc:
                last_error = exc
                if not self._should_retry(attempts, max_tries):
                    raise
                self._backoff(attempts)
            except LlmProviderError as exc:
                last_error = exc
                if not getattr(exc, "retryable", False) or not self._should_retry(attempts, max_tries):
                    raise
                self._backoff(attempts)
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
        if status < 400:
            return response
        _LOG.warning("llm_http status=%s", status)
        if status in {401, 403}:
            raise LlmAuthenticationError("autenticação recusada")
        if status == 429:
            raise LlmRateLimitError("rate limit")
        if status >= 500:
            err = LlmProviderError(f"provider {status}")
            err.retryable = True
            raise err
        raise LlmProviderError(f"provider {status}")

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
        finish = choices[0].get("finish_reason")
        if finish == "length":
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
        finish = None
        if choices:
            finish = choices[0].get("finish_reason")
        return LlmCallMetadata(
            provider="deepseek",
            model=payload.get("model") or self._config.model,
            request_id=payload.get("id"),
            latency_ms=latency,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            finish_reason=finish,
            attempts=attempts,
        )

    def _should_retry(self, attempts: int, max_tries: int) -> bool:
        return attempts < max_tries

    def _backoff(self, attempts: int) -> None:
        delay = self._config.retry_backoff_seconds * (2 ** (attempts - 1))
        self._sleeper(delay)

    def _log_ok(self, metadata: LlmCallMetadata, size: int) -> None:
        _LOG.info(
            "llm_ok provider=%s model=%s request_id=%s latency_ms=%.0f bytes=%s status=ok",
            metadata.provider,
            metadata.model,
            metadata.request_id,
            metadata.latency_ms,
            size,
        )
        if self._config.log_payloads:
            _LOG.warning("llm_payload_opt_in ativo — inseguro para produção")
