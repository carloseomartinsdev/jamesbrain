# ADR 0031 — Attribute Routing Safety & v8 Storage Contract Freeze (I11.12.1)

## Status

Accepted — I11.12.1. **Schema remains v7.** No ORM/table/migration.

Extends ADR 0030.

## Type boundary

### Where TYPE became Attribute (before)

```text
“O Corolla é um carro.”
→ stable_property_semantics=true + attribute_expression
→ PrimitiveRouter ATTRIBUTE branch
→ persistability denied (attribute_not_materializable)
```

Persistence block was insufficient: classification still entered the Attribute path.

### Corrected boundary

```text
classification_semantics=true
→ PrimitiveKind.TYPE  (before Attribute branch)
→ resolver: SAFE_PARTIAL / classification sense
→ persistability: classification_not_materializable
→ never Attribute materialization path
```

Signal is structured (`classification_semantics`), not a raw `"é um"` lexical hack.

## Type architecture

```text
DOES_PKE_ALREADY_HAVE_A_CANONICAL_TYPE_PATH?
PARTIALLY
```

- Entity rows carry `type_id` / ontology `entity.*` via `kind_hint` → `resolve_entity_type`.
- Classification **utterances** do not yet update Entity type as a first-class write path.
- `PrimitiveKind.TYPE` is **routing-only** (no Type storage table). Safe non-Attribute outcome.

`ATTRIBUTE-TYPE-01` = **CLOSED** (operational path blocked).

## Typed value discriminator

```text
Choice: A — explicit value_kind enum
```

Reasons: validation safety, migration clarity, invalid-state prevention, queryability.

Exactly one semantic value representation active:

| value_kind | active fields |
|---|---|
| `text` | text_value |
| `number` | numeric_value + unit (one semantic quantity) |
| `year` | year_value |
| `date` | date_value |
| `concept` | concept_value_id |

`numeric_value` alone without unit is invalid for quantity kinds that require unit.

## Dimension identity

```text
WHAT_IDENTIFIES_AN_ATTRIBUTE_DIMENSION?
stable semantic key (required) + optional ontology concept FK
```

```text
dimension_key          TEXT NOT NULL   # e.g. attribute.color — stable, may predate CORE concept
dimension_concept_id   TEXT NULL       # optional FK when ontology concept exists
```

Storage must not require CORE expansion for every descriptive property. Ontology-backed dimensions are optional enrichment.

## Cardinality & uniqueness

```text
assertions per entity/dimension: 0..N
database uniqueness: NO UNIQUE(entity_id, dimension)
functional vs multi-valued: resolver/metadata later — not DB uniqueness
```

## Assertion identity

Primary key = assertion `id` (ULID).

Dedup is **not** forced on `(entity, dimension, value)`.

```text
CAN_TWO_ASSERTIONS_HAVE_THE_SAME_ENTITY_DIMENSION_VALUE?
YES
```

when time, source, confidence, or observation context differ — or as repeated evidence. Do not over-deduplicate.

## Temporal / currentness / supersession

```text
temporal:     TemporalKnowledge (optional; unknown time allowed)
observed_at:  when assertion was recorded/known — not fact start
valid_from:   nullable; never auto-filled from created_at
valid_to:     nullable
is_current:   storage bookkeeping / preferred-assertion marker — NOT epistemic authority
supersedes_id: assertion lineage bookkeeping — does NOT imply correction vs evolution
```

- `"O Corolla é prata."` → unknown fact time remains unknown.
- `"O Corolla era preto."` → historical/non-current evidence + unknown calendar representable.
- `"Agora …"` → reuse existing temporal resolution; do not substitute `created_at` unless calendar resolved.

Correction vs evolution: future reason/metadata separate; same storage shape must allow both.

## Provenance (align State)

```text
source (required)
raw_input_id (nullable)
confidence (nullable/required per State convention at implement time)
created_at (row creation)
```

## User isolation

```text
attribute.user_id == entity.user_id
```

Repository must reject cross-user (same pattern as State).

## Delete behavior

State/Relation/Event entity FKs: **no ON DELETE CASCADE** today.  
Attribute v8: **RESTRICT / no cascade** — follow same integrity policy; do not orphan silently or cascade for convenience.

## Indexes (conceptual)

```text
(user_id, entity_id, dimension_key)
(user_id, entity_id, dimension_key, is_current)
(user_id, dimension_key)
# numeric query index deferred until Attribute query exists
```

## Query contract

```text
AttributeQuery: entity + dimension + temporal?
→ 0..N Attribute assertions
```

```text
0 rows ≠ entity lacks property (absence of knowledge ≠ knowledge of absence)
multiple current candidates → do not pick latest created_at as truth
historical values returned when temporal asks
```

## V8 conceptual schema (frozen — not implemented)

```text
EntityAttribute
├── id
├── user_id
├── entity_id
├── dimension_key              # required stable key
├── dimension_concept_id       # optional
├── value_kind                # text|number|year|date|concept
├── concept_value_id?         # when value_kind=concept
├── text_value?               # when value_kind=text
├── numeric_value?            # with unit when quantity
├── unit?                     # pairs with numeric_value
├── date_value?
├── year_value?
├── temporal_* / TemporalKnowledge payload fields
├── observed_at
├── valid_from?
├── valid_to?
├── is_current
├── supersedes_id?
├── source_id
├── raw_input_id?
├── confidence_*
└── created_at
```

Check constraint conceptually: exactly one value representation active per `value_kind`.

## Deferred work

```text
ATTRIBUTE-01       storage + materializer (v8 implementation)
ATTRIBUTE-QUERY-01 retrieval + current-value resolution (separate — justified)
MEASUREMENT-01     unchanged
ONTOLOGY-COVERAGE-01 wait on Attribute storage
```

## Explicit non-goals

v8 migration · ontology expansion · Correction Engine · event-derived Attribute transition · holdout · live
