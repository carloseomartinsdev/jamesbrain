# ADR 0061 — Structured Proposal Completeness and Safe Execution Readiness (I12.10)

## Status

**CLOSED — implemented**

## Context

I12.9 showed:

- 96.4% of live runs produce a **valid** SemanticProposal
- only 54.6% are **semantically useful / execution-ready**
- MP1 typically emits Event + Measurement with `subject=null`
- Engine collapsed that case to `semantic_resolution:concept_resolution`

That collapse mixed **invalid proposals** with **valid but execution-incomplete** proposals.

## Decision

Introduce a single deterministic authority:

```text
pke.interpretation.semantic.execution_readiness
```

It inspects SemanticProposal + persistability + assertion frames.

It does **not** read `raw_input` to invent missing entities, roles, primitives, or dimensions.

### Distinctions

```text
proposal validity ≠ semantic completeness ≠ materialization readiness ≠ persistence
```

Per-primitive statuses (existing persistability reused):

| Status | Meaning |
|--------|---------|
| READY | wire_allowed |
| SAFE_PARTIAL_NON_MATERIALIZABLE | e.g. Event category unresolved (I12.7.1) |
| INCOMPLETE_REQUIRED_INFORMATION | required identity missing (entity, endpoints, dimension/value) |
| REJECTED_INVALID | unsafe / blocked |

Overall:

- VALID_EXECUTABLE
- VALID_PARTIALLY_EXECUTABLE (COMMIT_VALID_INDEPENDENTLY)
- VALID_EXECUTION_INCOMPLETE (zero materializable, semantics retained)
- INVALID

Zero-materializable valid proposals use `failure_stage=EXECUTION_INCOMPLETE` instead of generic `CONCEPT_RESOLUTION`.

Application mapping:

- `semantic_resolution:execution_incomplete:…` → `IngestStatus.NEEDS_CLARIFICATION` when the missing slot is user-answerable
- otherwise `UNSUPPORTED`
- never `COMMITTED` when nothing materializes

## Non-goals (this increment)

- Prompt / model / provider change
- SemanticProposal schema change
- Wire expansion
- Reconstructing `temperatura` from raw text
- Multi-pass Interpreter
- Closing INTERPRETER-EVENT-01 via abstention

## Consequences

- MP1 missing-subject is **safe incomplete**, not a parser crash.
- MP1 knowledge **capture** remains unsolved (model still omits measured entity).
- Independent ready primitives still commit (MP1 with subject → Measurement commits, Event non-materialized).

## Core freeze

Knowledge Core v1 FROZEN · schema v10 · CORE 65 · prompt v4 · holdout untouched.
