"""Pending semantic operation — workflow state (not Knowledge Core).

Conversation != Knowledge != Session.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

AnswerKind = Literal[
    "entity_reference",
    "dimension",
    "value",
    "correction_target",
    "none",
]


class PendingOperationStatus(StrEnum):
    PENDING = "pending"
    ANSWERED = "answered"
    RESOLVED = "resolved"
    FAILED = "failed"
    CANCELLED = "cancelled"


# I12.13 entity-reference MVP + I12.14 bounded dimension/value expansion.
SUPPORTED_ENTITY_SLOTS = frozenset(
    {
        "measured_entity",
        "relation_subject",
        "relation_object",
        "state_entity",
        "attribute_entity",
    }
)

SUPPORTED_DIMENSION_SLOTS = frozenset(
    {
        "measurement_dimension",
        "attribute_dimension",
    }
)

SUPPORTED_VALUE_SLOTS = frozenset(
    {
        "state_value",
    }
)

SUPPORTED_ANSWER_KINDS = frozenset({"entity_reference", "dimension", "value"})

MAX_CLARIFICATION_ROUNDS_PER_PENDING_OPERATION = 1


class PendingSemanticOperation(BaseModel):
    """Structured resume state for bounded clarification recovery."""

    model_config = ConfigDict(extra="forbid")

    pending_operation_id: str = Field(default_factory=lambda: str(uuid4()))
    originating_raw: str
    """Immutable original utterance (evidence). Never reinterpreted."""

    proposal_dump: dict[str, Any]
    """Frozen original SemanticProposal dump."""

    missing_slot: str
    expected_answer_kind: AnswerKind
    primitive: str
    reason: str
    question_key: str

    status: PendingOperationStatus = PendingOperationStatus.PENDING
    rounds_used: int = 0
    committed_measurement_ids: list[str] = Field(default_factory=list)
    committed_event_ids: list[str] = Field(default_factory=list)
    committed_relation_ids: list[str] = Field(default_factory=list)
    committed_state_ids: list[str] = Field(default_factory=list)
    committed_attribute_ids: list[str] = Field(default_factory=list)

    answer_text: str | None = None
    """Last clarification answer (new evidence), if any."""

    def is_supported(self) -> bool:
        if self.expected_answer_kind == "entity_reference":
            return self.missing_slot in SUPPORTED_ENTITY_SLOTS
        if self.expected_answer_kind == "dimension":
            return self.missing_slot in SUPPORTED_DIMENSION_SLOTS
        if self.expected_answer_kind == "value":
            return self.missing_slot in SUPPORTED_VALUE_SLOTS
        return False
