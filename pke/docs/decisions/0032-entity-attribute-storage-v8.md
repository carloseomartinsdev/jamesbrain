# ADR 0032 — EntityAttribute Storage v8 Implementation (I11.12.2)

## Status

Accepted — implements ADR 0030/0031.

## Schema

```text
previous = v7
current  = v8
migration = Python runner MigrationStep(7, 8, migrate_v7_to_v8)
authority = pke.persist.migrations.runner (Alembic non-authoritative)
```

## Canonical source

```text
WHAT_IS_THE_CANONICAL_SOURCE_OF_ATTRIBUTE_KNOWLEDGE?
table entity_attributes / domain EntityAttribute
```

Not Fact.attribute.*, State, Event metadata, or JSON bag.

## Typed value

Explicit `value_kind` + CHECK constraint + domain validator: exactly one semantic value representation.

Numeric: `Decimal` via `DecimalAsText` (no float).

## Dimension identity

`dimension_key` required (stable semantic key: color, area, …).  
`dimension_concept_id` optional NULL — no CORE explosion.

## Cardinality

0..N assertions per (entity, dimension). No UNIQUE on dimension. No auto-supersession on write.

## Temporal

Unknown fact time → `TemporalKnowledge.UNKNOWN`.  
`created_at` / `observed_at` never become `valid_from`.  
Historical (`era`) → `is_current=False` without inventing calendar.

## Materialization

`PrimitiveKind.ATTRIBUTE` → `IrAttribute` → `EntityAttribute`.  
TYPE remains non-materializable. No automatic Event→Attribute.

## Indexes

```text
user_id
entity_id
(entity_id, dimension_key)
(entity_id, dimension_key, is_current)
dimension_key
```

## Delete

FK to entities: **no ON DELETE CASCADE** (matches State/Relation).

## Deferred

```text
ATTRIBUTE-QUERY-01 — NL query + current-value resolution
MEASUREMENT-01 — open
ONTOLOGY-COVERAGE-01 — reduced for color/area via dimension keys; not CLOSED
```
