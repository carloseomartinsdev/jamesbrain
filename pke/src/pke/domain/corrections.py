"""Correction — epistemic meta-knowledge ledger (not a world-model primitive)."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator


class KnowledgePrimitiveKind(StrEnum):
    """Stable persisted discriminators for typed KnowledgeReference."""

    EVENT = "event"
    MEASUREMENT = "measurement"
    RELATION = "relation"
    STATE = "state"
    ATTRIBUTE = "attribute"


SUPPORTED_KNOWLEDGE_KINDS: frozenset[KnowledgePrimitiveKind] = frozenset(KnowledgePrimitiveKind)


class CorrectionOperation(StrEnum):
    RETRACT = "retract"
    REPLACE = "replace"


class AssertionEffectiveness(StrEnum):
    EFFECTIVE = "effective"
    INEFFECTIVE = "ineffective"
    UNKNOWN = "unknown"


class KnowledgeReference(BaseModel):
    """Typed assertion identity. user_id scopes isolation; not duplicated in ledger FK columns."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: KnowledgePrimitiveKind
    assertion_id: str
    user_id: str

    @model_validator(mode="after")
    def _nonempty(self) -> KnowledgeReference:
        if not self.assertion_id.strip():
            raise ValueError("assertion_id required")
        if not self.user_id.strip():
            raise ValueError("user_id required")
        return self

    def identity_key(self) -> tuple[str, str, str]:
        return (self.user_id, self.kind.value, self.assertion_id)


class Correction(BaseModel):
    """Committed correction ledger row — epistemic lineage only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    user_id: str
    operation: CorrectionOperation
    target: KnowledgeReference
    replacement: KnowledgeReference | None = None
    raw_input_id: str | None = None
    source_id: str | None = None
    recorded_at: dt.datetime

    @model_validator(mode="after")
    def _invariants(self) -> Correction:
        if self.target.user_id != self.user_id:
            raise ValueError("target.user_id must equal correction.user_id")
        if self.operation is CorrectionOperation.RETRACT:
            if self.replacement is not None:
                raise ValueError("RETRACT forbids replacement")
        elif self.operation is CorrectionOperation.REPLACE:
            if self.replacement is None:
                raise ValueError("REPLACE requires replacement")
            if self.replacement.user_id != self.user_id:
                raise ValueError("replacement.user_id must equal correction.user_id")
            if self.replacement.identity_key() == self.target.identity_key():
                raise ValueError("REPLACE forbids self-replacement")
        return self
