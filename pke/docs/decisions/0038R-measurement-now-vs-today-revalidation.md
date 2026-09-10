# ADR 0038R — Measurement NOW vs TODAY (audit + R2 fix)

## Status

**Corrected** — I11.15.3-R2.

Audit I11.15.3-R found `MEASUREMENT_NOW_TODAY_COLLAPSE`. This ADR preserves that
evidence and documents the fix.

## Confirmed defect (I11.15.3-R)

```text
“agora”
→ observation_at_time
→ RelativePeriod.TODAY
→ [hoje 00:00, amanhã 00:00)
→ Measurement membership
```

Classification was **B** (calendar-day interval). Earlier-today observations
could answer NOW queries.

## Root cause

Collapse at semantic query resolution / IrQueryTime mapping:

```text
query_resolution._temporal_query / NOW fallback
→ RelativePeriod.TODAY
```

not at TemporalKnowledge persistence, repository, or MeasurementResolver
membership logic itself.

## Fix (I11.15.3-R2)

```text
“agora” / neste momento / no momento / atualmente
→ RelativePeriod.NOW
→ QueryTemporalResolver
→ AbsoluteRange [reference_at, reference_at + 1µs)
→ observation_at_time membership
```

```text
“hoje”
→ RelativePeriod.TODAY
→ [start_of_today, start_of_tomorrow)
```

NOW uses existing IrQueryTime `relative_period` pattern (parallel to TODAY).
No TemporalKnowledge domain extension. No TIME-01 redesign.
No `current_value`. No freshness/TTL heuristic.

## Why not current_value / freshness

NOW remains `observation_at_time` with present-instant scope.
Exact temporal evidence at reference may MATCH; earlier-today does not.
No product TTL policy.

## MeasurementResolver

Unchanged epistemic role: MATCH / NO_MATCH / UNKNOWN over supplied TimeRange.
Does not invent clocks or current-state policy.

## Traceability

I11.15.3-R audit tests originally documented collapse metrics = 1.
I11.15.3-R2 replaces those assertions with safe expectations (metrics = 0).

## Recommendation after fix

```text
I11.15.3_CLOSE
```

(pending full suite green)
