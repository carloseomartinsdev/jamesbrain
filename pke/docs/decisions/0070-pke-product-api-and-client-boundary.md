# ADR 0070 — PKE Product API and Client Boundary (Engine v1 freeze handoff)

## Status

**Accepted** — WEB-01 freeze handoff addendum.

Supersedes nothing; **extends** ADR 0052 with the post-I12-R freeze checkpoint.

## Context

After I12-R:

```text
Knowledge Core v1 = FROZEN
Engine v1 = FROZEN
schema = v10
CORE = 65
prompt = v4
```

Product/Application consumes a frozen Engine. WEB-01 remains valid; the entry
checkpoint is now the dual freeze (Core + Engine), not Core-only.

## Decision

### Layer authorities (no overlap)

| Layer | Owns |
|-------|------|
| **Product** | auth/session UX, conversation state, message persistence, public API DTO, request orchestration, presentation mapping, client idempotency |
| **Engine** | interpretation, semantic resolution, ExecutionReadiness, EXECUTE/CLARIFY/SAFE_ABSTAIN, ClarificationRecoveryService, query semantic orchestration |
| **Knowledge Core** | knowledge/primitive/temporal/correction semantics, persistence knowledge contracts, query truth foundations |

```text
PRODUCT_ENGINE_AUTHORITY_CONFLICT_COUNT = 0
```

### Capability contract (Product mapping)

Engine outcomes remain authoritative:

```text
EXECUTE → Product committed / answered (after real commit/query)
CLARIFY → Product needs_clarification / clarification_required
SAFE_ABSTAIN → Product unsupported (not error, not clarification)
```

Product may render/transport/persist conversation and solicit user answers.
Product must not reinterpret, correct, substitute, infer, or override Engine outcomes.

### Public API

Stable multiplatform boundary: `/api/v1/`

Public DTOs (`ApiMessageRequest`, `ApiMessageResponse`, …) remain distinct from
internal Engine IR (`SemanticProposal`, `IngestIR`, `QueryIR`, …).

Conversation storage remains in **product** SQLite (`PRODUCT_SCHEMA_VERSION`),
isolated from Knowledge Core schema v10.

Identity is server-derived (`DEV_AUTH` temporary). Body `user_id` is never authority.

`client_request_id` provides idempotent POST retries.

Clarification answers flow through Application → `ClarificationRecoveryService`
(not `original + answer → full Interpreter`).

### UI honesty

Acknowledgement copy that claims persistence is emitted only after confirmed
commit (`operation.outcome = committed`).

## Consequences

- Next Product work deepens application UX/integration on this contract.
- No Core reopen / Engine reopen for WEB-01 shell closure.
- Future Web/PWA/Mobile/Desktop share the same Product API boundary.

## References

- `docs/ENGINE-V1-FREEZE.md`
- ADR 0069 (Engine v1 freeze)
- ADR 0052 (original multiplatform boundary)
- `docs/reports/WEB-01-PKE-WEB-CLIENT-API-CONTRACT.md`
