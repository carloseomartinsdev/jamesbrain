# ADR 0073 — Product Resilience and Cross-Store Recovery Boundary

## Status

**Accepted** — P3 Product resilience foundation.

Extends ADR 0072. Does not reopen Engine or Knowledge Core.

## Context

P2 established durable conversations, messages, clarifications, and idempotency
with fingerprints. Cross-store crashes leave an ambiguous window:

```text
idempotency = in_progress
Engine may or may not have committed
Product result may be missing
```

Blind Engine re-execution in that window is unsafe.

## Decision

### Authorities

| Authority | Owner |
|-----------|--------|
| `NORMAL_INTERACTION_AUTHORITY` | `ConversationOrchestrator` |
| `RECOVERY_AUTHORITY` | `ProductRecoveryService` |
| `IDEMPOTENCY_AUTHORITY` | ProductStore idempotency + recovery |
| `PRODUCT_PERSISTENCE_AUTHORITY` | ProductStore |
| `ENGINE_INVOCATION_AUTHORITY` | ConversationOrchestrator → EngineGateway |
| `CLARIFICATION_OPERATION_AUTHORITY` | ConversationOrchestrator (recovery never bypasses pending check) |

```text
PRODUCT_RESILIENCE_AUTHORITY_CONFLICT_COUNT = 0
NO DISTRIBUTED ACID CLAIM
```

### Idempotency statuses (Product schema 1.4)

```text
in_progress          — durable guard taken; Engine may still be running
completed            — durable Product result exists → always replay
failed               — fail_idempotent before complete → SAFE_ENGINE_RETRY
recovery_required    — stale/ambiguous completion → no Engine retry
```

### Stale `in_progress` (lazy reconciliation)

Detected when `updated_at` age ≥ `PKE_IDEMPOTENCY_STALE_SECONDS` (default 120).

On stale same-fingerprint retry:

1. If `response_json` exists → complete + **REPLAY_PRODUCT_RESULT**
2. Else if assistant Product message exists for `client_request_id` → reconstruct
   public response from that message + complete + **REPLAY**
3. Else → mark `recovery_required` + **MARK_REQUIRES_RECONCILIATION**
   (`OPERATION_RECOVERY_REQUIRED`, `retryable=false`)

Never:

```text
UNPROVEN_ENGINE_REEXECUTION
```

No startup worker; lazy reconciliation on request is sufficient for v1.

### Product DB unavailable

`ping()` before establishing the durable guard. Fail closed (`503 PRODUCT_UNAVAILABLE`).

```text
ENGINE_INVOKED_WITHOUT_DURABLE_PRODUCT_GUARD = 0
```

### Clarification

Terminal clarification still yields `409 CLARIFICATION_ANSWERED`.
Stale/idempotent answer paths never double-call `ClarificationRecoveryService`.

### Manual reconciliation

Scenario: `recovery_required` with no durable Product result after possible Engine commit.

Operator may:

- inspect Product `idempotency` + `messages` for the `(user_id, client_request_id)`
- inspect Knowledge for that Product user id if needed for support
- **must not** invent a semantic Product result or force Engine re-run

User-facing copy does not expose cross-store jargon.

### Non-goals

No outbox/saga, no background worker, no provider retry layer at Product,
no Engine/Core changes.

## Consequences

- Clients must handle `OPERATION_RECOVERY_REQUIRED` without blind resubmit
- Fresh `IDEMPOTENCY_IN_PROGRESS` remains `retryable=true`
- Residual ambiguous cases are explicit, not silent false failures
