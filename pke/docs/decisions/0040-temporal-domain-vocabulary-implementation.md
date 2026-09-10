# ADR 0040 — Temporal Domain Vocabulary & Canonical Authority (I11.16.1)

## Status

Accepted — **implemented** (domain/wire/authority cleanup). Schema remains v9.

## Links

- Design freeze: ADR 0039
- Clarified architecture: `SPLIT_PRECISION…` with **CONDITIONAL** persistence (not forced v10)

## Canonical authorities

| Concept | Authority |
|---------|-----------|
| Temporal form | `TemporalKind` (PARTIAL = relative/no-calendar) |
| Calendar resolution | `TemporalKnowledge.calendar_granularity()` → `TemporalGranularity` YEAR/MONTH/DAY/WEEK/INSTANT |
| Occurrence status | `OccurrenceStatus` |
| Relation to reference | `RelationToReference` |
| Query RelativePeriod | query/linguistic only (NOW/TODAY preserved) |
| Query completeness | `TemporalCompleteness` (QueryResult) |
| TimePrecision | TimeValue + **v9 LEGACY persistence** only |

## TimePrecision.PARTIAL

```text
CANONICAL new emission: forbidden (use TemporalKind.PARTIAL / granularity=None)
LEGACY_WRITE: relative/unknown rows still persist time_precision=partial
LEGACY_READ: load without inventing YEAR/MONTH/DAY
```

`calendar_precision()` now delegates to `legacy_time_precision()` (compat).

## Constructors

```text
occurrence_year / occurrence_month / calendar_occurrence
partial_past / partial_future / partial_ongoing
from_calendar (sets granularity from TimeValue.precision when possible)
```

Month/year are **INTERVAL + granularity**, not epistemic PARTIAL.

## temporal_role

```text
IS_TEMPORAL_ROLE_REQUIRED_IN_PERSISTENCE? NO (for I11.16.1)
```

Role remains derivable from owning primitive/fields (Event occurrence, Measurement observation, Relation valid_*). Deferred to I11.16.3 review if needed.

## V9 capacity

```text
V9_CAN_PERSIST_NEW_TEMPORAL_VOCABULARY = YES
```

via existing `temporal_kind` + `temporal_granularity` + interval columns; `time_precision` PERIOD for year/month, PARTIAL only for no-calendar.

## Remaining TIME-01

```text
TIME-01 architecture   CLOSED
TIME-01 vocabulary     CLOSED
TIME-01 membership     OPEN (I11.16.2)
TIME-01 persistence    CONDITIONAL (v10 only if role must persist)
TIME-01 cross-primitive OPEN
```

## Recommendation

```text
I11.16.1_CLOSE_PROCEED_TO_MEMBERSHIP
```
