# ADR 0053 — Interpreter Provider Retry & Pre-Commit Idempotency (I12.2)

## Status

Accepted — **INTERPRETER-RETRY-01 = CLOSED**.

No Knowledge Core change. No schema/migration. No CORE expansion.
No SemanticProposal / Wire redesign. No prompt semantic expansion (v4 unchanged).
Holdout untouched.

## Context

I12 froze:

```text
provider retry ≠ knowledge write retry
retry only before commit
MAX_ATTEMPTS = 2
```

I12.1 closed prompt hardening (v4). Remaining blocker: transient provider/transport
failures without duplicate knowledge.

Prior risk: `DeepSeekProvider` defaulted to `max_retries=2` (up to 3 HTTP tries).
Application-level retry without disabling SDK retry would multiply attempts.

## Decision

### Authority

```text
DeepSeekInterpreter.interpret
  → RetryPolicy (singular, bounded)
  → LlmProvider.generate_structured  (one HTTP try by default)
  → transport normalizer (existing proposal_normalizer / wire)
  → schema validation
  → accepted SemanticProposal / wire IR
  → frozen semantic pipeline
  → (only then) EngineGateway → Ingest/Ask commit
```

Retry does **not** live in repositories, materializer, CorrectionService, QueryEngine,
or Knowledge Core.

### Bounds

```text
application max attempts = 2
SDK / DeepSeekProvider default max_retries = 0
HTTP client retries = 0 (httpx single call)
effective maximum provider calls per logical request = 2
```

### Rate limit (429)

```text
RATE_LIMIT_POLICY = RETRY_ONCE_BOUNDED
```

One bounded delay (`PKE_INTERPRETER_RETRY_DELAY_SECONDS`, capped). No arbitrary
provider `Retry-After` blocking.

### Retryable

timeout, temporary network, HTTP 5xx, empty response, invalid JSON, schema-invalid
structured output, truncated, 429 (bounded once).

### Non-retryable

auth 401/403, configuration, permanent 4xx, valid semantic insufficiency /
contradiction / resolution miss, clarification, safe abstention, wrong-but-schema-valid
proposal (no semantic guess loop).

### Transport vs semantic repair

Allowed: fence strip, JSON envelope extract, known field-name drift (existing normalizer).

Forbidden: invent primitives, entities, times, measurement dimensions, correction IDs,
canonical concepts.

### Idempotency

One `interpreter_request_id` → at most one accepted proposal → at most one semantic
execution / commit. Failed attempt payloads are discarded (never merged).

### Config

| Env | Default | Role |
|-----|---------|------|
| `PKE_PROVIDER_TIMEOUT_SECONDS` | 30 | provider timeout |
| `PKE_PROVIDER_MAX_RETRIES` | 0 | SDK-layer retries |
| `PKE_INTERPRETER_MAX_ATTEMPTS` | 2 | interpreter attempts (capped ≤2) |
| `PKE_INTERPRETER_RETRY_DELAY_SECONDS` | 0.05 | bounded delay |

### API mapping

Exhausted transient failures → existing `PROVIDER_UNAVAILABLE` (presenter).
Auth/config are not presented as temporary unavailability.

## Artifacts

| Artifact | Path |
|----------|------|
| RetryPolicy | `src/pke/interpretation/retry.py` |
| Interpreter loop | `src/pke/interpretation/deepseek_interpreter.py` |
| SDK default retries=0 | `src/pke/llm/config.py` |
| Suite | `tests/interpreter_retry/` |

## Central answers

```text
CAN_TRANSIENT_PROVIDER_AND_TRANSPORT_FAILURES_NOW_RECOVER
WITHOUT_DUPLICATING_OR_MUTATING_KNOWLEDGE_UNSAFELY?
YES
```

```text
IS_INTERPRETER_RETRY_NOW_SAFE_ENOUGH_FOR_ENGINE_V1?
YES
```

```text
IS_LIVE_ENGINE_CHARACTERIZATION_NOW_THE_NEXT_CORRECT_ACTION?
YES
```

## Debt

```text
INTERPRETER-RETRY-01 = CLOSED
```

Still open (characterization): INTERPRETER-STATE-01, INTERPRETER-RELATION-01,
INTERPRETER-EVENT-01, ONTOLOGY-COVERAGE-01, SEMANTIC-QUERY-01.

## Freeze confirmation

```text
Knowledge Core v1 = FROZEN
schema = v10
CORE = 65
prompt semantic version = v4 (no semantic expansion)
SemanticProposal unchanged
Wire unchanged
holdout untouched
```

## Suite

```text
baseline I12.1: 2420 passed, 0 failed, 7 live deselected
I12.2:          2573 passed, 0 failed, 7 live deselected
retry catalog:  110 cases (+ behavioral tests → 153 in suite folder)
```

## Recommendation

```text
I12.2_CLOSE_PROCEED_TO_LIVE_ENGINE_CHARACTERIZATION
```
