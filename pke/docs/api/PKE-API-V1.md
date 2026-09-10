# PKE API v1

Canonical multiplatform boundary. Versioned under `/api/v1/`.

Identity is resolved by the server (`DEV_AUTH` in development). The body must
never carry authoritative `user_id`.

Public DTOs live in `pke.product.api.v1.dtos`. They are not Engine IR.

## `GET /api/v1/health`

Operational liveness only.

**200**

```json
{ "status": "ok" }
```

No secrets. No auth required.

## `GET /api/v1/me`

**Headers:** `Authorization: Bearer dev:<user_id>` (DEV_AUTH)

**200**

```json
{ "id": "u1", "display_name": "u1", "auth_mode": "dev" }
```

**401** invalid bearer.

## `GET /api/v1/conversations`

List of `ApiConversationSummary` for the authenticated user, newest first.

**200** array of `{ id, title, created_at, updated_at }`

Timestamps are conversation bookkeeping, not fact time.

## `POST /api/v1/conversations`

**201** `{ id, title, created_at, updated_at }`

Creates a new conversational context. Does not create a knowledge namespace.

## `GET /api/v1/conversations/{conversation_id}`

**200** conversation metadata.

**404** missing or not owned.

## `GET /api/v1/conversations/{conversation_id}/messages`

**200** array of `ApiMessage`.

**404** missing or not owned.

## `POST /api/v1/messages`

Central turn endpoint.

**Request**

```json
{
  "conversation_id": "conv_…",
  "text": "Troquei a embreagem do Corolla.",
  "client_request_id": "uuid"
}
```

`conversation_id` optional — API creates a conversation when absent.

**200** `ApiMessageResponse`

```json
{
  "conversation_id": "conv_…",
  "message_id": "msg_…",
  "type": "acknowledgement",
  "status": "completed",
  "text": "Certo. Registrei essa informação.",
  "operation": { "kind": "knowledge_write", "outcome": "committed" }
}
```

`type`: `answer` | `acknowledgement` | `clarification` | `unsupported` | `error`

`status`: `completed` | `clarification_required` | `failed`

**HTTP**

| Situation | Status |
|-----------|--------|
| Successful turn, including unsupported / clarification | 200 |
| Invalid payload | 422 |
| Unauthenticated | 401 |
| Conversation not owned | 404 |
| Provider unavailable | 503 |
| Unexpected server error | 500 |

Unsupported is **not** 500.

## `POST /api/v1/clarifications/{clarification_id}/answer`

**Request**

```json
{
  "text": "Corolla",
  "option_id": "…",
  "client_request_id": "uuid"
}
```

**200** same envelope as `POST /messages`.

**404** unknown or not owned.

**409** already answered.

**422** neither text nor option.

Ownership: only the user who received the clarification may answer it.

## Error envelope

```json
{
  "type": "error",
  "status": "failed",
  "error": {
    "code": "PROVIDER_UNAVAILABLE",
    "message": "Não foi possível processar sua solicitação agora."
  }
}
```

No stack traces.

## Streaming

Not in v1. The JSON envelope can later be emitted over SSE / WebSocket without
changing the semantic contract.
