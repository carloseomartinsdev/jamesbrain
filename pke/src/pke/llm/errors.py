"""Erros da camada LLM. Sem ValueError genérico. Sem segredos na mensagem."""


class LlmError(Exception):
    """Falha do provider ou da validação da proposta do modelo."""


class LlmConfigurationError(LlmError):
    """API key ausente, URL inválida, modelo não configurado."""


class LlmAuthenticationError(LlmError):
    """401/403. Não retry."""


class LlmTimeoutError(LlmError):
    """Timeout de rede. Retry limitado."""


class LlmRateLimitError(LlmError):
    """429. Retry limitado."""


class LlmProviderError(LlmError):
    """5xx ou falha genérica do provider. Retry só em 5xx."""


class LlmInvalidResponseError(LlmError):
    """Corpo vazio, JSON ilegível, finish_reason=length.

    Retryable at Interpreter RetryPolicy (pre-commit), not as knowledge write.
    """


class LlmSchemaValidationError(LlmError):
    """JSON parseável mas inválido no contrato Pydantic/wire.

    Retryable at Interpreter RetryPolicy (pre-commit). Not a semantic repair loop.
    """

    def __init__(
        self,
        message: str = "proposta do modelo rejeitada pelo Pydantic",
        *,
        issues: list[dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.issues = issues or []

    def summary(self) -> str:
        if not self.issues:
            return str(self)
        first = self.issues[0]
        path = first.get("path") or "?"
        reason = first.get("reason") or first.get("type") or "invalid"
        extra = f" (+{len(self.issues) - 1} more)" if len(self.issues) > 1 else ""
        return f"path: {path} reason: {reason}{extra}"
