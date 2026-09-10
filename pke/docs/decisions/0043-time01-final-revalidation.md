# ADR 0043 — TIME-01 Final Cross-Primitive Temporal Revalidation (I11.16-R)

## Status

Accepted — **TIME-01 CLOSED**. Schema remains v9. CORE = 65. No new capability.

## History

| Increment | Focus | ADR |
|-----------|-------|-----|
| I11.16 | Design freeze | 0039 |
| I11.16.1 | Vocabulary / authority | 0040 |
| I11.16.2 | Coarse/fine membership | 0041 |
| I11.16.3 | Cross-primitive roles | 0042 |
| I11.16-R | Final revalidation | 0043 |

## Final temporal model

```text
calendar granularity  ≠  epistemic incompleteness
storage precision     ≠  semantic precision
occurrence window     ≠  continuous validity
observation scope     ≠  current truth
assertion scope       ≠  continuous validity
NOW                   ≠  TODAY
latest observation    ≠  current value
unknown membership    ≠  false
recorded_at/created_at ≠ fact time
```

## Authority map

| Responsibility | Canonical authority |
|----------------|---------------------|
| temporal container | `TemporalKnowledge` |
| calendar granularity | `TemporalKnowledge.calendar_granularity()` / `TemporalGranularity` |
| temporal form | `TemporalKind` |
| relative relation | `relation_to_reference` |
| occurrence status | `OccurrenceStatus` |
| membership | `range_membership` + `validity_interval_membership` |
| temporal role | `derive_temporal_membership_role` (runtime, not persisted) |
| query relative expansion | `QueryTemporalResolver` |
| legacy precision | `TimePrecision` / `legacy_time_precision()` |

`TimePrecision.PARTIAL` = compatibility only — zero canonical authority.

## Cross-primitive roles

| Primitive | Role(s) | Query semantics |
|-----------|---------|-----------------|
| Event | OCCURRENCE_WINDOW | coarse containment |
| Measurement | OBSERVATION_SCOPE | observation membership; latest ≠ current |
| Relation | VALIDITY_INTERVAL (`valid_*`) | `held_during` = VALID_THROUGHOUT(query) |
| State | OBSERVATION / VALIDITY by field | StateResolver = currentness authority |
| Attribute | ASSERTION_SCOPE | coarse assertion ≠ continuous validity |

## Persistence result

```text
CAN_V9_PERSIST_ALL_CURRENT_TIME01_SEMANTICS? YES
IS_SCHEMA_V10_REQUIRED_FOR_TIME01? NO
IS_PERSISTED_TEMPORAL_ROLE_REQUIRED? NO
```

Role reconstructed after reload from `(primitive, field_path)`.

## Query limitations

```text
SUPPORTED:
  RelationQueryKind CURRENT_BOOLEAN | HISTORICAL_EXISTENCE | TERMINATION_DATE | HELD_DURING
  Event/Measurement/Attribute range membership via TimeRange
  Measurement modes (latest / at_time / in_range / proposition)
  QueryTemporalResolver NOW / TODAY / week / month relatives

UNSUPPORTED (abstain safely → UNKNOWN):
  EXISTS_DURING as overlap-MATCH distinct from VALID_THROUGHOUT
  explicit VALID_THROUGHOUT flag separate from held_during
  recurrence expansion, open-interval algebra, fuzzy/probabilistic time
```

Unsupported intents do **not** block TIME-01 closure: supported paths remain safe.

## Relation held_during contract

```text
held_during ≡ VALID_THROUGHOUT(query_range)
MATCH  ↔ validity covers full query
NO_MATCH ↔ disjoint
UNKNOWN ↔ partial overlap or incomplete endpoints
```

Not silent overlap-as-MATCH.

## Closure

```text
TIME-01 architecture     CLOSED
TIME-01 vocabulary       CLOSED
TIME-01 membership       CLOSED
TIME-01 cross-primitive  CLOSED
TIME-01 persistence      CLOSED / NOT REQUIRED
TIME-01                  CLOSED
```

## Remaining non-TIME debts (out of scope)

Correction Engine, Measurement analytics/current_value, Attribute current-value redesign,
State lifecycle redesign, recurrence/open-interval engines, clarification UX.

## Recommendation

```text
TIME01_CLOSE
```
