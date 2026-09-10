"""IDs de produto. Distintos de KnowledgeReference / assertion_id."""

from __future__ import annotations

from pke.domain.ids import new_ulid


def user_id() -> str:
    return f"usr_{new_ulid()}"


def session_id() -> str:
    return f"sess_{new_ulid()}"


def conversation_id() -> str:
    return f"conv_{new_ulid()}"


def message_id() -> str:
    return f"msg_{new_ulid()}"


def clarification_id() -> str:
    return f"clar_{new_ulid()}"


def request_id() -> str:
    return f"req_{new_ulid()}"
