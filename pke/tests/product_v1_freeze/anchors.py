"""Product v1 freeze anchors P01–P50 (hand-audited)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal[
    "auth",
    "ownership",
    "write",
    "query",
    "clarification",
    "abstain",
    "idempotency",
    "recovery",
    "durability",
    "isolation",
    "boundary",
    "correction",
]


@dataclass(frozen=True)
class ProductFreezeAnchor:
    anchor_id: str
    kind: Kind
    title: str
    safety_expectation: str


PRODUCT_FREEZE_ANCHORS: list[ProductFreezeAnchor] = [
    ProductFreezeAnchor("P01", "auth", "register creates session", "server identity"),
    ProductFreezeAnchor("P02", "auth", "login issues bearer", "server identity"),
    ProductFreezeAnchor("P03", "auth", "invalid login 401", "no leak"),
    ProductFreezeAnchor("P04", "auth", "/me requires auth", "401"),
    ProductFreezeAnchor("P05", "auth", "logout revokes session", "401 after"),
    ProductFreezeAnchor("P06", "auth", "multi-session allowed", "both valid"),
    ProductFreezeAnchor("P07", "auth", "dev token rejected in session mode", "no DEV_AUTH fallback"),
    ProductFreezeAnchor("P08", "auth", "body user_id rejected", "extra=forbid"),
    ProductFreezeAnchor("P09", "ownership", "cross-user conversation read 404", "ownership"),
    ProductFreezeAnchor("P10", "ownership", "cross-user conversation write 404", "ownership"),
    ProductFreezeAnchor("P11", "ownership", "cross-user messages 404", "ownership"),
    ProductFreezeAnchor("P12", "ownership", "cross-user clarification 404", "ownership"),
    ProductFreezeAnchor("P13", "write", "knowledge write committed", "FALSE_COMMIT=0"),
    ProductFreezeAnchor("P14", "write", "write acknowledgement natural", "UX"),
    ProductFreezeAnchor("P15", "write", "user message durable", "reload"),
    ProductFreezeAnchor("P16", "write", "assistant durable", "reload"),
    ProductFreezeAnchor("P17", "query", "query answers from knowledge", "epistemic"),
    ProductFreezeAnchor("P18", "query", "cross-conversation knowledge", "Conversation!=Knowledge"),
    ProductFreezeAnchor("P19", "clarification", "needs_clarification durable", "pending"),
    ProductFreezeAnchor("P20", "clarification", "reload pending clarification", "hydration"),
    ProductFreezeAnchor("P21", "clarification", "answer uses recovery path", "no full reinterp"),
    ProductFreezeAnchor("P22", "clarification", "duplicate answer 409", "one-shot"),
    ProductFreezeAnchor("P23", "clarification", "idempotent clarification answer", "replay"),
    ProductFreezeAnchor("P24", "abstain", "unsupported is completed", "not technical error"),
    ProductFreezeAnchor("P25", "abstain", "unsupported not clarification", "SAFE_ABSTAIN"),
    ProductFreezeAnchor("P26", "abstain", "unsupported persists reload", "durable"),
    ProductFreezeAnchor("P27", "idempotency", "same key same payload replay", "no Engine"),
    ProductFreezeAnchor("P28", "idempotency", "same key different payload 409", "fingerprint"),
    ProductFreezeAnchor("P29", "idempotency", "user-scoped keys", "cross-user ok"),
    ProductFreezeAnchor("P30", "idempotency", "completed after restart", "durable"),
    ProductFreezeAnchor("P31", "recovery", "stale with assistant recovers", "replay"),
    ProductFreezeAnchor("P32", "recovery", "stale ambiguous blocks Engine", "UNPROVEN=0"),
    ProductFreezeAnchor("P33", "recovery", "failed allows safe retry", "SAFE_ENGINE_RETRY"),
    ProductFreezeAnchor("P34", "recovery", "product db down 503", "fail closed"),
    ProductFreezeAnchor("P35", "recovery", "fresh in_progress retryable", "409"),
    ProductFreezeAnchor("P36", "durability", "empty conversation valid", "no synthetic knowledge"),
    ProductFreezeAnchor("P37", "durability", "explicit create conversation", "ownership"),
    ProductFreezeAnchor("P38", "durability", "implicit create via message", "ownership"),
    ProductFreezeAnchor("P39", "durability", "hydration includes messages", "GET detail"),
    ProductFreezeAnchor("P40", "durability", "list has preview", "sidebar"),
    ProductFreezeAnchor("P41", "isolation", "logout login resume", "same user"),
    ProductFreezeAnchor("P42", "isolation", "user B empty list", "no leak"),
    ProductFreezeAnchor("P43", "boundary", "schema product 1.4", "independent"),
    ProductFreezeAnchor("P44", "boundary", "knowledge schema v10", "frozen"),
    ProductFreezeAnchor("P45", "boundary", "CORE 65", "frozen"),
    ProductFreezeAnchor("P46", "boundary", "prompt v4", "frozen"),
    ProductFreezeAnchor("P47", "boundary", "no IR in public DTO modules", "boundary"),
    ProductFreezeAnchor("P48", "boundary", "web has no Engine IR tokens", "frontend"),
    ProductFreezeAnchor("P49", "correction", "correction outcome path available", "guard intact"),
    ProductFreezeAnchor("P50", "boundary", "health public", "no auth"),
]

assert [a.anchor_id for a in PRODUCT_FREEZE_ANCHORS] == [f"P{i:02d}" for i in range(1, 51)]
assert len(PRODUCT_FREEZE_ANCHORS) == 50
