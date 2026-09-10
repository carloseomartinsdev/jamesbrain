"""Configuração DeepSeek. A chave nunca vai para repr, log ou exceção."""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from pke.llm.errors import LlmConfigurationError

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"
API_KEY_ENV = "DEEPSEEK_API_KEY"


class DeepSeekConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = Field(default=30.0, gt=0)
    # Engine v1 (I12.2): application Interpreter RetryPolicy owns retries.
    # Keep SDK/http adapter at 0 by default to avoid attempt multiplication.
    max_retries: int = Field(default=0, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.2, ge=0)
    log_payloads: bool = False

    @classmethod
    def from_env(cls, **overrides: object) -> DeepSeekConfig:
        raw = os.environ.get(API_KEY_ENV, "").strip()
        if not raw:
            raise LlmConfigurationError(f"{API_KEY_ENV} ausente")
        data: dict[str, object] = {"api_key": raw}
        model = os.environ.get("DEEPSEEK_MODEL", "").strip()
        if model:
            data["model"] = model
        timeout = os.environ.get("PKE_PROVIDER_TIMEOUT_SECONDS", "").strip()
        if timeout:
            data["timeout_seconds"] = float(timeout)
        sdk_retries = os.environ.get("PKE_PROVIDER_MAX_RETRIES", "").strip()
        if sdk_retries:
            data["max_retries"] = int(sdk_retries)
        data.update(overrides)
        return cls.model_validate(data)

    @property
    def api_key_value(self) -> str:
        return self.api_key.get_secret_value()

    def __repr__(self) -> str:
        return (
            f"DeepSeekConfig(model={self.model!r}, base_url={self.base_url!r}, "
            f"timeout_seconds={self.timeout_seconds}, api_key=***)"
        )
