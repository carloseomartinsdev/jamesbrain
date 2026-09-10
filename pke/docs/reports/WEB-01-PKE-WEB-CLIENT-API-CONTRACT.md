# WEB-01 — PKE Web Client & API Contract (Freeze Handoff)

## Executive

| Question | Answer |
|----------|--------|
| IS_WEB_CLIENT_NOW_DECOUPLED_FROM_PKE_INTERNAL_IR? | **YES** |
| IS_PKE_API_V1_NOW_A_STABLE_MULTIPLATFORM_BOUNDARY? | **YES** |
| CAN_WEB_SEND_AND_RECEIVE_REAL_PKE_INTERACTIONS? | **YES** |
| ARE_CLARIFICATION_AND_SAFE_ABSTAIN FIRST_CLASS_PRODUCT_OUTCOMES? | **YES** |
| IS_CONVERSATION_STORAGE SEPARATE_FROM_KNOWLEDGE_STORAGE? | **YES** |
| IS_CLIENT_RETRY_IDEMPOTENT? | **YES** |
| DID_KNOWLEDGE_CORE_V1_REMAIN_FROZEN? | **YES** |
| DID_ENGINE_V1_REMAIN_FROZEN? | **YES** |

```text
PRODUCT_ENGINE_AUTHORITY_CONFLICT_COUNT = 0
```

## Recommendation

```text
WEB_V1_SHELL_CLOSE_PROCEED_TO_PRODUCT_APPLICATION_INTEGRATION
```

---

## Canonical entry checkpoint (post I12-R)

```text
Knowledge Core v1 = FROZEN
Engine v1 = FROZEN
schema = v10
CORE = 65
prompt = v4
provider baseline = deepseek-chat
Engine tests = 4715 passed · 0 failed · 8 live deselected
holdout = UNTOUCHED
```

Freeze docs:

- `docs/ENGINE-V1-FREEZE.md`
- `docs/decisions/0069-engine-v1-final-revalidation-and-freeze.md`
- Handoff ADR: `docs/decisions/0070-pke-product-api-and-client-boundary.md`
- Prior boundary ADR: `docs/decisions/0052-multiplatform-api-web-client-boundary.md`

---

## Product baseline

| Item | Status |
|------|--------|
| Frontend stack | Vanilla JS modules + CSS (`web/`), conversation-first shell |
| Backend/API stack | FastAPI `pke.product.api.v1` + ConversationOrchestrator |
| Public API | `/api/v1/` |
| Conversation persistence | Product SQLite (`data/pke_product.db`, schema **1.1**) |
| Knowledge persistence | Separate Knowledge SQLite (schema **v10**) |
| Auth | **DEV_AUTH** (`Authorization: Bearer dev:<id>`), server-derived identity |
| Idempotency | `client_request_id` stored in product DB; retries return cached response |
| Real Engine integration | **YES** — `EngineGateway` → Interpreter → IngestService / AskService / ClarificationRecoveryService |
| Clarification UX | First-class (`type=clarification`, `status=clarification_required`, timeline card) |
| Safe abstention UX | Mapped to `type=unsupported` / `outcome=unsupported` (not error, not clarification) |
| Tests | `tests/api`, `tests/web`, `tests/product` (green in this audit) |

---

## Architecture

```text
Web Client
    ↓
Public API /api/v1
    ↓
Application / Conversation Orchestrator
    ↓
EngineGateway → Engine v1 (FROZEN)
    ↓
Knowledge Core v1 (FROZEN)
```

There is **no mock between API and Engine**. Tests use `FakeInterpreter` as a
deterministic Interpreter boundary (§45 allowed); production runtime uses
`DeepSeekInterpreter` when `DEEPSEEK_API_KEY` is present.

API does **not** manually construct internal IR to simulate the Engine.

---

## Public API routes (implemented)

| Method | Path |
|--------|------|
| GET | `/api/v1/health` |
| GET | `/api/v1/me` |
| GET | `/api/v1/conversations` |
| POST | `/api/v1/conversations` |
| GET | `/api/v1/conversations/{id}` |
| GET | `/api/v1/conversations/{id}/messages` |
| POST | `/api/v1/messages` |
| POST | `/api/v1/clarifications/{id}/answer` |

---

## Product outcome contract

### Operation kinds

```text
knowledge_write
knowledge_query
knowledge_correction
clarification
none
```

### Outcomes

```text
committed
answered
needs_clarification
unsupported
failed
```

### Engine → Product mapping

| Engine | Product |
|--------|---------|
| EXECUTE (committed write) | `acknowledgement` + `committed` |
| EXECUTE (query answered) | `answer` + `answered` |
| CLARIFY | `clarification` + `needs_clarification` / `clarification_required` |
| SAFE_ABSTAIN / unsupported semantics | `unsupported` + `unsupported` |
| Provider / transport failure | `error` + `failed` (e.g. HTTP 503) |

