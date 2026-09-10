# Product v1 Freeze

**Status:** `PRODUCT_V1 = FROZEN`  
**Freeze decision:** P-R — Product v1 Final Revalidation & PKE v1 Completion Gate  
**Date:** 2026-09-04  
**ADR:** `docs/decisions/0075-product-v1-final-revalidation-and-pke-v1-completion.md`

---

## Versions

| Item | Value |
|------|-------|
| Product schema | **1.4** |
| Public API | **`/api/v1/`** |
| Knowledge Core | **v1 FROZEN** (schema **v10**, CORE **65**) |
| Engine | **v1 FROZEN** (prompt **v4**, provider **deepseek-chat**) |
| Holdout | **UNTOUCHED** |

---

## Freeze meaning

```text
PRODUCT_V1_FREEZE DOES NOT MEAN ALL FEATURES EXIST.
PRODUCT_V1_FREEZE DOES NOT MEAN FULL ONTOLOGY OR MODEL RECALL.
PRODUCT_V1_FREEZE MEANS THE DECLARED PRODUCT FLOWS ARE
STABLE, SAFE, TRUTHFUL, DURABLE AND USABLE
AGAINST THE FROZEN ENGINE/CORE BOUNDARY.
```

---

## Product v1 scope

Product v1 is **conversation-first**. It is **not** a Knowledge administration console.

Supported application surface:

```text
Authentication / logout
Durable sessions
Durable conversations and messages
Durable clarifications
Durable user-scoped idempotency
Durable recovery metadata
Conversation hydration
Responsive Web client
Public Product API /api/v1
```

---

## Supported flows

| Capability | Supported | Durable | Reload-safe | Ownership-safe | Truthful UX |
|---|---:|---:|---:|---:|---:|
| Authentication | YES | YES | YES | YES | YES |
| Logout | YES | YES | YES | YES | YES |
| New conversation | YES | YES | YES | YES | YES |
| Continue conversation | YES | YES | YES | YES | YES |
| Knowledge write | YES | YES | YES | YES | YES |
| Query | YES | YES | YES | YES | YES |
| Correction | YES | YES | YES | YES | YES |
| Clarification | YES | YES | YES | YES | YES |
| Safe abstain | YES | YES | YES | YES | YES |
| Technical retry | YES | YES | YES | YES | YES |
| Recovery-required | YES | YES | YES | YES | YES |
| Conversation history | YES | YES | YES | YES | YES |

---

## Public API boundary

- Clients speak only public DTOs under `/api/v1/`.
- Public API must not expose Engine IR (`SemanticProposal`, `IngestIR`, `QueryIR`, resolver internals).
- Web client is I/O and presentation only — not semantic authority.

---

## Identity boundary

- Server-authenticated identity is the only Engine user identity source.
- Client-supplied `user_id` is not authorization authority.
- Product User ID ≠ world-model Entity ID.
- `DEV_AUTH` remains opt-in development mode (`PKE_AUTH_MODE=dev`); not canonical production.

---

## Conversation boundary

```text
Session != Conversation
Conversation != Knowledge
Message != Knowledge assertion
message_id != assertion_id
message timestamp != fact time
```

- Conversation may outlive Session.
- New Conversation does not create a Knowledge namespace.
- Conversation history never reconstructs Knowledge.
- Cross-conversation Knowledge query uses shared user Knowledge.

---

## Durability model

Product SQLite store (schema 1.4) persists:

- users / sessions
- conversations / messages
- pending clarifications
- idempotency records `(user_id, client_request_id)` + fingerprint
- recovery metadata (`in_progress` | `completed` | `failed` | `recovery_required`)

Knowledge remains in the separate Knowledge Core store (schema v10).

---

## Idempotency model

```text
(user_id, client_request_id) + request fingerprint
```

- Completed operations replay durable Product result.
- Fingerprint mismatch → conflict (no silent bypass).
- Stale `in_progress` without proven completion → `recovery_required` (no blind Engine reexecution).

---

## Recovery model

`ProductRecoveryService` is **operational only**:

- uses Product durable metadata
- does not inspect raw text to infer semantics
- does not construct IR
- does not invoke Interpreter for history replay

`recovery_required` must not render as confirmed success or confirmed failure without evidence.

---

## UX truthfulness rules

| Product/Engine state | UX |
|---|---|
| committed | Acknowledgement only after confirmed commit |
| answered | Conversational answer |
| needs_clarification | Clarification (not technical error) |
| unsupported / SAFE_ABSTAIN | Distinct non-error limitation |
| failed retryable | Technical error + retry |
| recovery_required | Uncertainty note |

Unknown must never silently become false.

---

## Security / ownership boundary

Cross-user isolation for session, conversation, message, clarification, idempotency, and recovery.

Mandatory counters (all zero at freeze):

```text
CROSS_USER_CONVERSATION_READ / WRITE
CROSS_USER_CLARIFICATION_ANSWER
CROSS_USER_RECOVERY_ACCESS
CROSS_USER_UI_STATE_LEAK
CLIENT_SUPPLIED_USER_ID_TRUSTED
KNOWLEDGE_USER_ISOLATION_BREACH
DEV_AUTH_PRODUCTION_FALLBACK
```

---

## Explicit non-goals (POST_V1)

```text
native mobile / desktop clients
voice / camera / file upload
notifications / streaming / offline inference
knowledge graph UI / Knowledge CRUD console
advanced analytics
Measurement current_value / Measurement analytics
behavioral hypotheses
TYPE persistence / adaptive aliases
expanded ontology coverage / higher model recall
additional clarification families
conversation sharing / multi-user conversations
plugins
```

---

## Frozen invariants (Product-facing)

```text
LLM output is proposal, never truth.
Product client is not semantic authority.
Product API does not expose internal IR.
Authenticated server identity determines Engine user.
Account identity != world-model Entity.
Conversation != Knowledge.
Conversation != Session.
Message != Knowledge assertion.
Message time != fact time.
Conversation history never rebuilds Knowledge.
Product acknowledgement follows real commit evidence.
Retries are idempotent.
Recovery is operational, not semantic.
No distributed ACID guarantee is claimed.
Knowledge Core v1 remains frozen.
Engine v1 remains frozen.
```

---

## Evidence

- Deterministic suite: `tests/product_v1_freeze/` (≥300 cases; P01–P50 hand-audited)
- Full non-live regression: see `docs/reports/P-R-PRODUCT-V1-FINAL-REVALIDATION.md`
- Prior closed increments: WEB-01, P1, P2, P3, P4

---

## Reopen rule

Reopen Product v1 only with concrete evidence that a frozen invariant is violated — not because a new feature would be useful.
