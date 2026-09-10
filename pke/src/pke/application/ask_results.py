"""Resultado de Ask. Sem frase de UI."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pke.query.results import QueryResult
from pke.query.spec import ResolvedQuerySpec
from pke.reasoning.issues import Issue


class AskStatus(StrEnum):
    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    NO_RESULTS = "no_results"
    REJECTED = "rejected"
    UNSUPPORTED = "unsupported"


class AskClarification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clarification_key: str
    reason: str
    blocking: bool = True
    candidate_entity_ids: list[str] = Field(default_factory=list)


class AskResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AskStatus
    raw_text: str
    query_result: QueryResult | None = None
    resolved_spec: ResolvedQuerySpec | None = None
    issues: list[Issue] = Field(default_factory=list)
    clarification: AskClarification | None = None
    resolved_entity_ids: list[str] = Field(default_factory=list)
