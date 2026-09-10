# ADR 0023 — Partial Canonicalization & Knowledge Materialization

## Status

Accepted — I11.8

## Context

I11.7 improved proposal reliability. Live frontier moved to CANONICAL_IR / MATERIALIZATION.
Audit found two primary rejection points:

1. `resolution_to_wire_ingest` rejected any `concepts.unresolved=True` (over-broad)
2. `event.maintenance` completeness schema required `action.maintain` as ESSENTIAL, blocking
   valid occurrence events (e.g. "A geladeira quebrou") that have event type cue but no action

I11.6-R had identified OVERCONSTRAINED_CANONICALIZATION.

## Decision

### Validity ≠ completeness

Introduce `assess_persistability()` with primitive-specific minimum persistable knowledge:

- **Event**: occurrence semantics + ≥1 semantic anchor (action, event_type, entity context, expression)
- **State**: valid state_value required; dimension may be inferred from value parent
- **Relation**: relation_type + subject + object (unchanged rigidity)
- **Attribute**: not materializable in this increment

### Critical vs non-critical unresolved

- `ontology_gap`, `safe_abstention` (install), BLOCKED, AMBIGUOUS → no wire
- Event with action resolved but event_type missing → partial wire allowed
- Event with event_type cue but no action → wire allowed (occurrence knowledge)

### Event category vs action

`action.replace` preserved without requiring specific event taxonomy.
Parent `event.maintenance` used only when action or event cue justifies it — not as generic filler
when no anchors exist.

### Completeness schema

`event.maintenance` action slot: ESSENTIAL → USEFUL (ask_if_missing).
TIME remains ESSENTIAL. Validation unchanged.

### No semantic invention

No nearest-concept coercion, no materializer NL inference, no CORE expansion.

## Consequences

### Positive

- Partial Event knowledge can persist (broke/open/replace clutch)
- Install ontology gap remains safely abstained
- Relation/State identity not weakened

### Negative / deferred

- EVENT-QUERY-01: action-based retrieval may need query refactor
- ONTOLOGY-COVERAGE-01: install still blocked without CORE action.install

## References

- ADR 0021, 0022
- I11.7 report
- I11.8 specification
