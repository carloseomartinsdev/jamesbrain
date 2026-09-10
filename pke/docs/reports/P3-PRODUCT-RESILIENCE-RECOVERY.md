# P3 — Product Resilience, Recovery & Operational Consistency

## Status

**CLOSED**

## Central question

```text
CAN_PRODUCT_V1_RECOVER_FROM
PROCESS, NETWORK AND CROSS-STORE
PARTIAL FAILURES WITHOUT
DUPLICATING OR FALSIFYING
SEMANTIC OUTCOMES?
YES
```

## Declaration

```text
NO DISTRIBUTED ACID CLAIM
```

## Authorities

```text
NORMAL_INTERACTION_AUTHORITY = ConversationOrchestrator
RECOVERY_AUTHORITY = ProductRecoveryService
IDEMPOTENCY_AUTHORITY = ProductStore + ProductRecoveryService
PRODUCT_PERSISTENCE_AUTHORITY = ProductStore
ENGINE_INVOCATION_AUTHORITY = ConversationOrchestrator → EngineGateway
CLARIFICATION_OPERATION_AUTHORITY = ConversationOrchestrator
PRODUCT_RESILIENCE_AUTHORITY_CONFLICT_COUNT = 0
```

## Recovery model

```text
Lazy reconciliation on request (no background worker)
Stale in_progress when updated_at age ≥ PKE_IDEMPOTENCY_STALE_SECONDS (default 120)

completed → REPLAY_PRODUCT_RESULT
failed → SAFE_ENGINE_RETRY
stale in_progress + assistant/result evidence → REPLAY
stale in_progress + no evidence → recovery_required (no Engine)
fresh in_progress → IDEMPOTENCY_IN_PROGRESS (retryable)
fingerprint mismatch → CONFLICT
```

## Recovery matrix (R1–R14)

| ID | Case | Engine on retry? | Knowledge dup? | Behavior | Safe? |
|---|---|---|---|---|---|
| R1 | Crash before durable guard | No | No | New claim | Yes |
| R2 | Crash after guard / before Engine | No (stale→recovery_required if no evidence) | No | Explicit | Yes |
| R3 | Engine/provider fail before commit | No commit ack | No | failed → safe retry | Yes |
| R4 | Engine + Product success | Replay | No | completed | Yes |
| R5 | Engine OK + Product assistant fail | Replay if idempotency completed | No | contained | Yes |
| R6 | Lost HTTP | Replay | No | completed | Yes |
| R7 | Completed after restart | No | No | Replay | Yes |
| R8 | Stale in_progress | Only if Product evidence | No | recover or recovery_required | Yes |
| R9 | Same key different FP | No | No | 409 conflict | Yes |
| R10 | Clarification crash/retry | No second recovery | No | 409 / replay | Yes |
| R11 | Stale clarification old tab | No | No | 409 ANSWERED | Yes |
| R12 | Product DB unavailable | No | No | 503 fail closed | Yes |
| R13 | Engine/Knowledge unavailable | No commit | No | technical failure | Yes |
| R14 | Cross-user recovery | No | No | 404 ownership | Yes |

## Manual reconciliation

```text
Scenario: recovery_required without durable Product result after possible Engine commit
Why automatic unsafe: cannot prove Engine non-commit
Operator: inspect idempotency + messages (+ Knowledge support if needed)
Operator must not invent semantic Product outcomes or force Engine re-run
```

## Safety counters

```text
DUPLICATE_ENGINE_INVOCATION_AFTER_RESTART = 0
DUPLICATE_KNOWLEDGE_COMMIT_AFTER_RESTART = 0
COMPLETED_OPERATION_ENGINE_REEXECUTION = 0
UNPROVEN_ENGINE_REEXECUTION = 0
RECOVERY_FALSE_COMMIT_ACK = 0
IDEMPOTENCY_FINGERPRINT_BYPASS = 0
CRASH_DUPLICATE_CLARIFICATION_RECOVERY = 0
CROSS_USER_RECOVERY_ACCESS = 0
ENGINE_INVOKED_WITHOUT_DURABLE_PRODUCT_GUARD = 0
PRODUCT_PROVIDER_RETRY_LOOP = 0
RECOVERY_RAW_TEXT_SEMANTIC_INFERENCE = 0
HISTORY_SEMANTIC_REPLAY_COUNT = 0
PERMANENT_STUCK_IN_PROGRESS_OPERATIONS = 0 (after stale path)
```

## Executive

```text
IS_PRODUCT_RESILIENCE_AND_RECOVERY_COMPLETE? YES
CAN_COMPLETED_OPERATIONS_SURVIVE_PROCESS_RESTART? YES
CAN_RETRY_AFTER_RESTART_DUPLICATE_A_KNOWLEDGE_MUTATION? NO
CAN_A_STALE_IN_PROGRESS_OPERATION_CAUSE_UNPROVEN_ENGINE_REEXECUTION? NO
CAN_PRODUCT_ACKNOWLEDGE_COMMIT_WITHOUT_RELIABLE_COMMIT_EVIDENCE? NO
CAN_CLARIFICATION_RECOVERY_BE_APPLIED_TWICE_AFTER_CRASH/RETRY? NO
CAN_PRODUCT_OPERATE_SAFELY_WHEN_PRODUCT_DB_IS_UNAVAILABLE? YES
ARE_CROSS_STORE_PARTIAL_FAILURES_RECOVERABLE_OR_EXPLICITLY_CONTAINED? YES
IS_PRODUCT_RECOVERY_NON_SEMANTIC? YES
DID_KNOWLEDGE_CORE_V1_REMAIN_FROZEN? YES
DID_ENGINE_V1_REMAIN_FROZEN? YES
```

## Baseline

```text
Product schema version = 1.4
Recovery model = ProductRecoveryService lazy reconcile
Stale operation strategy = age(updated_at) + evidence-based replay or recovery_required
Startup/lazy reconciliation = lazy only
Manual reconciliation cases = recovery_required ambiguity (documented)
Product/API tests = 44 passed
Web tests = 14 passed
Resilience/failure tests = 9 passed
Product suite total = 59 passed
Full non-live regression = 4749 passed, 0 failed, 8 live deselected
```

## ADR

`docs/decisions/0073-product-resilience-cross-store-recovery.md`

## Recommendation

```text
P3_CLOSE_PROCEED_TO_PRODUCT_UX_COMPLETION
```
