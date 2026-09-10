# P1 — Product Identity, Session & Ownership Foundation

## Status

**CLOSED**

## Phase

```text
PRODUCT V1 / APPLICATION LAYER
```

## Entry state

```text
Knowledge Core v1 = FROZEN
Engine v1 = FROZEN
schema = v10
CORE = 65
prompt = v4
WEB-01 = CLOSED
Public API = /api/v1/
Product storage = SQLite (now 1.2)
Knowledge storage = schema v10
Prior auth = DEV_AUTH (canonical debt)
```

## Central answers

```text
DOES_PRODUCT_V1_HAVE_A_REAL
SERVER-AUTHENTICATED_USER_IDENTITY?
YES

CAN_ONE_USER_ACCESS_OR_MUTATE
ANOTHER_USER'S PRODUCT RESOURCES?
NO

IS_THE_IDENTITY_PASSED_TO_ENGINE
DERIVED_EXCLUSIVELY_FROM
SERVER_AUTHENTICATED_CONTEXT?
YES
```

## What shipped

### Identity & session

- Product `users` + `sessions` + `auth_events` in Product SQLite **1.2**
- `ProductAuthService`: register / login / logout / bearer resolve
- Password: PBKDF2-HMAC-SHA256 (never plaintext; never returned)
- Session token: opaque bearer; store SHA-256 hash only; TTL default 7d
- Multiple concurrent sessions: allowed
- Default auth mode: `session`; `PKE_AUTH_MODE=dev` opt-in only; invalid → 503

### API

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/me
```

Protected conversation/message/clarification routes resolve `AuthUser` server-side.
Body/query `user_id` is not an authorization authority (`extra=forbid` on message DTOs).

### Ownership

| Resource | Owner | Authorization path |
|---|---|---|
| Session | Product user | bearer → token_hash → sessions.user_id |
| Conversation | Product user | conversations.user_id == AuthUser.id |
| Message | via conversation | message → conversation → owner |
| Clarification | Product user + conversation | clarifications.user_id == AuthUser.id |
| client_request_id record | Product user | PK (user_id, client_request_id) |

Ownership failures → **404**. Engine is not invoked.

### Web

- Auth gate (login/register)
- States: unauthenticated / authenticating / authenticated / session expired
- Bearer in `sessionStorage`; composer draft preserved on session expiry
- Logout control in sidebar

### Authorities

```text
PRODUCT_IDENTITY_AUTHORITY = ProductAuthService + Product users
PRODUCT_SESSION_AUTHORITY = ProductAuthService + Product sessions
PRODUCT_RESOURCE_OWNERSHIP_AUTHORITY = ConversationOrchestrator + scoped store
PRODUCT_IDEMPOTENCY_AUTHORITY = (user_id, client_request_id)
ENGINE_USER_IDENTITY_SOURCE = AuthUser.id from ProductAuthResolver
```

## Security counters

```text
PLAINTEXT_PASSWORD_STORED = 0
PASSWORD_HASH_EXPOSED = 0
RAW_SESSION_TOKEN_LOGGED = 0
CLIENT_SUPPLIED_USER_ID_TRUSTED = 0
CROSS_USER_CONVERSATION_READ = 0
CROSS_USER_CONVERSATION_WRITE = 0
CROSS_USER_MESSAGE_READ = 0
CROSS_USER_CLARIFICATION_ANSWER = 0
CROSS_USER_CLIENT_REQUEST_COLLISION = 0
UNAUTHORIZED_ENGINE_INVOCATION = 0
DEV_AUTH_PRODUCTION_FALLBACK = 0
KNOWLEDGE_USER_ISOLATION_BREACH = 0
```

## CORS / CSRF / token storage

```text
CORS policy = explicit allow-list origins; allow_credentials=False
CSRF policy = N/A for cookie CSRF (Bearer Authorization; no ambient cookie session)
Token storage = sessionStorage (tab-scoped); XSS can steal token — mitigate via CSP/hygiene; no long-lived localStorage secret
```

## Schema versions

```text
Product schema version = 1.2
Knowledge schema version = 10
```

Physically separate SQLite files; separate migration authorities.

## Executive

```text
IS_PRODUCT_IDENTITY_FOUNDATION_COMPLETE? YES
IS_DEV_AUTH_REMOVED_FROM_CANONICAL_PRODUCT_PATH? YES
IS_SERVER_AUTHENTICATED_IDENTITY
THE_ONLY_ENGINE_USER_IDENTITY_SOURCE? YES
CAN_ONE_USER_READ_ANOTHER_USER'S_CONVERSATION? NO
CAN_ONE_USER_WRITE_TO_ANOTHER_USER'S_CONVERSATION? NO
CAN_ONE_USER_ANSWER_ANOTHER_USER'S_CLARIFICATION? NO
IS_CLIENT_REQUEST_ID_SAFE_ACROSS_USERS? YES
IS_PRODUCT_STORAGE_STILL_SEPARATE
FROM_KNOWLEDGE_STORAGE? YES
DID_KNOWLEDGE_CORE_V1_REMAIN_FROZEN? YES
DID_ENGINE_V1_REMAIN_FROZEN? YES
```

## Baseline

```text
Product schema version = 1.2
Auth mechanism = first-party username/password + session bearer
Session mechanism = opaque bearer; hashed at rest; TTL; multi-session OK
Credential hashing = PBKDF2-HMAC-SHA256
DEV_AUTH status = opt-in PKE_AUTH_MODE=dev only; not canonical
CORS policy = explicit origins; credentials false
CSRF policy = N/A (Bearer, not cookies)
Product/API tests = 24 passed
Web tests = 12 passed
Security tests = 8 passed (test_p1_identity_ownership.py)
Product boundary = 1 passed
Product suite total = 37 passed
Full non-live regression = 4727 passed, 0 failed, 8 live deselected
```

## ADR

`docs/decisions/0071-product-identity-session-ownership-boundary.md`

## Recommendation

```text
P1_CLOSE_PROCEED_TO_CONVERSATION_APPLICATION_LIFECYCLE
```

## Confirmation

```text
Knowledge Core v1 remains FROZEN.

Engine v1 remains FROZEN.

Product identity is distinct from world-model Entity identity.

Server-authenticated identity is the only
source of Engine user identity.

Client-supplied user_id is not an authorization authority.

Session is distinct from Conversation.

Conversation is distinct from Knowledge.

Product resources enforce user ownership.

Clarification ownership is enforced before
ClarificationRecoveryService invocation.

Idempotency is isolated across users.

Unauthorized Product requests never invoke Engine.

Product storage remains separate from
Knowledge storage.

DEV_AUTH is not part of the canonical
production Product path.

No Product component became a semantic authority.
```
