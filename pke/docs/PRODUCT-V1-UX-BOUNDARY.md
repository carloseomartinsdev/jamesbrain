# Product v1 UX Boundary

Conversation-first Web Product. Not a Knowledge admin console.

## Supported flows

```text
login / register
logout
new conversation
continue conversation
message → committed write
message → query answer
message → clarification → bounded answer
message → safe abstain
reload / resume
retry (retryable technical)
recovery_required (explicit uncertainty)
desktop + mobile shell
```

## Public outcomes → presentation

| Outcome | UX |
|---------|-----|
| committed | Conversational acknowledgement |
| answered | Conversational answer |
| needs_clarification | Inline clarification |
| unsupported | Non-error abstain |
| failed + retryable | Technical error + retry |
| recovery_required | “Não consegui confirmar…” (not success/failure claim) |

## Truthfulness rules

```text
No commit claim before Engine commit
Unknown ≠ no
SAFE_ABSTAIN ≠ clarification
Clarification ≠ technical error
recovery_required ≠ confirmed success
recovery_required ≠ confirmed failure
```

## Architecture boundaries

```text
Web → /api/v1 → ConversationOrchestrator → EngineGateway → Engine → Knowledge
```

Frontend does not inspect Engine IR and does not decide semantics.

```text
Conversation ≠ Knowledge
Session ≠ Conversation
Product history ≠ Knowledge authority
```

## Explicitly unsupported in Product v1

```text
Knowledge graph UI
ontology editor
semantic debugger (normal UX)
analytics dashboards
voice / camera / file uploads
conversation sharing
multi-user conversations
offline semantic inference
native mobile/desktop apps
streaming responses
conversation deletion as Knowledge wipe
```

## Responsive / a11y baseline

- Desktop: sidebar + conversation
- Mobile: drawer history + full conversation + bottom composer
- Labels, focus-visible, Enter send / Shift+Enter newline
- Clarification controls keyboard-accessible

## Registration

Self-registration is part of Product v1 (`POST /api/v1/auth/register`).

## Manual checklist

See `docs/reports/P4-PRODUCT-UX-MANUAL-CHECKLIST.md`.
