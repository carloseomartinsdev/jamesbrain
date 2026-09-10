"""Contrato de provider. Não assume DeepSeek."""

from __future__ import annotations

from typing import Protocol

from pke.llm.models import LlmStructuredRequest, LlmStructuredResponse


class LlmProvider(Protocol):
    def generate_structured(self, request: LlmStructuredRequest) -> LlmStructuredResponse: ...
