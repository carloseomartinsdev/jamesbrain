# P2 — Conversation Application Lifecycle & Durable Interaction State

## Status

**CLOSED**

## Central question

```text
CAN_A_PRODUCT_CONVERSATION
BE_DURABLY_CREATED, CONTINUED,
INTERRUPTED FOR CLARIFICATION,
RELOADED AND RESUMED
WITHOUT LOSING OR DUPLICATING
THE ENGINE INTERACTION STATE?
YES
```

## Authorities

```text
CONVERSATION_LIFECYCLE_AUTHORITY = ConversationOrchestrator
MESSAGE_LIFECYCLE_AUTHORITY = ConversationOrchestrator + Product messages
PENDING_CLARIFICATION_AUTHORITY = ConversationOrchestrator + clarifications
PRODUCT_OPERATION_AUTHORITY = ConversationOrchestrator
PRODUCT_IDEMPOTENCY_AUTHORITY = Product idempotency (user_id, client_request_id) + fingerprint
ENGINE_INVOCATION_AUTHORITY = ConversationOrchestrator → EngineGateway
PRODUCT_LIFECYCLE_AUTHORITY_CONFLICT_COUNT = 0
```

## Lifecycle examples

### A. knowledge write success

```text
Product: claim → USER msg → Engine write commit → complete idempotency → ASSISTANT ack
Knowledge: mutated once
Retry same key: Product replay, Engine=0
```

### B. query success

```text
Product: USER + ASSISTANT answer durable; outcome=answered
Knowledge: read only
Reload: GET hydration shows answer; no Interpreter replay
```

### C. safe abstention

```text
Product: USER + ASSISTANT unsupported durable
Knowledge: no write
Reload: unsupported remains
```

### D. clarification → reload → answer → success

```text
needs_clarification persisted (clarifications.status=pending)
GET conversation → pending_clarification visible
answer → ClarificationRecoveryService (not full reinterpret)
status → resolved/answered; duplicate → 409
```

### E. HTTP response lost → retry

```text
idempotency COMPLETED with response_json
retry → REPLAY; Engine not invoked; Knowledge not duplicated
```

### F. Engine failure before commit

```text
USER message may remain; ASSISTANT failed/unsupported
outcome ≠ committed; Knowledge not falsely acknowledged
```

### G. Product persistence failure after Engine success

```text
idempotency completed before assistant-row write
retry → Product result replay (no Engine)
assistant row may be missing until repair (orphan explicit)
NO distributed ACID claim
```

## Failure matrix (summary)

| Case | Engine? | Knowledge? | Product? | Retry | Safe? |
|---|---|---|---|---|---|
| Persist fail before Engine | No | No | claim fail / release | reclaim | Yes |
| Engine fail before commit | Yes | No commit | USER + failed/unsupported | new key | Yes |
| Engine OK + Product result fail | Yes once | Maybe committed | idempotency completed | replay | Yes* |
| HTTP lost after Product OK | No on retry | No dup | replay | Yes |
| Dup HTTP same payload | No on 2nd | No dup | replay | Yes |
| Same key different payload | No | No | 409 conflict | Yes |
| Dup clarification answer | No 2nd recovery | No 2nd | 409 | Yes |
| Stale clarification | No | No | 409 | Yes |
| Reload pending clar | No | No | GET hydration | Yes |
| Logout/login pending | No | No | durable Product | Yes |
| Cross-user | No | No | 404 | Yes |

\*Assistant-row orphan possible; result recoverable via idempotency replay.

## Safety counters

```text
FALSE_PRODUCT_COMMIT_ACK = 0
DUPLICATE_ENGINE_INVOCATION_FROM_RETRY = 0
DUPLICATE_KNOWLEDGE_COMMIT_FROM_PRODUCT_RETRY = 0
DUPLICATE_CLARIFICATION_RECOVERY = 0
IDEMPOTENCY_KEY_PAYLOAD_CONFUSION = 0
OPTIMISTIC_MESSAGE_DUPLICATION = 0
HISTORY_SEMANTIC_REPLAY_COUNT = 0
CROSS_USER_CONVERSATION_LIFECYCLE_BREACH = 0
CROSS_USER_CLARIFICATION_LIFECYCLE_BREACH = 0
PRODUCT_TIMESTAMP_USED_AS_FACT_TIME = 0
```

## Consistency counters (explicit)

```text
ORPHAN_USER_MESSAGE_COUNT = possible on Engine fail (expected)
ORPHAN_PKE_RESPONSE_COUNT = possible if assistant persist fails after idempotency complete
STUCK_PENDING_CLARIFICATION_COUNT = 0 under normal answer path
COMPLETED_ENGINE_OPERATION_WITHOUT_PRODUCT_RESULT_COUNT = mitigated by completing idempotency before assistant persist
```

Recovery: automatic idempotent HTTP retry for completed keys; no outbox/saga in P2.

## Cross-store

```text
P2 does not pretend Product DB and Knowledge DB share one atomic transaction.
```

## Executive

```text
IS_CONVERSATION_APPLICATION_LIFECYCLE_COMPLETE? YES
CAN_CONVERSATIONS_SURVIVE_RELOAD_AND_LOGIN_CYCLES? YES
CAN_PENDING_CLARIFICATIONS_SURVIVE_RELOAD? YES
CAN_PENDING_CLARIFICATIONS_BE_RESUMED_WITHOUT_FULL_REINTERPRETATION? YES
IS_PRODUCT_CONVERSATION_HISTORY_DURABLE_AND_SEPARATE_FROM_KNOWLEDGE? YES
CAN_HTTP_RETRY_DUPLICATE_A_KNOWLEDGE_WRITE? NO
CAN_DUPLICATE_CLARIFICATION_SUBMISSION_REAPPLY_SEMANTIC_RECOVERY? NO
CAN_PRODUCT_REPORT_COMMITTED_BEFORE_ENGINE_COMMIT? NO
IS_CROSS_STORE_PARTIAL_FAILURE_EXPLICITLY_HANDLED? YES
DID_KNOWLEDGE_CORE_V1_REMAIN_FROZEN? YES
DID_ENGINE_V1_REMAIN_FROZEN? YES
```

## Baseline

```text
Product schema version = 1.3
Conversation persistence = Product SQLite conversations (status active)
Message persistence = Product messages (ORDER BY created_at, id)
Clarification persistence = Product clarifications (pending|answered|resolved)
Idempotency persistence = durable SQLite + fingerprint + in_progress|completed|failed
Conversation creation model = POST /conversations OR POST /messages without id
Product/API tests = 35 passed
Web tests = 13 passed
Lifecycle/failure tests = 11 passed
Product suite total = 49 passed
Full non-live regression = 4739 passed, 0 failed, 8 live deselected
```

## ADR

`docs/decisions/0072-conversation-application-lifecycle.md`

## Recommendation

```text
P2_CLOSE_PROCEED_TO_PRODUCT_RESILIENCE_AND_RECOVERY
```

Residual: explicit orphan repair / operator tooling for rare Product assistant-row gaps after Engine success remains Product resilience work — not Engine/Core.
