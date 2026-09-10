from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from pke.llm import (
    DeepSeekConfig,
    DeepSeekProvider,
    LlmAuthenticationError,
    LlmCallMetadata,
    LlmConfigurationError,
    LlmInvalidResponseError,
    LlmMessage,
    LlmProviderError,
    LlmRateLimitError,
    LlmStructuredRequest,
    LlmTimeoutError,
)


def _config(**kwargs) -> DeepSeekConfig:
    data = {
        "api_key": "sk-secret-test-key",
        "timeout_seconds": 1,
        "max_retries": 2,
        "retry_backoff_seconds": 0,
    }
    data.update(kwargs)
    return DeepSeekConfig.model_validate(data)


def _request() -> LlmStructuredRequest:
    return LlmStructuredRequest(
        messages=[
            LlmMessage(role="system", content="json"),
            LlmMessage(role="user", content="hoje"),
        ],
        json_schema={"type": "object"},
    )


def _ok_payload(content: str = '{"ir_kind":"ingest"}') -> dict:
    return {
        "id": "req-1",
        "model": "deepseek-chat",
        "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }


def test_config_from_env_and_repr_hides_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-hidden-value")
    cfg = DeepSeekConfig.from_env()
    dumped = repr(cfg)
    assert "sk-hidden-value" not in dumped
    assert "***" in dumped
    assert "sk-hidden-value" not in str(cfg.model_dump())
    with pytest.raises(LlmConfigurationError):
        monkeypatch.delenv("DEEPSEEK_API_KEY")
        DeepSeekConfig.from_env()


def test_request_shape_and_json_mode() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_ok_payload())

    provider = DeepSeekProvider(_config(), transport=httpx.MockTransport(handler), sleeper=lambda _: None)
    provider.generate_structured(_request())
    assert seen[0].url.path.endswith("/chat/completions")
    body = json.loads(seen[0].content)
    assert body["model"] == "deepseek-chat"
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system"
    assert "sk-secret-test-key" not in json.dumps(provider.last_request_body)


def test_timeout_maps_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    provider = DeepSeekProvider(_config(max_retries=0), transport=httpx.MockTransport(handler))
    with pytest.raises(LlmTimeoutError):
        provider.generate_structured(_request())


def test_429_retries_then_succeeds() -> None:
    hits = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        if hits["n"] < 3:
            return httpx.Response(429, json={"error": "rate"})
        return httpx.Response(200, json=_ok_payload())

    sleeps: list[float] = []
    provider = DeepSeekProvider(
        _config(),
        transport=httpx.MockTransport(handler),
        sleeper=sleeps.append,
    )
    result = provider.generate_structured(_request())
    assert hits["n"] == 3
    assert sleeps == [0.0, 0.0]
    assert isinstance(result.metadata, LlmCallMetadata)
    assert result.metadata.attempts == 3
    assert result.metadata.request_id == "req-1"


def test_auth_error_no_retry() -> None:
    hits = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(401, json={"error": "no"})

    provider = DeepSeekProvider(_config(), transport=httpx.MockTransport(handler), sleeper=lambda _: None)
    with pytest.raises(LlmAuthenticationError):
        provider.generate_structured(_request())
    assert hits["n"] == 1


def test_5xx_retries_limited() -> None:
    hits = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(503, json={"error": "down"})

    provider = DeepSeekProvider(_config(), transport=httpx.MockTransport(handler), sleeper=lambda _: None)
    with pytest.raises(LlmProviderError):
        provider.generate_structured(_request())
    assert hits["n"] == 3


def test_invalid_json_content() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_payload("OK"))

    provider = DeepSeekProvider(_config(max_retries=0), transport=httpx.MockTransport(handler))
    with pytest.raises(LlmInvalidResponseError):
        provider.generate_structured(_request())


def test_llm_package_does_not_import_persist_or_query() -> None:
    root = Path(__file__).parents[2] / "src" / "pke" / "llm"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "pke.persist" not in text
        assert "pke.query" not in text
        assert "pke.application" not in text
