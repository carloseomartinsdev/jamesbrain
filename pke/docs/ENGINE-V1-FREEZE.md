# Engine v1 Freeze

**Status:** `ENGINE_V1 = FROZEN`  
**Freeze decision:** I12-R — Engine v1 Final Revalidation & Freeze  
**Date:** 2026-09-03

---

## Versions

| Item | Value |
|------|-------|
| Engine version | **v1 (FROZEN)** |
| Knowledge Core | **v1 (FROZEN)** |
| Storage schema | **v10** |
| CORE concept count | **65** |
| Interpreter prompt | **v4** (`pke.interpret.v4`) |
| Provider baseline | **deepseek-chat** |
| SemanticProposal | unchanged (I12+) |
| Wire | unchanged |
| RetryPolicy | unchanged (`max_attempts=2`, SDK retries=0) |
| Holdout | **UNTOUCHED** |

---

## Supported capability boundary

Engine v1 consistently chooses among:

```text
EXECUTE          (auto_execute / partial_execute)
CLARIFY
SAFE_ABSTAIN
```

```text
ENGINE_V1_FREEZE DOES NOT MEAN UNLIMITED ONTOLOGY COVERAGE.
ENGINE_V1_FREEZE DOES NOT MEAN 100% AUTONOMOUS INTERPRETATION RECALL.
ENGINE_V1_FREEZE MEANS THE ENGINE BEHAVES SAFELY AND PREDICTABLY
INSIDE ITS DECLARED CAPABILITY BOUNDARY.
```

---

## Architecture (canonical)

```text
User/App Input
     ↓
Interpreter (LLM proposes; not source of truth)
     ↓
SemanticProposal
     ↓
Resolution / Routing
     ↓
ExecutionReadiness
     ↓
CapabilityStrategy
  ┌──┼───────────┐
  ↓  ↓           ↓
EXECUTE CLARIFY ABSTAIN
  ↓      ↓
Ingest   ClarificationRecoveryService
  ↓      ↓
Knowledge Core (persist / query)
```

---

## Canonical authorities

| Responsibility | Canonical authority |
|---|---|
| Raw-language interpretation | Interpreter |
| Provider transport/retry | RetryPolicy / provider boundary |
| Semantic proposal structure | SemanticProposal |
| Transport normalization | Wire / proposal normalization |
| Primitive routing | semantic router (`collect_assertions`) |
| Entity resolution | EntityResolver |
| Temporal write semantics | TemporalResolver |
| Temporal query expansion | QueryTemporalResolver |
| State epistemic resolution | StateResolver |
| Relation semantic/lifecycle | Relation authorities |
| Attribute epistemic resolution | AttributeResolver |
| Measurement query semantics | Measurement resolver/query |
| Correction acceptance | Correction Acceptance Guard |
| Correction target identity | CorrectionTargetResolver |
| Correction effectiveness | AssertionEffectivenessResolver |
| Execution readiness | ExecutionReadiness |
| Execute / clarify / abstain | CapabilityStrategy |
| Clarification recovery | ClarificationRecoveryService |
| Persistence transaction | IngestService / UoW |
| Query truth/result semantics | Query layer / resolvers |

`ENGINE_AUTHORITY_CONFLICT_COUNT = 0`

---

## Frozen invariants

1. LLM output is proposal, not truth.
2. LLM never writes persistence directly.
3. Missing information is never invented.
4. Unknown canonical semantics are not forced.
5. Valid partial semantics are preserved.
6. Independent valid semantics may commit independently (`COMMIT_VALID_INDEPENDENTLY`).
7. Clarification only resolves explicitly authorized gaps.
8. Clarification answers are new evidence.
9. Safe abstention is a valid Engine outcome.
10. Query does not turn uncertainty into false certainty.
11. Time of record is not fact time.
12. Correction preserves history.
13. User isolation is mandatory.
14. Conversation ≠ Knowledge ≠ Session.
15. Core semantic authority remains outside Product clients.

---

## Clarification recovery (supported)

| Family | Slots |
|--------|--------|
| `entity_reference` | measured_entity, state_entity, attribute_entity, relation_subject, relation_object |
| `dimension` | measurement_dimension, attribute_dimension |
| `state_value` | state_value |

### Unsupported (POST_V1)

```text
correction_target
temporal
state_dimension
measurement_value
```

---

## Known non-blocking limitations (POST_V1)

- Ontology coverage beyond CORE 65
- Model autonomous recall (bounded; ~37–47% useful capture class historically)
- Additional clarification families
- Adaptive aliases / TYPE persistence
- Measurement analytics / `current_value`
- Behavioral hypotheses

These do **not** invalidate Engine v1 safety.

---

## Core vs Engine vs Product

| Layer | Owns |
|-------|------|
| **Knowledge Core** | world model + epistemic persistence semantics |
| **Engine** | interpretation + resolution orchestration + capability decision + clarification + querying orchestration |
| **Product** | HTTP/UI/auth/conversation presentation/streaming/notifications/settings |

Product must not reinterpret semantic outcomes, construct internal IR, override capability decisions, or expose SemanticProposal / IngestIR / QueryIR as public API.

---

## Test baseline (freeze close)

```text
pytest tests/ -m "not live"
4715 passed · 0 failed · 8 live deselected
```

ADR range for Engine reliability wave: **0060–0069** (freeze ADR = **0069**).

---

## Product handoff contract

```text
Product may call Engine.
Product may render Engine outcomes.
Product may maintain conversation/session/auth state.
Product must not reinterpret semantic outcomes.
Product must not construct internal IR manually.
Product must not override EXECUTE / CLARIFY / SAFE_ABSTAIN.
Product must not infer successful persistence before Engine commit.
Product must not expose internal semantic contracts as public API.
```

**Next phase:** `PRODUCT V1 / APPLICATION LAYER` — not another Interpreter hardening wave.
