# ADR 0015 — Partial Temporal Knowledge (I11.3)

**Status:** Accepted  
**Date:** 2026-09-02  
**Supersedes:** Partial aspects of ADR 0014 (blocking on all missing calendar time)

## Context

ADR 0014 required resolvable calendar time for all materialized events. Real usage shows valid past events without calendar anchors (*"Troquei a embreagem"*) and explicit temporal uncertainty (*"não lembro quando"*).

`Event.time = None` is insufficient: it conflates wire omission, unprocessed state, not_provided, forgotten, and partial knowledge.

## Decision

Introduce **`TemporalKnowledge`** as the canonical temporal representation on `Event.temporal`:

| Kind | Meaning |
|------|---------|
| EXACT / RELATIVE | Calendar-resolved `TimeValue` in `calendar` |
| INTERVAL | Partial month/year bounds |
| PARTIAL | Relation to reference without calendar |
| HABITUAL | Recurrence pattern |
| UNKNOWN | No temporal semantics |

Persistable when `has_calendar_anchor()` **or** `PARTIAL` with explicit `relation_to_reference`.

### Principles frozen

- `valid knowledge ≠ complete knowledge`
- `missing calendar time ≠ invalid event`
- `recorded_at ≠ event time`
- `linguistic evidence ≠ absolute calendar time`
- `unknown temporal membership ≠ false membership`
- `enrichment ≠ correction`

### Query semantics

`range_membership(temporal, time_range) → MATCH | NO_MATCH | UNKNOWN`

- Existential queries (no period filter): partial events participate
- Period filters: UNKNOWN events are not silently included or excluded as certainty
- Aggregates expose `temporal_completeness`, `unknown_temporal_contributors`, `latest_known_*`

### Storage

Schema v2 adds `temporal_*` columns on `events`. Migration `v1_to_v2` preserves existing calendar columns; `temporal_kind='exact'` for legacy rows.

## Alternatives considered

1. **Nullable `Event.time`** — rejected (insufficient semantics)
2. **Separate atemporal events table** — rejected (splits episodic model)
3. **Infer `today` from tense** — rejected (forbidden inference)

## Consequences

- `KnowledgeCandidate.resolved_temporal` replaces direct `resolved_time` assignment
- `CompletenessEngine`: TIME essential = persistable temporal, not calendar-only
- D2 case commits as temporally incomplete (not `time.missing` block)
- QueryEngine uses ternary temporal logic

## Migration

- Version: `1` → `2`
- Script: `pke/persist/migrations/v1_to_v2.py`
- Alembic: `alembic/versions/001_storage_v2_temporal_knowledge.py` (reference)

## Enrichment compatibility

`TemporalKnowledge` fields are enrichable in future I11.7 without correction semantics (e.g. add `interval_start` to partial past event).

## recorded_at separation

`Event.created_at` / `recorded_at` never used as fact time in query filters — protected by `test_recorded_at_is_distinct_from_event_time`.
