# ADR 0064 — Bounded Clarification Recovery (I12.13)

## Status

**CLOSED — implemented (MVP entity_reference)**

## Context

I12.12 defined execute / clarify / abstain. Product `answer_clarification` still did:

```text
original + answer → full Interpreter
```

violating the strategy.

## Decision

### Authority

```text
CLARIFICATION_RECOVERY_AUTHORITY = ClarificationRecoveryService
  (pke.application.clarification_recovery)
```

Composes CapabilityStrategy, ExecutionReadiness, EntityResolver (optional), IngestService.
Does not call `Interpreter.interpret`.

### Resume stage

```text
CLARIFICATION_RECOVERY_RESUME_STAGE =
  apply_clarification_evidence
  → resolve_proposal
  → assess_execution_readiness / decide_capability
  → IngestService.ingest_from_ir
```

### Pending operation

Workflow-only `PendingSemanticOperation` stored in Product SQLite
`clarifications.pending_operation_json` (not Knowledge Core).

### Supported / unsupported

```text
SUPPORTED = entity_reference
  (measured_entity, relation_subject, relation_object, state_entity, attribute_entity)

UNSUPPORTED in this increment =
  dimension, value, correction_target
→ RECOVERY_UNSUPPORTED_SLOT (no crash, no full reinterpretation)
```

### Cutover

`ConversationOrchestrator.answer_clarification` uses bounded recovery only.
Legacy concat path removed from canonical flow.

### Budget

```text
MAX_CLARIFICATION_ROUNDS_PER_PENDING_OPERATION = 1
```

## Consequences

- MP1 measured_entity recovery: deterministic + live fixture **100%**
- Relation/State entity fill alone often insufficient (identity/value still incomplete) — coverage debt
- Knowledge Core v1 remains FROZEN

See `docs/reports/I12.13-BOUNDED-CLARIFICATION-RECOVERY.md`.
