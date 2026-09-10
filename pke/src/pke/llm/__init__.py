"""Camada LLM. Interpreta linguagem; não persiste nem consulta conhecimento."""

from pke.llm.config import DEFAULT_MODEL, DeepSeekConfig
from pke.llm.deepseek import DeepSeekProvider
from pke.llm.errors import (
    LlmAuthenticationError,
    LlmConfigurationError,
    LlmError,
    LlmInvalidResponseError,
    LlmProviderError,
    LlmRateLimitError,
    LlmSchemaValidationError,
    LlmTimeoutError,
)
from pke.llm.models import (
    LlmCallMetadata,
    LlmMessage,
    LlmMetrics,
    LlmStructuredRequest,
    LlmStructuredResponse,
)
from pke.llm.provider import LlmProvider

__all__ = [
    "DEFAULT_MODEL",
    "DeepSeekConfig",
    "DeepSeekProvider",
    "LlmAuthenticationError",
    "LlmCallMetadata",
    "LlmConfigurationError",
    "LlmError",
    "LlmInvalidResponseError",
    "LlmMessage",
    "LlmMetrics",
    "LlmProvider",
    "LlmProviderError",
    "LlmRateLimitError",
    "LlmSchemaValidationError",
    "LlmStructuredRequest",
    "LlmStructuredResponse",
    "LlmTimeoutError",
]
