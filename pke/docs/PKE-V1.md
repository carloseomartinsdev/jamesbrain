# PKE v1 — Canonical Architecture Summary

**Status:** `PKE_V1 = COMPLETE`  
**Date:** 2026-09-04  
**Freeze gate:** P-R — Product v1 Final Revalidation & PKE v1 Completion  
**ADR:** `docs/decisions/0075-product-v1-final-revalidation-and-pke-v1-completion.md`

---

## Meaning of COMPLETE

```text
PKE v1 COMPLETE does not mean feature-complete forever.

It means the first coherent production-oriented
architecture and user-facing product boundary
has passed its declared v1 safety,
reliability and usability gates.
```

---

## Layer stack

| Layer | Status | Canonical versions |
|-------|--------|-------------------|
| Knowledge Core v1 | **FROZEN** | schema **v10**, CORE **65** |
| Engine v1 | **FROZEN** | prompt **v4**, provider **deepseek-chat** |
| Product v1 | **FROZEN** | Product schema **1.4**, API `/api/v1/` |

Documents:

- Knowledge / Engine freeze: `docs/ENGINE-V1-FREEZE.md`
- Product freeze: `docs/PRODUCT-V1-FREEZE.md`
- UX boundary: `docs/PRODUCT-V1-UX-BOUNDARY.md`

---

## End-to-end architecture

```text
┌─────────────────────────────────────────────────────────────┐
│ Clients (Web / future API consumers)                        │
│   I/O + presentation only — not semantic authority          │
└───────────────────────────┬─────────────────────────────────┘
                            │ public DTOs
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Product API  /api/v1                                        │
│   PRODUCT_API_AUTHORITY                                     │
├─────────────────────────────────────────────────────────────┤
│ Identity / Session                                          │
│   PRODUCT_IDENTITY_AUTHORITY                                │
│   PRODUCT_SESSION_AUTHORITY                                 │
│   PRODUCT_RESOURCE_OWNERSHIP_AUTHORITY                      │
├─────────────────────────────────────────────────────────────┤
│ ConversationOrchestrator                                    │
│   CONVERSATION / MESSAGE / CLARIFICATION lifecycle          │
│   PRODUCT_IDEMPOTENCY_AUTHORITY                             │
│   ENGINE_INVOCATION_AUTHORITY                               │
│   PUBLIC outcome mapping (DTO)                              │
├──────────────┬──────────────────────────────┬───────────────┤
│ ProductStore │ ProductRecoveryService       │ EngineGateway │
│ (durable)    │ operational reconciliation   │               │
└──────┬───────┴──────────────┬───────────────┴───────┬───────┘
       │                      │                       │
       │ Product SQLite       │ metadata only         │
       │ schema 1.4           │ (non-semantic)        ▼
       │                      │         ┌─────────────────────────┐
       │                      │         │ Engine v1 FROZEN        │
       │                      │         │ Interpreter (proposal)  │
       │                      │         │ ExecutionReadiness      │
       │                      │         │ CapabilityStrategy      │
       │                      │         │ ClarificationRecovery   │
       │                      │         │ Correction guards       │
       │                      │         └───────────┬─────────────┘
       │                      │                     │
       │                      │                     ▼
       │                      │         ┌─────────────────────────┐
       │                      │         │ Knowledge Core v1       │
       │                      │         │ FROZEN (schema v10)     │
       │                      │         │ semantics + persistence │
       │                      │         └─────────────────────────┘
       └──────────────────────┴───────────────────────────────────
```

---

## Authority boundaries (final)

