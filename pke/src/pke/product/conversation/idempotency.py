"""Product idempotency fingerprints and claim outcomes.

PRODUCT_IDEMPOTENCY_AUTHORITY — ProductStore + ConversationOrchestrator.
Durable SQLite records (not memory-only).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class IdempotencyStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERY_REQUIRED = "recovery_required"


class IdempotencyClaimResult(StrEnum):
    PROCEED = "proceed"
    REPLAY = "replay"
    CONFLICT = "conflict"
    IN_PROGRESS = "in_progress"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass(frozen=True)
class IdempotencyRecord:
    user_id: str
    client_request_id: str
    request_fingerprint: str
    conversation_id: str | None
    status: str
    response_json: dict[str, Any] | None
    created_at: str
    updated_at: str = ""


def fingerprint_payload(parts: dict[str, Any]) -> str:
    """Stable hash over canonical request identity (not secrets)."""
    canonical = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def message_fingerprint(*, text: str, conversation_id: str | None) -> str:
    return fingerprint_payload(
        {
            "kind": "message",
            "text": text,
            "conversation_id": conversation_id or "",
        }
    )


def clarification_fingerprint(
    *,
    clarification_id: str,
    text: str | None,
    option_id: str | None,
) -> str:
    return fingerprint_payload(
        {
            "kind": "clarification_answer",
            "clarification_id": clarification_id,
            "text": (text or "").strip(),
            "option_id": option_id or "",
        }
    )
