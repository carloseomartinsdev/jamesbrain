# ADR 0042 — Cross-Primitive Temporal Role & Query Semantics (I11.16.3)

## Status

Accepted — **implemented / revalidated**. Schema remains v9. CORE = 65.

## Links

- Design: ADR 0039
- Vocabulary: ADR 0040
- Membership: ADR 0041

## Runtime temporal roles

| Role | Meaning | Algebra |
|------|---------|---------|
| `OCCURRENCE_WINDOW` | Event sometime in F | F ⊆ Q / disjoint / else UNKNOWN |
| `OBSERVATION_SCOPE` | Measurement/State observation in F | same coarse-window algebra |
| `ASSERTION_SCOPE` | Attribute assertion in F | same coarse-window algebra |
| `VALIDITY_INTERVAL` | Relation/State valid_* covers Q | Q ⊆ validity / disjoint / else UNKNOWN |

Roles are **not persisted**. Derived by:

```text
derive_temporal_membership_role(primitive, field_path)
```

Reconstructible after DB reload from primitive + field path alone.

## Role derivation

```text
event.temporal              → OCCURRENCE_WINDOW
measurement.temporal        → OBSERVATION_SCOPE
measurement.observed_at     → OBSERVATION_SCOPE
attribute.temporal          → ASSERTION_SCOPE
relation.valid_from/to      → VALIDITY_INTERVAL
relation.temporal           → VALIDITY_INTERVAL (validity evidence path)
relation.termination_temporal → OBSERVATION_SCOPE
state.temporal              → OBSERVATION_SCOPE
state.valid_from/to         → VALIDITY_INTERVAL
```

Never inferred from range shape alone.

## Primitive semantics

| Primitive | Role(s) | Membership authority |
|-----------|---------|----------------------|
| Event | OCCURRENCE_WINDOW | `range_membership(..., role=OCCURRENCE_WINDOW)` |
| Measurement | OBSERVATION_SCOPE | `measurement_range_membership` → shared `range_membership` |
| Relation | VALIDITY_INTERVAL | `relation_held_during` → `validity_interval_membership` |
| State | OBSERVATION / VALIDITY (by field) | StateResolver for currentness; observation uses coarse-window |
| Attribute | ASSERTION_SCOPE | `range_membership(..., role=ASSERTION_SCOPE)` |

## Validity vs occurrence

Year fact as **occurrence** vs January query → UNKNOWN.
Same bounds as **validity** covering January → MATCH.

Partial validity overlap (Jan–Jun vs May–Aug) → UNKNOWN
(QueryIR does not distinguish EXISTS_DURING vs VALID_THROUGHOUT).

## Query-intent limitations

```text
EXISTS_DURING / VALID_THROUGHOUT / AT_TIME
```

Relation exposes `held_during` only. Distinction **PARTIALLY** supported via safe
VALID_THROUGHOUT MATCH + UNKNOWN on partial overlap. No QueryIR redesign in this increment.

```text
IS_THIS_DISTINCTION_REQUIRED_NOW? PARTIALLY
```

## Repository filtering

No SQL temporal prefilter drops UNKNOWN candidates. Graph load → resolver membership.

## Persistence decision

```text
IS_PERSISTED_TEMPORAL_ROLE_NEEDED? NO
schema v10 remains unnecessary for TIME-01 role semantics
```

## Remaining TIME-01

```text
TIME-01 architecture     CLOSED
TIME-01 vocabulary       CLOSED
TIME-01 membership       CLOSED
TIME-01 cross-primitive  CLOSED (I11.16.3)
TIME-01 persistence      CONDITIONAL (no v10 for roles)
```

Next: TIME-01 revalidation / I11.16-R (not started).

## Recommendation

```text
I11.16.3_CLOSE_PROCEED_TO_TIME01_REVALIDATION
```
