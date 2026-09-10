# ADR 0052 — Multiplatform API & Web Client boundary

## Status

Accepted.

## Context

Knowledge Core v1 is frozen (ADR 0050). Schema v10. CORE = 65. Product/API UX
was explicitly out of the freeze.

James (and every future surface) needs a stable way to talk to PKE without
depending on Engine internals.

## Decision

All clients are I/O surfaces over a canonical PKE server API.

```text
Web · Windows · macOS · Android · iOS · PWA · CLI · voice
        ↓
     PKE API v1
        ↓
Conversation Orchestrator (application)
        ↓
PKE Engine
        ↓
Knowledge Core (frozen)
        ↓
Persistence
```

Knowledge semantics remain server-side.

Public API contracts (`ApiMessageRequest`, `ApiMessageResponse`, …) are
distinct from internal Engine IR (`SemanticProposal`, `WireSemanticEnvelope`,
`IngestIR`, `QueryIR`, `ResolutionResult`, `KnowledgeCandidate`,
`KnowledgeReference`, `Correction`, `TemporalKnowledge`).

Conversation bookkeeping is stored in a **product** SQLite database, isolated
from Knowledge Core schema v10. No Core migration.

Authentication identity is derived on the server. Development uses an explicit
`DEV_AUTH` adapter (`Authorization: Bearer dev:<id>`). The JSON body is never
the authority for `user_id`.

## Consequences

- Frontend may collect input, display output, manage conversation UX, and
  answer clarifications rendered by the API.
- Frontend must not decide primitives, resolve entities, or fabricate
  acknowledgement copy.
- Future clients should not bypass `/api/v1/`.
- Closing a conversation must not erase knowledge.

## Not in this increment

Streaming, voice, attachments, production auth, knowledge graph, ontology
admin, destructive conversation delete.
