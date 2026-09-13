"""Request-scoped correlation IDs for semantic traces.

Does not allocate new IDs. Bind whatever the caller already has.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class TraceIds:
    client_request_id: str | None = None
    pke_request_id: str | None = None
    interpreter_request_id: str | None = None
    provider_request_id: str | None = None
    conversation_id: str | None = None
    user_message_id: str | None = None

    def file_id(self) -> str | None:
        return self.client_request_id or self.pke_request_id or self.interpreter_request_id


_IDS: ContextVar[TraceIds | None] = ContextVar("pke_trace_ids", default=None)
_RESOLUTIONS: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "pke_entity_resolutions", default=None
)


def current_trace() -> TraceIds:
    return _IDS.get() or TraceIds()


def bind_trace(**kwargs: str | None) -> Token:
    current = current_trace()
    updated = replace(
        current,
        **{key: value for key, value in kwargs.items() if value is not None},
    )
    return _IDS.set(updated)


def update_trace(**kwargs: str | None) -> None:
    current = current_trace()
    _IDS.set(
        replace(
            current,
            **{key: value for key, value in kwargs.items() if value is not None},
        )
    )


def reset_trace(token: Token) -> None:
    _IDS.reset(token)
    _RESOLUTIONS.set(None)


def record_resolution_payload(item: dict[str, Any]) -> None:
    items = list(_RESOLUTIONS.get() or [])
    items.append(item)
    _RESOLUTIONS.set(items)


def take_resolution_payloads() -> list[dict[str, Any]]:
    items = list(_RESOLUTIONS.get() or [])
    _RESOLUTIONS.set([])
    return items
