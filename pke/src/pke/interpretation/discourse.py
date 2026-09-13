"""Conversation-scoped discourse focus — not knowledge, not a linguistic dump.

The Interpreter may copy entity_ids listed here. The PKE never infers follow-up
from raw_input or previous utterance text.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DiscourseDecision(StrEnum):
    CONTINUE = "continue"
    NEW_TOPIC = "new_topic"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


class DiscourseReferent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    type_key: str | None = None
    display_name: str | None = None
    role: str | None = None
    salience: float = 1.0


class DiscourseFocus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primitive: str | None = None
    relation_type: str | None = None
    target_type: str | None = None
    entity_ids: list[str] = Field(default_factory=list)
    display_name: str | None = None


class DiscoursePendingIntent(BaseModel):
    """Frozen query waiting for a missing subject — conversation-scoped, not knowledge."""

    model_config = ConfigDict(extra="forbid")

    operation: str = "attribute_query"
    attribute_dimension_key: str | None = None
    missing_role: str | None = "subject"
    candidate_entity_ids: list[str] = Field(default_factory=list)
    query_dump: dict[str, Any] | None = None


class DiscourseState(BaseModel):
    """Temporary conversation focus. Isolated by conversation_id via engine session."""

    model_config = ConfigDict(extra="forbid")

    active_focus: DiscourseFocus | None = None
    recent_referents: list[DiscourseReferent] = Field(default_factory=list)
    last_query_primitive: str | None = None
    last_relation_type: str | None = None
    last_result_kind: str | None = None
    last_update_reason: str | None = None
    pending_intent: DiscoursePendingIntent | None = None
    idle_turns: int = 0


MAX_RECENT_REFERENTS = 8
MAX_IDLE_TURNS = 8


def allowed_entity_ids(state: DiscourseState | None) -> list[str]:
    if state is None:
        return []
    ids: list[str] = []
    seen: set[str] = set()

    def add(eid: str | None) -> None:
        if eid and eid not in seen:
            seen.add(eid)
            ids.append(eid)

    if state.active_focus is not None:
        for eid in state.active_focus.entity_ids:
            add(eid)
    for item in state.recent_referents:
        add(item.entity_id)
    if state.pending_intent is not None:
        for eid in state.pending_intent.candidate_entity_ids:
            add(eid)
    return ids


def discourse_prompt_payload(
    state: DiscourseState | None,
    utterances: list[str],
    *,
    utterance_limit: int = 6,
) -> dict[str, object]:
    cleaned = [u.strip() for u in utterances if (u or "").strip()][-utterance_limit:]
    allowed = allowed_entity_ids(state)
    pending = None
    if state is not None and state.pending_intent is not None:
        pending = {
            "operation": state.pending_intent.operation,
            "attribute_dimension_key": state.pending_intent.attribute_dimension_key,
            "missing_role": state.pending_intent.missing_role,
            "candidate_entity_ids": list(state.pending_intent.candidate_entity_ids),
        }
    structured: dict[str, object] = {
        "active_focus": state.active_focus.model_dump(mode="json") if state and state.active_focus else None,
        "recent_referents": [r.model_dump(mode="json") for r in (state.recent_referents if state else [])],
        "allowed_entity_ids": allowed,
        "last_query_primitive": state.last_query_primitive if state else None,
        "last_relation_type": state.last_relation_type if state else None,
        "last_result_kind": state.last_result_kind if state else None,
        "pending_intent": pending,
    }
    return {
        "recent_user_utterances": cleaned,
        "structured": structured,
    }
