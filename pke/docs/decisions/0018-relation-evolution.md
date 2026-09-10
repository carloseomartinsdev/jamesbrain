# ADR 0018 — Relation Evolution

## Status

Accepted — I11.5

## Context

Relation existed as a minimal stub (`from_id`, `to_id`, `type_id`, `valid_from`/`valid_to`) without temporal semantics, currentness, history, ingest IR, or query path. Employment and other links were blocked as `ArchitecturalGap.RELATION` (PEOPLE_001).

State (I11.4) closed the dimensional state model but must not absorb binary entity links.

## Problem

Utterances like “João trabalha na Acme.” assert a **link**, not a state dimension value nor a hiring event. The engine needed a productive Relation primitive with evolution, without collapsing Event/State/Attribute.

## Decision

**CURRENT_MODEL_REUSABLE (partial) + STRUCTURAL_MIGRATION_REQUIRED**

Reuse `from_id`/`to_id`/`type_id` columns; evolve domain and storage v4→v5 with State-like temporal columns, `is_current`, history via termination (not delete), and explicit IR `RECORD_RELATION`.

### Relation identity

`(subject_entity_id/from_id, relation_concept_id, object_entity_id/to_id)` — context deferred.

### Directionality

Canonical storage direction per concept (e.g. person `employed_by` organization). Inverse metadata only (`relation.employs`); no automatic dual rows.

### Inverse relations

Metadata in `ontology/relation_metadata.py`. Query inverse derivation deferred.

### Symmetry

`married_to` uses canonical entity-id ordering; symmetric query matches without duplicate rows.

### Temporal semantics

Reuse `TemporalKnowledge` (EXACT, INTERVAL, PARTIAL, UNKNOWN). `observed_at ≠ valid_from`.

### Currentness

`is_current` is persisted bookkeeping; epistemic resolution uses temporal + scope in query. Termination sets `valid_to` + `is_current=false` without invented dates.

### History

Rows preserved on termination. No DELETE.

### Termination

`RelationAssertionMode.TERMINATE` closes the **same instance** only.

### Relation vs Event

“Trabalha na Acme” → Relation only. “Começou a trabalhar…” may yield Event + Relation when explicit.

### Relation vs State

Employment is Relation (binary). “Desempregado” would be State — not inferred from missing Relation.

### Relation vs Attribute

“Brasileiro” → Attribute. “Trabalha na Acme” → Relation.

### Concurrency

Same concept + different objects may both be `is_current=true`. No dimension-style supersession.

### Persistence

Storage v4→v5 migration (`persist/migrations/v4_to_v5.py`). Alembic stub only (MIGRATION-01 unchanged).

## CORE relation concepts added

| key | meaning | direction | inverse | symmetric |
|-----|---------|-----------|---------|-----------|
| relation.employed_by | employment | person → org | employs | no |
| relation.resides_at | residence | person → place | — | no |
| relation.owns | ownership | person → thing | owned_by | no |
| relation.married_to | marriage | person ↔ person | — | yes |
| relation.parent_of | progenitor | parent → child | child_of | no |
| relation.provider_for | professional service | provider → person | client_of | no |

Also: `entity.place` for location endpoints.

Removed `relation.provided_by` seed (superseded by `provider_for`).

## Consequences

- Deterministic ingest/query for R1–R6 and PEOPLE_001 (with FakeIR).
- Live interpreter generalization deferred to I11.5-R (INTERPRETER-RELATION-01).
- RelationContext, cardinality ontology, inverse query, RuleEngine — deferred.

## Deferred work

- RelationContext payload for branch/office qualifiers
- Ontological cardinality / exclusivity rules
- Inverse query derivation
- Event→Relation automatic linkage (minimal explicit only)
- Live wire tuning beyond prompt principle
