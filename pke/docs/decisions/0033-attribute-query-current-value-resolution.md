# ADR 0033 — Attribute Query & Current-Value Resolution (I11.13)

## Status

Accepted — closes `ATTRIBUTE-QUERY-01`.

## Context

I11.12.2 persisted `EntityAttribute` (schema v8). READ had no first-class Attribute path; Event/State/Relation queries must not be overloaded.

## Decision

### Query intent

```text
QuerySpec.intent = "attribute"
QuerySpec.attribute_query_mode ∈ {value_lookup, proposition, historical_existence}
```

Distinct from Event `list`/`aggregate`, State `state`, Relation `relation`.

### Pipeline

```text
NL → SemanticProposal → PrimitiveRouter(ATTRIBUTE)
  → resolve_query_proposal → QueryIR(intent=attribute)
  → ResolvedQueryBuilder → ResolvedQuerySpec
  → QueryEngine._execute_attribute
  → AttributeResolver (epistemic)
  → QueryResult(attribute_*)
```

### Dimension resolution

WRITE and READ share `attribute_resolution.resolve_attribute_dimension_key` /
`resolve_attribute_value` plus controlled static aliases (`cor`→`color`, …).
No adaptive alias learning. No second vocabulary.

### Repository vs resolver

- Repository / snapshot: retrieval of candidate `EntityAttribute` rows only
  (`for_entity_dimension` / `list_by_entity_dimension`).
- `AttributeResolver`: value grouping, currentness bookkeeping participation,
  temporal membership ternary, resolution status.
- `created_at` is never epistemic current-value authority.

### Value grouping

Assertion identity ≠ semantic value identity. Equality by `value_kind`:
text (stored normalized), number+unit (exact; no conversion), year, date, concept id.

Repeated equal evidence → one resolved value with `support_count > 1`.

### Current-value semantics

`is_current` is storage bookkeeping evidence, not absolute truth.
Multiple distinct current values → `AMBIGUOUS` (no arbitrary winner).
No current markers → `TEMPORALLY_UNKNOWN` (safer than guessing).

### Temporal unknown

Reuse `TemporalMembership` MATCH | NO_MATCH | UNKNOWN.
Historical existence without calendar may be YES.
Membership in an arbitrary year without calendar evidence → `TEMPORALLY_UNKNOWN`, not YES.

### Proposition truth

Answers: `yes` | `unknown` | `ambiguous` | `temporally_unknown`.
`no` is **not** inferred for generic dimensions — functional cardinality deferred
(`ATTRIBUTE_CARDINALITY` not introduced as debt unless required later).

### Primitive boundaries

TYPE / State / Relation / Event query routing unchanged and non-Attribute.
No Event→Attribute enrichment on read. Query is read-only.

### Deferred

- Unit conversion engine (`MEASUREMENT-01`)
- Functional dimension metadata
- Adaptive aliases / Interpreter retry
- TIME-01 calendar model itself

## Consequences

```text
ATTRIBUTE-QUERY-01     CLOSED
SEMANTIC-QUERY-01      residual (broader NL coverage)
TIME-01                OPEN
schema                 remains v8
CORE                   65 (unchanged)
```
