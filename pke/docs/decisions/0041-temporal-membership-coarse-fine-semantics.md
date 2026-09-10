# ADR 0041 — Temporal Membership: Coarse/Fine Occurrence Windows (I11.16.2)

## Status

Accepted — **implemented**. Schema remains v9. CORE unchanged (65).

## Links

- Design freeze: ADR 0039
- Vocabulary: ADR 0040
- Prior unsafe NOW/TODAY: ADR 0038R

## Membership model

Canonical authority: `pke.temporal.membership.range_membership`.

Occurrence-window semantics (default `TemporalMembershipRole.OCCURRENCE_WINDOW`):

```text
fact_possible_window ⊆ query  → MATCH
fact_possible_window ∩ query = ∅ → NO_MATCH
otherwise → UNKNOWN
```

Half-open intervals `[start, end)`. Inclusive stored end-dates
(`occurrence_year` / `occurrence_month` / `calendar_occurrence`) convert to
exclusive end = end_date + 1 day.

Exact `INSTANT` / `TimePrecision.MINUTE` evidence: point ∈ query → MATCH/NO_MATCH
(no coarse UNKNOWN).

`TemporalMembershipRole.VALIDITY_INTERVAL` is **not** implemented in
`range_membership` (returns UNKNOWN). Relation validity stays in
`relation_lifecycle` / relation resolvers.

## Possible occurrence window ≠ continuous validity

Year/month/day/week bounds represent **where an occurrence may have happened**,
not that a fact is true at every instant in the window.

Therefore:

| Fact | Query | Result |
|------|-------|--------|
| YEAR 2024 | YEAR 2024 | MATCH |
| YEAR 2024 | JAN 2024 | UNKNOWN |
| YEAR 2024 | YEAR 2025 | NO_MATCH |
| MONTH Aug | day in Aug | UNKNOWN |
| DAY Aug-10 | Aug-10 14:32 | UNKNOWN |
| TODAY day | NOW instant | UNKNOWN |

## Runtime temporal role

- Not persisted (I11.16.1).
- Optional `role=` on `range_membership`; default OCCURRENCE_WINDOW.
- Primitive resolvers must not redefine coarse/fine rules.

## Event integration

QueryEngine partitions candidates via `range_membership`:

- MATCH → result items
- UNKNOWN → contributes `temporal_completeness=PARTIAL` / `temporal_membership_unknown`
- NO_MATCH → excluded

`_event_matches` preserves UNKNOWN (not MATCH-only).

## Measurement integration

`measurement_range_membership` continues to delegate to `range_membership`
(when `observed_at` absent). Coarse month observation → day query = UNKNOWN.

## Repository prefilter

Event/Measurement repositories remain retrieval-only. Membership runs in
resolvers/engine after load. No SQL range filter drops UNKNOWN candidates.

## Legacy PARTIAL

`TimePrecision.PARTIAL` is not membership authority. Relative/no-calendar →
calendar query = UNKNOWN. Bounds that independently prove disjointness may
still NO_MATCH.

## NOW / TODAY

Preserved: TODAY = calendar day; NOW = reference instant `[t, t+1µs)`.
Today-coarse evidence does not answer NOW.

## QueryResult completeness

Zero MATCH rows with UNKNOWN temporal contributors → PARTIAL, not complete NO.

## Known limitations

- Validity-interval membership not in shared API (Relation lifecycle deferred).
- Habitual/recurrence → UNKNOWN (no expansion).
- APPROX_DAY / DAY_PERIOD → UNKNOWN.
- Cross-primitive full lifecycle alignment remains TIME-01 cross-primitive work.

## Remaining TIME-01

```text
TIME-01 architecture   CLOSED
TIME-01 vocabulary     CLOSED
TIME-01 membership     CLOSED (I11.16.2)
TIME-01 persistence    CONDITIONAL
TIME-01 cross-primitive OPEN
```

## Recommendation

```text
I11.16.2_CLOSE_PROCEED_TO_CROSS_PRIMITIVE
```
