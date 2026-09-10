# ADR 0017 — State Dimension & Value Semantics (I11.4.1)

## Status

Accepted — 2026-09-02

## Context

I11.4 introduced `State` but treated flat concepts like `state.anomaly` and `state.working` as independent dimensions. Transition tests showed both could be `is_current=True` simultaneously — a semantic error.

## Problem

The model conflated **state dimension** (axis of variation) with **state value** (mutually exclusive condition within that axis).

## Decision

### State model v2

```text
State
  dimension_id / dimension_key    # e.g. state.operational_condition
  value_concept_id / value_key    # e.g. state.value.broken
  payload                         # non-semantic associated data (quantity, unit)
  is_current                      # persisted; supersession sets False
  temporal, observed_at, valid_from, valid_to, supersedes_id
```

### Dimension vs Value

| Dimension | Values (mutually exclusive) |
|-----------|----------------------------|
| `state.operational_condition` | broken, working |
| `state.availability` | depleted |
| `state.payment_status` | unpaid |
| `state.due_status` | overdue |
| `state.openness` | open, closed |
| `state.validity` | valid, expired |
| `state.observed_quantity` | quantity_observation (PROVISIONAL) |

### Mutual exclusivity

Values within the same dimension compete for `current`. Values across dimensions coexist.

### Current state

Resolved **per dimension** via `resolve_current_by_dimension()` — not one global state per entity.

### Supersession

New state in same dimension closes prior `is_current` rows (`valid_to`, `is_current=False`, `supersedes_id`). No destructive DELETE.

### Unknown ordering

If temporal ordering is insufficient, `TemporalCompleteness.PARTIAL/INDETERMINATE` — never false certainty.

### Semantic corrections

- `UNPAID ≠ OVERDUE` — separate dimensions (`payment_status` vs `due_status`)
- `DEPLETED ≠ UNAVAILABLE` — only `depleted` modeled; no generic unavailable value

### State vs Measurement

S6 mileage uses `state.observed_quantity` + payload as **PROVISIONAL**. Future `Measurement` / `TemporalAttribute` primitive may supersede. Not frozen as universal pattern.

### Storage

**MIGRATION_REQUIRED: v3 → v4**

- Added: `dimension_concept_id`, `dimension_key`, `value_concept_id`, `value_key`, `is_current`
- Renamed semantic: `value_kind` → `payload_kind`
- v3 legacy keys mapped via `migrate_v3_to_v4`

## Consequences

- Transition broken→working works correctly on same dimension
- Query returns multiple current states when dimensions differ
- Wire/IR use `state.value` concept keys, not flat state types

## Deferred

- Measurement primitive
- RuleEngine for overdue inference
- TIME-01, MIGRATION-01
