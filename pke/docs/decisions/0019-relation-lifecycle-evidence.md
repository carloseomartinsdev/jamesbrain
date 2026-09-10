# ADR 0019 — Relation Lifecycle & Termination Evidence

## Status

Accepted — I11.5.1

## Context

I11.5 introduced Relation with termination via `valid_to = recorded_at`, collapsing assertion provenance with termination evidence and inventing calendar precision where none existed.

Audit classification: **LIFECYCLE_MODEL_INSUFFICIENT**.

## Problem

“João não trabalha mais na Acme.” provides **termination knowledge**, not a calendar endpoint. The original row's `source`/`raw_input_id`/`observed_at` describe the assertion, not the termination.

## Decision

**Strategy A — lifecycle fields on Relation** (minimal; no generic Evidence primitive).

Add termination-specific fields mirroring assertion structure:

```text
termination_temporal
termination_observed_at
termination_raw_input_id
termination_source
termination_confidence
```

Repository exposes `terminate(relation, RelationTerminationEvidence)` — not generic `update_relation`.

### Relation assertion

Original fields unchanged: `temporal`, `observed_at`, `source`, `raw_input_id`, `confidence`.

### Relation termination

`Relation.apply_termination(evidence)` sets termination fields + `is_current=false`.

### Termination temporal knowledge

Reuses `TemporalKnowledge`. Partial termination without calendar → PARTIAL + `relation_to_reference=BEFORE`.

### Unknown termination date

Termination known (`termination_observed_at` set) while `valid_to` remains `null` when no calendar anchor exists.

**PROHIBITED:** `valid_to = recorded_at` / `valid_to = today` without explicit calendar.

### valid_to semantics

**B — best temporal knowledge endpoint.** Set only from `relation_calendar_endpoint(termination_temporal)`. Never write-time closure marker.

### is_current semantics

Bookkeeping flag. `termination_known → is_current=false` even when termination calendar unknown.

### Correction vs termination

`RelationAssertionMode.TERMINATE` = ended after holding. `DENY_CURRENT` = not current without termination evidence (no termination fields). Full correction engine deferred.

### Event linkage

`caused_by_event_id` on termination evidence when explicit; never inferred from “não trabalha mais”.

### Persistence

Storage v5→v6 (`persist/migrations/v5_to_v6.py`). Legacy rows with `valid_to == observed_at` cleared during migration; termination provenance not fabricated.

## Deferred

- **EVIDENCE-01** — generic Assertion/Evidence primitive if multi-evidence graph needed
- Correction/contradiction (“nunca trabalhou lá”)
- TIME-01 calendar vs epistemic incompleteness refactor

## Consequences

- Distinct assertion vs termination provenance (LT provenance test)
- Query: current NO, historical YES, termination date UNKNOWN when calendar absent
- I11.5-R can proceed after review
