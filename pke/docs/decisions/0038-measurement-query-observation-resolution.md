# ADR 0038 — Measurement Query & Observation Resolution (I11.15.3)

## Status

Accepted — **implemented**.

## Decision

```text
IS_MEASUREMENT_NOW_FIRST_CLASS_QUERYABLE_KNOWLEDGE?
YES

Recommendation:
I11.15.3_CLOSE
```

## Pipeline

```text
Natural Language
→ SemanticProposal
→ PrimitiveRouter (MEASUREMENT)
→ query_resolution._resolve_measurement_query
→ QueryIR (intent=measurement)
→ ResolvedQueryBuilder
→ ResolvedQuerySpec
→ QueryEngine._execute_measurement
→ MeasurementResolver
→ QueryResult
```

## Query modes

| Mode | Status |
|------|--------|
| `latest_observation` | IMPLEMENTED |
| `observation_at_time` | IMPLEMENTED |
| `observations_in_range` | IMPLEMENTED |
| `value_proposition` | IMPLEMENTED |

`current_value` is **not** implemented. Current-language (“agora”) maps to
`observation_at_time` with today’s range — never to silent latest-as-current.

## Epistemic authority

```text
SqlMeasurementRepository / read store  → retrieval only
MeasurementResolver                    → temporal membership, ordering,
                                         value grouping, ambiguity,
                                         proposition truth, completeness
```

Repository must NOT decide latest/current truth, proposition truth, or
treat temporal UNKNOWN as false.

## Latest ≠ current

```text
latest_observation = chronologically maximal known observation
  among observations with usable temporal ordering

DOES_LATEST_OBSERVATION_MEAN_CURRENT_TRUTH?
NO
```

Unknown-time observations coexisting with known-time rows → `ambiguous`
(block definitive latest). `created_at` / row id never used as chronology.

## Temporal membership

```text
MATCH | NO_MATCH | UNKNOWN
```

Uses `observed_at` when exact; else `TemporalKnowledge` via `range_membership`.
UNKNOWN contributors appear in range metadata; never converted to false/NO.

## Value proposition

Public answers: `yes` | `unknown` | `ambiguous` | `temporally_unknown`.

```text
no rows ≠ NO
unit incomparability ≠ NO (no conversion)
```

## Result statuses

```text
known_single | known_multiple | unknown | temporally_unknown | ambiguous
```

## Comparison

- Decimal equality (no float)
- Percentage remains `80` + unit `%`
- Currency via `currency_code` (no FX)
- Unequal units → incomparable / unknown

## Explicitly deferred

Aggregation, unit/FX conversion, current-value freshness heuristics,
Measurement↔State/Event derivation, Correction Engine, Clarification,
Observation super-primitive, analytics.

## Schema / ontology

```text
schema before = v9
schema after  = v9
migration     = none
CORE          = 65 (unchanged)
```

## Debt

```text
Measurement semantic design  CLOSED
Measurement routing          CLOSED
Measurement storage          CLOSED
Measurement query            CLOSED
Measurement analytics        NOT STARTED

MEASUREMENT-01               CLOSED (base write/read capable)
TIME-01                      OPEN
SEMANTIC-QUERY-01            residual (non-Measurement)
ONTOLOGY-COVERAGE-01         OPEN/reduced
CORRECTION_ENGINE_DEBT       OPEN
```
