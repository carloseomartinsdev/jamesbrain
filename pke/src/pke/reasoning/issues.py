"""Issues de reasoning — lógica usa `code`, não o texto."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    rule_id: str
    message: str
    severity: Severity
    field: str | None = None
    concept_key: str | None = None
