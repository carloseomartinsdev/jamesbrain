# P4 — Product UX manual checklist

Use on desktop and a narrow/mobile viewport.

## Auth
- [ ] Login with valid credentials
- [ ] Invalid credentials message (not generic “Login failed” only)
- [ ] Network/server failure distinct when offline
- [ ] Session expiry returns to login without foreign conversation flash
- [ ] Logout clears history UI; other user sees empty/own list

## Conversation
- [ ] Empty state suggestions
- [ ] Nova conversa
- [ ] Sidebar history + active highlight
- [ ] Enter send / Shift+Enter newline
- [ ] Double-submit does not duplicate
- [ ] Processing “Pensando…” without premature “saved”

## Outcomes
- [ ] Successful write acknowledgement
- [ ] Query answer readable
- [ ] Clarification choice / text modes
- [ ] Reload restores pending clarification
- [ ] Safe abstain looks non-error
- [ ] Technical error distinct from abstain
- [ ] recovery_required wording (if provoked) is uncertain, not success/failure

## Responsive / a11y
- [ ] Mobile drawer works
- [ ] Composer usable
- [ ] Focus visible on controls
- [ ] Long answers wrap without breaking layout
