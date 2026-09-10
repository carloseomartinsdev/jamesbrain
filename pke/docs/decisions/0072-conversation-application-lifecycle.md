# ADR 0072 — Conversation Application Lifecycle and Durable Interaction State

## Status

**Accepted** — P2 Product conversation lifecycle.

Extends ADR 0071 (identity/ownership). Does not reopen Engine or Knowledge Core.

## Context

P1 established server-authenticated identity and ownership. Conversations,
messages, clarifications, and retries still needed an explicit durable Product
lifecycle across reload, login cycles, and HTTP retries — without pretending
Product DB and Knowledge DB share one ACID transaction.

## Decision

### Authorities (`PRODUCT_LIFECYCLE_AUTHORITY_CONFLICT_COUNT = 0`)

| Authority | Owner |
|-----------|--------|
| `CONVERSATION_LIFECYCLE_AUTHORITY` | `ConversationOrchestrator` |
| `MESSAGE_LIFECYCLE_AUTHORITY` | `ConversationOrchestrator` + Product `messages` |
| `PENDING_CLARIFICATION_AUTHORITY` | `ConversationOrchestrator` + Product `clarifications` |
| `PRODUCT_OPERATION_AUTHORITY` | `ConversationOrchestrator` (presents Engine outcomes) |
| `PRODUCT_IDEMPOTENCY_AUTHORITY` | Product `idempotency` via orchestrator claims |
| `ENGINE_INVOCATION_AUTHORITY` | `ConversationOrchestrator` → `EngineGateway` only |

`EngineGateway` remains an adapter — not auth, not Product persistence, not UI.

### Conversation creation model

Canonical dual path (documented, not competing):

1. `POST /conversations` → empty durable conversation
2. `POST /messages` without `conversation_id` → create then send

Ownership always from `AuthUser.id`. New conversation does **not** create a
Knowledge namespace.

### Message timing

```text
authenticate + ownership
→ claim idempotency (if client_request_id)
→ persist USER message
→ EngineGateway
→ complete idempotency with Product response
→ persist ASSISTANT / pending clarification
```

`outcome=committed` only after Engine confirms Knowledge commit
(`FALSE_PRODUCT_COMMIT_ACK = 0`).

### Status vs outcome

| Product status | Typical outcome |
|----------------|-----------------|
| `completed` | `committed` / `answered` / `unsupported` / `failed` |
| `clarification_required` | `needs_clarification` |

Status is UI/application; outcome is Product operation result. Neither is a
Knowledge primitive.

### Clarification lifecycle

States used: `pending` → `answered` | `resolved`.

Only `pending` may invoke `ClarificationRecoveryService`.
Duplicate / stale answers → `409 CLARIFICATION_ANSWERED`
(`DUPLICATE_CLARIFICATION_RECOVERY = 0` at Product boundary).

Answer text is persisted as a USER conversation message (display), distinct
from Engine recovery payload.

### Idempotency (durable Product SQLite 1.3)

```text
PK (user_id, client_request_id)
+ request_fingerprint
+ status in_progress|completed|failed
+ response_json
```

- Same key + same fingerprint → replay (no Engine)
- Same key + different fingerprint → `409 IDEMPOTENCY_KEY_CONFLICT`
- Same key in progress → `409 IDEMPOTENCY_IN_PROGRESS`

Not memory-only. Survives process restart.

### Hydration

`GET /conversations/{id}` returns metadata + `messages` +
`pending_clarification` for reload without Engine replay
(`HISTORY_SEMANTIC_REPLAY_COUNT = 0`).

### Cross-store reality

```text
Product DB ≠ Knowledge DB
P2 does NOT claim distributed atomicity.
```

Partial failure after Engine success: idempotency record is completed first so
HTTP retry replays Product result without re-invoking Engine. Assistant-row
persistence is best-effort recovery on that path; residual orphans are
explicit, not hidden.

### Conversation title

Deterministic truncation of first user message. No LLM title call.

### Deletion / archive

Conversation deletion unsupported in P2. Optional `status=active` column
reserved; archive does not mutate Knowledge.

## Consequences

- Clients must handle `409` idempotency/clarification conflicts
- Web reloads from hydrated GET (not ephemeral JS)
- Further resilience (outbox/saga) is out of scope unless metrics prove need

## Non-goals

Engine/Core semantics, streaming, sharing, outbox/saga by default.
