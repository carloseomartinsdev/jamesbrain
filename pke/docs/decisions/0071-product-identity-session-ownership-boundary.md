# ADR 0071 — Product Identity, Session and Ownership Boundary

## Status

**Accepted** — P1 Product identity foundation.

Supersedes DEV_AUTH as the canonical Product identity mechanism (ADR 0070
noted DEV_AUTH as remaining debt). Extends ADR 0070; does not reopen Engine
or Knowledge Core.

## Context

WEB-01 closed with a real Product API and Web client, but identity was still
`DEV_AUTH`. Product resources (conversation, message, clarification,
idempotency) needed a server-authenticated owner before further application
lifecycle work.

Constraints:

```text
Knowledge Core v1 = FROZEN (schema v10, CORE 65)
Engine v1 = FROZEN
Product storage ≠ Knowledge storage
Conversation ≠ Knowledge ≠ Session
Product User ID ≠ world-model Entity ID
```

## Decision

### Authorities (no competitors)

| Authority | Implementation |
|-----------|----------------|
| `PRODUCT_IDENTITY_AUTHORITY` | `ProductAuthService` + Product `users` table |
| `PRODUCT_SESSION_AUTHORITY` | `ProductAuthService` + Product `sessions` (token **hash** only) |
| `PRODUCT_RESOURCE_OWNERSHIP_AUTHORITY` | `ConversationOrchestrator` + store queries scoped by `AuthUser.id` |
| `PRODUCT_IDEMPOTENCY_AUTHORITY` | Product `idempotency` PK `(user_id, client_request_id)` |
| `ENGINE_USER_IDENTITY_SOURCE` | `AuthUser.id` from server session/dev resolver only |

### Authentication mechanism (v1)

- First-party username/password registration + login
- Password hashing: PBKDF2-HMAC-SHA256 (`pke.product.passwords`)
- Session: opaque bearer token; server stores SHA-256 hash only
- Default TTL: 7 days (`PKE_SESSION_TTL_SECONDS`)
- Multiple concurrent sessions: **allowed**
- Logout: revokes current session by token hash
- Client storage: `sessionStorage` bearer (XSS tradeoff documented; not cookies)

### DEV_AUTH

```text
Canonical default: PKE_AUTH_MODE unset → session
Opt-in only: PKE_AUTH_MODE=dev
Invalid mode → fail closed (503)
No silent production fallback to DEV_AUTH
```

### Ownership policy

Cross-user access returns **404** (no existence leak). Rejection happens
before Engine invocation.

| Resource | Owner | Authorization path |
|----------|-------|--------------------|
| Session | Product user | bearer → token_hash → sessions.user_id |
| Conversation | Product user | conversations.user_id == AuthUser.id |
| Message | via conversation | messages → conversation → owner |
| Clarification | Product user + conversation | clarifications.user_id == AuthUser.id |
| client_request_id record | Product user | PK (user_id, client_request_id) |

### CORS / CSRF

- CORS: explicit origin allow-list; `allow_credentials=False`
- Auth via `Authorization: Bearer` (not cookies) → CSRF for cookie auth **N/A**
  (state-changing requests require the bearer secret; no ambient cookie credential)

### Isolation

- Product SQLite schema version **1.2** (independent of Knowledge **v10**)
- Product account rows live in Product DB; Knowledge `users` remains the
  Engine isolation key (same string id may be used as `UserContext.user_id`)
- No fake world-model `Entity(name="eu")` for accounts
- Login/logout are Product `auth_events`, not Knowledge Events

## Consequences

- Web must gate unauthenticated users and handle session expiry
- Tests must register/login; DEV_AUTH only in explicit `auth_mode=dev` fixtures
- Next Product work may assume real ownership + session identity

## Non-goals (unchanged)

SemanticProposal, ExecutionReadiness, CapabilityStrategy,
ClarificationRecoveryService semantics, Correction Guard, RetryPolicy,
ontology, schema v10, CORE 65, prompt v4, provider baseline.