| Authority | Owner |
|-----------|--------|
| `PRODUCT_API_AUTHORITY` | FastAPI `/api/v1` + DTOs |
| `PRODUCT_IDENTITY_AUTHORITY` | ProductAuthService |
| `PRODUCT_SESSION_AUTHORITY` | ProductAuthService + sessions |
| `PRODUCT_RESOURCE_OWNERSHIP_AUTHORITY` | ConversationOrchestrator + scoped store |
| `CONVERSATION_LIFECYCLE_AUTHORITY` | ConversationOrchestrator |
| `MESSAGE_LIFECYCLE_AUTHORITY` | ConversationOrchestrator |
| `PENDING_CLARIFICATION_AUTHORITY` | ConversationOrchestrator |
| `PRODUCT_IDEMPOTENCY_AUTHORITY` | ProductStore + ProductRecoveryService |
| `PRODUCT_RECOVERY_AUTHORITY` | ProductRecoveryService |
| `PUBLIC_OUTCOME_RENDERING_AUTHORITY` | `web/assets/js/renderers/index.js` |
| `ENGINE_INVOCATION_AUTHORITY` | ConversationOrchestrator → EngineGateway |
| `INTERPRETER_AUTHORITY` | Interpreter |
| `EXECUTION_READINESS_AUTHORITY` | ExecutionReadiness |
| `CAPABILITY_STRATEGY_AUTHORITY` | CapabilityStrategy |
| `CLARIFICATION_RECOVERY_AUTHORITY` | ClarificationRecoveryService |
| `CORRECTION_ACCEPTANCE_AUTHORITY` | Correction Acceptance Guard |
| `CORRECTION_TARGET_AUTHORITY` | CorrectionTargetResolver |
| `ASSERTION_EFFECTIVENESS_AUTHORITY` | AssertionEffectivenessResolver |
| `ENTITY_RESOLUTION_AUTHORITY` | EntityResolver |
| `TEMPORAL_WRITE_AUTHORITY` | TemporalResolver |
| `TEMPORAL_QUERY_AUTHORITY` | QueryTemporalResolver |
| `STATE_EPISTEMIC_AUTHORITY` | StateResolver |
| `RELATION_EPISTEMIC_AUTHORITY` | Relation authorities |
| `ATTRIBUTE_EPISTEMIC_AUTHORITY` | AttributeResolver |
| `MEASUREMENT_QUERY_AUTHORITY` | Measurement query authority |
| `KNOWLEDGE_COMMIT_AUTHORITY` | IngestService / UoW |

```text
FINAL_AUTHORITY_CONFLICT_COUNT = 0
```

---

## Supported capability (stack)

Engine capability outcomes Product must represent without override:

```text
EXECUTE / CLARIFY / SAFE_ABSTAIN
```

Product application capabilities: authentication, conversation lifecycle, durable messaging, clarification, query/write/correction presentation, idempotent retry, operational recovery, truthful UX.

---

## Explicit limitations

- Ontology coverage beyond CORE 65 = POST_V1
- Autonomous model recall improvements = POST_V1
- Additional clarification families = POST_V1
- Native clients, streaming, multimodal input = POST_V1
- Knowledge administration UI / analytics = POST_V1
- No distributed ACID across Product + Knowledge stores

---

## Canonical invariants

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
Engine executes only after semantic readiness.
Engine may clarify only supported detectable gaps.
Engine may safely abstain.
Unknown != false.
recorded_at != fact time.
Correction preserves history.
COMMIT_VALID_INDEPENDENTLY remains intact.
Product acknowledgement follows real commit evidence.
Retries are idempotent.
Recovery is operational, not semantic.
No distributed ACID guarantee is claimed.
Knowledge Core v1 remains frozen.
Engine v1 remains frozen.
```

---

## Post-v1 debt (not v1 safety blockers)

| Debt | State | V1 blocker? | Destination |
|---|---|---:|---|
| Ontology coverage | OPEN | NO | V1.x / V2 |
| Model recall | OPEN | NO | V1.x / V2 |
| Additional clarification families | OPEN | NO | V1.x / V2 |
| State coverage | OPEN | NO | V1.x / V2 |
| Relation coverage | OPEN | NO | V1.x / V2 |
| Event reliability | OPEN | NO | V1.x / V2 |
| Measurement analytics | OPEN | NO | V1.x / V2 |
| TYPE persistence | OPEN | NO | V1.x / V2 |
| Adaptive aliases | OPEN | NO | V1.x / V2 |
| Behavioral hypotheses | OPEN | NO | V1.x / V2 |
| Native clients | OPEN | NO | V1.x / V2 |
| Streaming | OPEN | NO | V1.x / V2 |
| File/voice input | OPEN | NO | V1.x / V2 |

---

## Reopen rule

A frozen layer may be reopened only with concrete evidence that a frozen invariant is violated — not merely because a new feature would be useful.

After freeze, expansion work is **V1.x / V2** and does not automatically reopen Core, Engine, or Product v1.
