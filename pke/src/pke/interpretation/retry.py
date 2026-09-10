"""Interpreter provider retry — pre-commit only (I12.2 / INTERPRETER-RETRY-01).

provider retry ≠ knowledge write retry.
Authority: Interpreter layer. Not repositories / materializer / Core.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable

from pke.interpretation.interpreter import InterpretationError
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

# Engine v1 freeze
MAX_ATTEMPTS = 2
DEFAULT_RETRY_DELAY_SECONDS = 0.05
MAX_RETRY_DELAY_SECONDS = 2.0

# Rate-limit policy (explicit): one bounded retry, no arbitrary Retry-After sleep.
RATE_LIMIT_POLICY = "RETRY_ONCE_BOUNDED"

RETRY_STRUCTURAL_REMINDER = (
    "Previous response did not satisfy the required structured-output contract. "
    "Return only a valid JSON response matching the schema. "
    "No markdown fences. Do not invent facts, IDs, times, primitives, or canonical concepts."
)


class FailureClass(StrEnum):
    TIMEOUT = "timeout"
    TEMPORARY_NETWORK = "temporary_network"
    HTTP_5XX = "http_5xx"
    RATE_LIMITED = "rate_limited"
    EMPTY_RESPONSE = "empty_response"
    INVALID_JSON = "invalid_json"
    SCHEMA_INVALID = "schema_invalid"
    TRUNCATED = "truncated"
    AUTH = "authentication"
    CONFIG = "configuration"
    PERMANENT_PROVIDER = "permanent_provider"
    SEMANTIC_NON_RETRYABLE = "semantic_non_retryable"
    CLIENT_INPUT = "client_input"
    UNKNOWN = "unknown"


_SEMANTIC_PREFIXES = (
    "proposal_semantics:",
    "semantic_resolution:",
    "acceptance_guard:",
)


@dataclass
class InterpreterRetryMetrics:
    """Diagnostic counters for one process / shared interpreter instance."""

    interpreter_requests: int = 0
    provider_attempts: int = 0
    retry_triggered: int = 0
    retry_succeeded: int = 0
    retry_exhausted: int = 0
    non_retryable_failures: int = 0
    invalid_json_responses: int = 0
    schema_invalid_responses: int = 0
    timeout_responses: int = 0
    temporary_provider_failures: int = 0
    first_attempt_success: int = 0
    recovered_requests: int = 0


@dataclass(frozen=True)
class RetryPolicy:
    """Singular bounded retry authority for Engine v1."""

    max_attempts: int = MAX_ATTEMPTS
    delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS
    rate_limit_policy: str = RATE_LIMIT_POLICY

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.max_attempts > 2:
            # Engine v1 hard upper bound = 2 (original + one retry)
            object.__setattr__(self, "max_attempts", max(1, min(2, self.max_attempts)))
        delay = max(0.0, min(float(self.delay_seconds), MAX_RETRY_DELAY_SECONDS))
        object.__setattr__(self, "delay_seconds", delay)

    @classmethod
    def from_env(cls) -> RetryPolicy:
        max_raw = os.environ.get("PKE_INTERPRETER_MAX_ATTEMPTS", str(MAX_ATTEMPTS)).strip()
        delay_raw = os.environ.get(
            "PKE_INTERPRETER_RETRY_DELAY_SECONDS", str(DEFAULT_RETRY_DELAY_SECONDS)
        ).strip()
        try:
            max_attempts = int(max_raw)
        except ValueError:
            max_attempts = MAX_ATTEMPTS
        try:
            delay = float(delay_raw)
        except ValueError:
            delay = DEFAULT_RETRY_DELAY_SECONDS
        return cls(max_attempts=max_attempts, delay_seconds=delay)

    def classify(self, exc: BaseException) -> FailureClass:
        root = exc.__cause__ if isinstance(exc, InterpretationError) and exc.__cause__ else exc
        if isinstance(root, LlmTimeoutError):
            return FailureClass.TIMEOUT
        if isinstance(root, LlmRateLimitError):
            return FailureClass.RATE_LIMITED
        if isinstance(root, LlmAuthenticationError):
            return FailureClass.AUTH
        if isinstance(root, LlmConfigurationError):
            return FailureClass.CONFIG
        if isinstance(root, LlmSchemaValidationError):
            return FailureClass.SCHEMA_INVALID
        if isinstance(root, LlmInvalidResponseError):
            msg = str(root).lower()
            if "vazio" in msg or "empty" in msg:
                return FailureClass.EMPTY_RESPONSE
            if "truncat" in msg or "length" in msg:
                return FailureClass.TRUNCATED
            return FailureClass.INVALID_JSON
        if isinstance(root, LlmProviderError):
            if getattr(root, "retryable", False):
                text = str(root).lower()
                if "rede" in text or "network" in text or "connection" in text:
                    return FailureClass.TEMPORARY_NETWORK
                return FailureClass.HTTP_5XX
            return FailureClass.PERMANENT_PROVIDER
        if isinstance(exc, InterpretationError):
            msg = str(exc)
            lower = msg.lower()
            if any(msg.startswith(p) or lower.startswith(p) for p in _SEMANTIC_PREFIXES):
                return FailureClass.SEMANTIC_NON_RETRYABLE
            if "proposal_transport:schema" in lower or "schema" in lower:
                return FailureClass.SCHEMA_INVALID
            if lower.startswith("normalization:") or "json_invalid" in lower or "malformed" in lower:
                return FailureClass.INVALID_JSON
            if lower.startswith("provider:"):
                # wrapped provider message without typed cause
                if "timeout" in lower:
                    return FailureClass.TIMEOUT
                if "401" in lower or "403" in lower or "autent" in lower:
                    return FailureClass.AUTH
                if any(code in lower for code in ("500", "502", "503", "504")):
                    return FailureClass.HTTP_5XX
                if "vazio" in lower or "empty" in lower:
                    return FailureClass.EMPTY_RESPONSE
                if "json" in lower:
                    return FailureClass.INVALID_JSON
                return FailureClass.TEMPORARY_NETWORK
        return FailureClass.UNKNOWN

    def is_retryable(self, exc: BaseException, *, attempt: int) -> bool:
        """attempt is 1-based index of the failed attempt."""
        if attempt >= self.max_attempts:
            return False
        klass = self.classify(exc)
        if klass in {
            FailureClass.AUTH,
            FailureClass.CONFIG,
            FailureClass.PERMANENT_PROVIDER,
            FailureClass.SEMANTIC_NON_RETRYABLE,
            FailureClass.CLIENT_INPUT,
        }:
            return False
        if klass is FailureClass.RATE_LIMITED:
            return self.rate_limit_policy == RATE_LIMIT_POLICY
        if klass is FailureClass.UNKNOWN:
            # Only retry UNKNOWN when it is a typed LlmError subclass we missed
            root = exc.__cause__ if isinstance(exc, InterpretationError) and exc.__cause__ else exc
            return isinstance(root, LlmError) and not isinstance(
                root, (LlmAuthenticationError, LlmConfigurationError)
            )
        return klass in {
            FailureClass.TIMEOUT,
            FailureClass.TEMPORARY_NETWORK,
            FailureClass.HTTP_5XX,
            FailureClass.EMPTY_RESPONSE,
            FailureClass.INVALID_JSON,
            FailureClass.SCHEMA_INVALID,
            FailureClass.TRUNCATED,
            FailureClass.RATE_LIMITED,
        }


def new_interpreter_request_id() -> str:
    return str(uuid.uuid4())


def is_transient_provider_failure(exc: LlmError | None) -> bool:
    """API/presenter: map exhausted operational provider failures to PROVIDER_UNAVAILABLE.

    Auth/config and clear HTTP 4xx client errors are not temporary unavailability.
    This is UX classification — not a second retry loop.
    """
    if exc is None:
        return False
    if isinstance(exc, (LlmAuthenticationError, LlmConfigurationError)):
        return False
    if isinstance(exc, LlmProviderError):
        text = str(exc)
        for code in ("400", "401", "403", "404", "409", "422"):
            if f"provider {code}" in text:
                return False
        return True
    policy = RetryPolicy()
    klass = policy.classify(exc)
    return klass in {
        FailureClass.TIMEOUT,
        FailureClass.TEMPORARY_NETWORK,
        FailureClass.HTTP_5XX,
        FailureClass.RATE_LIMITED,
        FailureClass.EMPTY_RESPONSE,
        FailureClass.INVALID_JSON,
        FailureClass.SCHEMA_INVALID,
        FailureClass.TRUNCATED,
    }


@dataclass
class AttemptRecord:
    attempt_number: int
    failure_class: FailureClass | None = None
    retry_decision: str | None = None
    provider_request_id: str | None = None
    success: bool = False


@dataclass
class InterpreterRequestTrace:
    interpreter_request_id: str
    attempts: list[AttemptRecord] = field(default_factory=list)
    recovered: bool = False
    exhausted: bool = False


Sleeper = Callable[[float], None]
