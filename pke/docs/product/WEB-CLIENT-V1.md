# WEB-CLIENT-V1 — Product shell over PKE API v1

## Client / server

```text
Web / future clients
        ↓
   PKE API v1
        ↓
Conversation Orchestrator
        ↓
PKE Engine (Ask / Ingest)
        ↓
Knowledge Core v1 (FROZEN)
        ↓
Knowledge persistence (schema v10)
```

The web client is an I/O surface. It collects text, displays responses, manages
conversation UX, and never decides Event / State / Relation / Attribute /
Measurement / correction / entity / time / materialization.

## Conversation ≠ Knowledge ≠ Session

| Concept | Lives in | Lost when |
|---------|----------|-----------|
| Conversation | product DB (`pke_product.db`) | conversation is discarded (not in v1) |
| Knowledge | Knowledge Core schema v10 | never discarded because a chat closed |
| Session (auth) | `DEV_AUTH` today; server auth later | expiry does not erase knowledge |

Closing the browser does not delete knowledge. A new conversation is not a new
user. Deleting a chat (future) must not delete knowledge.

## Public response types

`answer` · `acknowledgement` · `clarification` · `unsupported` · `error`

Clarification is a normal interaction state, not an error.

`operation.kind` / `operation.outcome` tell the UI whether knowledge was
committed. The UI must not say “registrei” unless `outcome=committed`.

## Clarification flow

Engine needs clarification → API `type=clarification` → UI card →
`POST /api/v1/clarifications/{id}/answer` → orchestrator resumes with
original text + answer → Engine runs again → public response.

The frontend never invents clarification options.

## Ownership

`conversation_id`, `message_id`, and `clarification_id` are untrusted until the
server checks they belong to the authenticated user. Cross-user access returns
404. `user_id` is never taken from the JSON body.

## Idempotency

`client_request_id` is part of the public contract. The product store replays
the first response for the same user + id.

## Future clients

Windows, macOS, Android, iOS, PWA, CLI, and voice should consume **only**
`/api/v1/`. Internal Engine IR (`SemanticProposal`, `IngestIR`, `QueryIR`, …)
is not a client contract.

## Core freeze boundary

Knowledge Core v1 remains FROZEN. Schema remains v10. CORE remains 65.
Conversation/message/clarification tables live in a **separate SQLite file**
with product schema version 1. No Core migration is required for WEB-01.