Product does not override these outcomes.

---

## Authority map

### Product owns

```text
authentication/session UX
conversation state
message persistence
public API DTO
request orchestration
presentation mapping
client idempotency contract
```

### Engine owns

```text
interpretation
semantic resolution
execution readiness
execute/clarify/abstain decision
clarification semantic recovery
query semantic orchestration
```

### Knowledge Core owns

```text
knowledge semantics
primitive semantics
temporal epistemics
correction semantics
persistence knowledge contracts
query truth foundations
```

```text
PRODUCT_ENGINE_AUTHORITY_CONFLICT_COUNT = 0
```

---

## Freeze boundaries respected

WEB-01 does **not** alter:

```text
SemanticProposal · ExecutionReadiness · CapabilityStrategy
ClarificationRecoveryService · Correction Acceptance Guard
RetryPolicy · Knowledge Core · schema · ontology · Wire · primitive semantics
```

Public API does **not** require clients to consume:

```text
SemanticProposal · IngestIR · QueryIR · KnowledgeCandidate · ResolutionResult
```

---

## Conversation boundary

```text
Conversation ≠ Knowledge ≠ Session
```

- New conversation creates conversational context only.
- Does not create a new Knowledge namespace.
- Knowledge remains user-scoped.
- Conversation timestamps are bookkeeping (`created_at` / message times), not fact time.

Storage: product DB tables `conversations`, `messages`, clarifications, idempotency —
**not** Knowledge Core tables.

---

## Clarification path

```text
User answer
  → Public API
  → Application layer
  → ClarificationRecoveryService
  → ExecutionReadiness / CapabilityStrategy / ingest
```

Not:

```text
original + answer → full Interpreter
```

---

## Commit-aware UX

- Optimistic UI uses `sending` / processing indicator before response.
- Copy containing “Registrei” / acknowledgement of persistence appears only when
  `operation.outcome = committed`.
- Unsupported / failed responses do not claim registration.

---

## Idempotency

- Client generates `client_request_id` per send.
- Server caches response by `(user_id, client_request_id)`.
- `message_id ≠ assertion_id`; `client_request_id ≠ message_id`;
  `conversation_id ≠ knowledge namespace`.

Status: **implemented** (not contract-only).

---

## UI shell

- Desktop: sidebar + central conversation
- Mobile: drawer + full-screen conversation + sticky composer
- Routes: `/`, `/c/{conversation_id}`, `/settings`
- Types rendered: user / assistant / clarification / unsupported / error
- Enter = send; Shift+Enter = newline; double-submit guarded + idempotency

Streaming: not required for WEB-01 (out of scope).

---

## Tests covered

API / Product:

- public DTO validation (extra fields rejected)
- message send + conversation continuation
- Engine outcome mapping (committed / answered / clarification / unsupported / error)
- clarification answer + ownership isolation
- wrong-user access
- idempotent repeated request
- provider failure → 503 / no false commit claim
- product schema isolated from Core

Web:

- shell / composer / assets
- clarification card hooks
- client_request_id in API client
- fetch confined to `api/client.js`
- Enter / Shift+Enter / retry hooks

---

## Gaps / next Product work (non-blockers for shell close)

- Production auth beyond DEV_AUTH
- Richer clarification option UX for all Engine slots
- Explicit Product labeling for “safe abstain” copy variants (currently under `unsupported`)
- Deeper Product application polish (settings, observability dashboards — still not required)

These do **not** reopen Core or Engine.

---

## Stop tokens

None triggered:

```text
WEB_API_REQUIRES_CORE_REOPEN — no
WEB_API_REQUIRES_ENGINE_REOPEN — no
WEB_API_INTERNAL_IR_LEAK — no
WEB_CLIENT_SEMANTIC_AUTHORITY_VIOLATION — no
```

---

## Final confirmation

```text
Knowledge Core v1 remains FROZEN.

Engine v1 remains FROZEN.

Product does not reinterpret semantic outcomes.

Product does not construct internal semantic IR manually.

Public API remains independent of internal Engine DTOs.

Conversation remains distinct from Knowledge.

Message timestamps remain bookkeeping,
not semantic fact time.

Clarification is a first-class Product outcome.

SAFE_ABSTAIN is a first-class Product outcome.

Successful knowledge-write acknowledgement
is emitted only after confirmed commit.

Client retry does not intentionally duplicate
Engine operations.

Future Web, PWA, Mobile and Desktop clients
can share the same Product API boundary.

No Product client is a semantic authority.
```
