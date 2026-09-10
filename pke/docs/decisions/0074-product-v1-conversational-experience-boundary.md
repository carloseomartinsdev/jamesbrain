# ADR 0074 — Product v1 Conversational Experience Boundary

## Status

**Accepted** — P4 Product UX completion.

Extends ADR 0070–0073. Does not freeze Product v1 itself (final revalidation next).
Does not reopen Engine or Knowledge Core.

## Context

Identity, lifecycle, and resilience are complete. Remaining work was making the
Web experience conversation-first, truthful, and usable without exposing
internal PKE architecture.

## Decision

### Product v1 definition

```text
Product v1 is conversation-first.
Product v1 is not a Knowledge administration console.
Product v1 exposes Engine capability, not Engine internals.
Product v1 preserves epistemic uncertainty.
Product v1 never claims persistence before confirmed commit.
Product v1 treats clarification as normal interaction.
Product v1 treats SAFE_ABSTAIN as safe capability boundary, not technical failure.
Conversation history is Product history, not Knowledge authority.
```

### Authorities (`PRODUCT_UX_AUTHORITY_CONFLICT_COUNT = 0`)

| Authority | Owner |
|-----------|--------|
| `PRODUCT_API_AUTHORITY` | FastAPI `/api/v1` + DTOs |
| `PRODUCT_IDENTITY_AUTHORITY` | ProductAuthService |
| `CONVERSATION_LIFECYCLE_AUTHORITY` | ConversationOrchestrator |
| `PRODUCT_RECOVERY_AUTHORITY` | ProductRecoveryService |
| `PUBLIC_OUTCOME_RENDERING_AUTHORITY` | `web/assets/js/renderers/index.js` |
| `AUTH_UI_STATE_AUTHORITY` | `web/assets/js/app.js` auth gate |
| `CONVERSATION_UI_STATE_AUTHORITY` | `web/assets/js/app.js` + conversation state |
| `CLARIFICATION_UI_STATE_AUTHORITY` | renderer + `pendingClarification` |

### UX truthfulness

| Product state | User presentation |
|---------------|-------------------|
| committed | Natural acknowledgement (e.g. “Registrei…”) |
| answered | Conversational answer |
| needs_clarification | Inline clarification card |
| unsupported | Distinct non-error abstain |
| failed retryable | Technical error + retry |
| failed terminal / conflict | Technical/conflict note, no false success |
| recovery_required | Uncertainty note — not success, not confirmed failure |

### Scope exclusions (Product v1)

No graph UI, ontology editor, voice, uploads, sharing, Knowledge CRUD panel,
streaming, or native apps.

## Consequences

- Final Product freeze is a separate revalidation increment
- Manual visual checklist remains recommended for desktop/mobile polish
