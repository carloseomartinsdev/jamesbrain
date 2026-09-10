# ADR 0068 — Event Residual Reliability and Engine v1 Freeze Gate

## Status

**CLOSED — residual audit complete; no material Engine v1 Event blocker**

## Context

After I12.15 (State) and I12.16 (Relation), Event remained the last language-boundary
primitive under residual audit before Engine v1 freeze.

Prior Event work (I12.5–I12.7, I12.8) already established:

- explicit Event semantics preserved
- multi-primitive Event + Measurement preservation
- partial Event not silently discarded
- partial Event not falsely canonicalized
- `event.intent` fallback removed
- `COMMIT_VALID_INDEPENDENTLY` for sibling Measurement

I12.17 is an **audit / freeze gate**, not a redesign.

## Decision

### Central finding

```text
DOES_EVENT_INTERPRETATION_STILL_CONTAIN
A MATERIAL ENGINE_V1_BLOCKING_DEFECT?
= NO
```

Live residual replay (I12.11 baseline Event / multi_primitive proposals):

| Primary | Runs |
|---------|-----:|
| EVENT_SAFE_PARTIAL | 90 |
| EVENT_CORRECT | 23 |
| EVENT_OMITTED_BY_MODEL | 1 |

`EVENT_ENGINE_DEFECT_RATE = 0`. All mandatory safety counters = 0.

### Dominant residual classes (non-blocking)

| Class | Count | Classification |
|-------|------:|----------------|
| Ontology / canonical unresolved | 70 | `ONTOLOGY_COVERAGE_LIMIT` / POST_V1 |
| Entity clarification gaps | 20 | `PRODUCT_CLARIFICATION_LIMIT` |
| Safe abstention / correct path | 23 | `SAFE_ABSTENTION` |
| Model omission | 1 | `MODEL_CAPABILITY_LIMIT` |

Low autonomous Event recall alone is **not** an Engine blocker when:

- known structured Event semantics are preserved
- unsupported semantics are not invented
- partial Events remain non-materialized, not fake-canonicalized
- siblings may still commit independently

### Freeze posture

```text
ENGINE_V1_FREEZE DOES_NOT_MEAN UNLIMITED_ONTOLOGY_COVERAGE
ENGINE_V1_FREEZE DOES_NOT_MEAN 100% AUTONOMOUS INTERPRETATION RECALL
```

Engine v1 is reliable within its explicit capability boundary when it consistently
chooses among `EXECUTE` / `CLARIFY` / `SAFE_ABSTAIN` without fabricating certainty.

### Not done (by design)

- No prompt / model / provider switch
- No SemanticProposal / Wire / RetryPolicy change
- No Core reopen / schema / migration / ontology expansion
- No raw-text Event detector
- No holdout touch

## Consequences

- `INTERPRETER-EVENT-01` = **CLOSED** (no material Engine blocker)
- State / Relation remain **PARTIALLY_MITIGATED** (ontology coverage)
- `ONTOLOGY-COVERAGE-01` = **POST_V1**
- Proceed to Engine v1 final revalidation (not another Event increment)

See `docs/reports/I12.17-EVENT-RESIDUAL-RELIABILITY.md`.
