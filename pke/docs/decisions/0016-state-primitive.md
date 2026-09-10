# ADR 0016 — State Primitive (I11.4)

## Status

Accepted — 2026-09-02

## Context

I11.1–I11.3 established partial temporal knowledge and showed that utterances describing **world conditions** (e.g. “a geladeira está quebrada”) should not be forced into `Event` or plain `Attribute`. I11.3-R2 classified cases like `SHOP_002` as blocked by missing `STATE` architecture.

## Problem

The productive model lacked a first-class primitive for conditions that:

- hold over time without implying a causal event;
- can be queried as current/historical;
- reuse `TemporalKnowledge` without inventing calendar anchors;
- preserve history on correction/transition.

## Decision

Introduce **`State`** as a productive primitive distinct from `Event`, `Action`, `Relation`, and generic `Attribute`.

### State semantics

| Primitive | Role |
|-----------|------|
| **State** | A semantically meaningful condition of an entity/context during an interval or point in time |
| **Event** | Something that happened/will happen — requires explicit event semantics |
| **Attribute** | Static or fact-like property (e.g. color); not a world condition that evolves |
| **Relation** | Typed link between entities (employment, ownership) — not a unary condition |

**Rule:** `observed state does not imply causal event`. `caused_by_event_id` is never inferred.

### State vs Attribute

- `Corolla.color = silver` → Attribute (stable property).
- `Corolla.condition = broken` → State (can transition, queried as current).
- `Corolla.mileage = 84500 at T` → `state.observed_quantity` (quantitative observation with temporal semantics), not a silent fact.

### State vs Relation

“João trabalha na Acme” remains `Relation` (I11.5). State does not subsume relational employment.

### State vs Event

- “A porta abriu.” → Event/Action.
- “A porta está aberta.” → State.
- Lexical form alone does not determine primitive; compositional semantics does.

### Temporal semantics

- Reuse `TemporalKnowledge` from I11.3 — no parallel temporal model.
- `observed_at` = when the assertion was known/recorded — **not** causal `started_at`.
- `valid_from` / `valid_to` only when explicitly provided or on supersession.
- Present-tense with no calendar → `TemporalKnowledge.partial_ongoing()`.

### History and current state

- Repository preserves all state rows; supersession sets `valid_to` on prior current row of same `(entity, state.key)`.
- **Current state** resolved via `resolve_current()` using temporal sort keys, not `MAX(observed_at)`.
- Unknown temporal ordering → `TemporalCompleteness.PARTIAL` or `INDETERMINATE` (never false certainty).

### StateObservation

Provenance is covered by `source`, `raw_input_id`, `observed_at`, and `confidence`. No separate `StateObservation` table in I11.4.

### IR / Wire

- `IngestIntent.RECORD_STATE` + `IrState` on `IngestIR`.
- Query `intent=state` + `state_types[]` on `QuerySpec`.
- Wire `record_state` intent and `state` block — catalog bucket `state_types`.

## CORE additions

| key | meaning | justification |
|-----|---------|---------------|
| `state.condition` | Parent for unary conditions | Structural root |
| `state.anomaly` | Broken / not working | S1, appliance faults |
| `state.depletion` | Depleted / unavailable | S2, SHOP_002 |
| `state.unpaid` | Overdue / unpaid obligation | S3 |
| `state.open` | Open position (door, etc.) | S4 |
| `state.expired` | Expired validity | S5 |
| `state.working` | Functioning normally | Transition test |
| `state.observed_quantity` | Quantitative observation at T | S6 mileage |
| `entity.home`, `entity.appliance`, `entity.document`, `entity.medication` | Entity types for S-cases | Minimal entity coverage |

## Persistence

- **Previous version:** `2`
- **New version:** `3`
- **Migration:** `pke.persist.migrations.v2_to_v3.migrate_v2_to_v3` (canonical Python path); Alembic stub `002_storage_v3_state_primitive.py`
- **Tables:** `states` extended with temporal columns, `observed_at`, `source_id`, `supersedes_id`, etc.

## Consequences

- Ingest can commit world conditions without inventing events.
- Query engine supports deterministic state queries with epistemic incompleteness.
- Interpreter/wire must learn `record_state` — live gap may remain until I11.4-R.

## Deferred work

- Relation Evolution (I11.5)
- Semantic Lexical Resolver (I11.6)
- SemanticFrame production integration
- Knowledge Enrichment, RuleEngine, Presenter, CLI
- TIME-01: calendar precision vs epistemic incompleteness
- MIGRATION-01: Alembic vs Python migration architecture
