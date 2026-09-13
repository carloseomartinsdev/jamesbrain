"""Text LLM adapter for the Presenter. Same provider family as Interpreter, different role."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass


class PresenterTimeout(Exception):
    pass


class PresenterProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        exception_class: str | None = None,
        provider_error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.exception_class = exception_class or type(self).__name__
        self.provider_error_code = provider_error_code


@dataclass(frozen=True)
class PresenterLlmResult:
    text: str
    model: str
    latency_ms: int
    provider_request_id: str | None = None


class PresenterProvider(Protocol):
    def complete(self, *, system: str, user: str, timeout_seconds: float) -> PresenterLlmResult:
        ...


class DeepSeekChatProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._transport = transport

    def complete(self, *, system: str, user: str, timeout_seconds: float) -> PresenterLlmResult:
        timeout = httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds))
        url = f"{self._base_url}/chat/completions"
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": 180,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout, transport=self._transport) as client:
                response = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise PresenterTimeout("presenter llm timeout") from exc
        except httpx.HTTPError as exc:
            kind = type(exc).__name__
            raise PresenterProviderError(
                f"presenter llm unavailable ({kind})",
                exception_class=kind,
            ) from exc
        if response.status_code == 401:
            raise PresenterProviderError(
                "presenter llm authentication failed",
                provider_error_code="401",
            )
        if response.status_code == 429:
            raise PresenterProviderError(
                "presenter llm rate limited",
                provider_error_code="429",
            )
        if response.status_code >= 400:
            snippet = (response.text or "").strip().replace("\n", " ")[:180]
            raise PresenterProviderError(
                f"presenter llm http {response.status_code}" + (f": {snippet}" if snippet else ""),
                provider_error_code=str(response.status_code),
            )
        try:
            decoded: dict[str, Any] = response.json()
        except json.JSONDecodeError as exc:
            raise PresenterProviderError(
                "presenter llm invalid json",
                exception_class="JSONDecodeError",
            ) from exc
        choices = decoded.get("choices") if isinstance(decoded, dict) else None
        if not isinstance(choices, list) or not choices:
            raise PresenterProviderError("presenter llm empty choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise PresenterProviderError("presenter llm missing content")
        return PresenterLlmResult(
            text=content,
            model=str(decoded.get("model") or self._model),
            latency_ms=int((time.perf_counter() - started) * 1000),
            provider_request_id=str(decoded["id"]) if decoded.get("id") else None,
        )
