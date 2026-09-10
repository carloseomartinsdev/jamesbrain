"""Contrato de interpretação. Fake, Scripted ou DeepSeek — mesmo Interpreter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from pke.domain.value_objects import UserContext
from pke.interpretation.models import IngestIR, InterpretationResult, QueryIR


class InterpretationError(Exception):
    """Falha de interpretação (script ausente, IR inválida, etc.)."""


class InterpretationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserContext
    recent_event_ids: list[str] = Field(default_factory=list)
    # Bounded prior user utterances for Correction acceptance (not Knowledge Store rows).
    recent_utterances: list[str] = Field(default_factory=list)
    client_request_id: str | None = None
    """Portal/Core idempotency id — used as request-log file name when present."""
    pke_request_id: str | None = None


class Interpreter(Protocol):
    """Fronteira estável para um LlmInterpreter futuro.

    Implementações atuais não chamam rede nem conhecem persistência.
    """

    def interpret(self, raw: str, ctx: InterpretationContext) -> InterpretationResult: ...


class FakeInterpreter:
    """Devolve IR pré-construída indexada pelo texto bruto. Usado em testes."""

    def __init__(
        self,
        responses: Mapping[str, InterpretationResult] | None = None,
    ) -> None:
        self._responses: dict[str, InterpretationResult] = dict(responses or {})

    def register(self, raw: str, ir: InterpretationResult) -> None:
        self._responses[raw] = ir

    def interpret(self, raw: str, ctx: InterpretationContext) -> InterpretationResult:
        del ctx
        if raw not in self._responses:
            raise InterpretationError(f"nenhuma IR scriptada para: {raw!r}")
        return self._responses[raw]


class ScriptedInterpreter:
    """Consome uma fila de IRs na ordem. Útil para sequências (fato → correção)."""

    def __init__(self, queue: Sequence[InterpretationResult]) -> None:
        self._queue: list[InterpretationResult] = list(queue)

    def interpret(self, raw: str, ctx: InterpretationContext) -> InterpretationResult:
        del ctx
        if not self._queue:
            raise InterpretationError("script de interpretação esgotado")
        ir = self._queue.pop(0)
        if isinstance(ir, (IngestIR, QueryIR)):
            return ir.model_copy(update={"raw_input": raw})
        raise InterpretationError("item do script não é IngestIR nem QueryIR")
