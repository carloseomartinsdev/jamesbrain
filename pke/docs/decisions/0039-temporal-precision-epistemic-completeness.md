# ADR 0039 — Temporal Precision & Epistemic Completeness (TIME-01 Design Freeze)

## Status

Accepted — **design frozen** (I11.16). No implementation in this increment.

## Context

Debt **TIME-01** (from I11.3 / generalization reevaluation):

> `TimePrecision.PARTIAL` mixes epistemic incompleteness with calendar coarseness (e.g. month).

After Measurement write/read closure and NOW≠TODAY fix (I11.15.3-R2), TIME-01 is the next temporal architecture gate.

## Actual current model (code)

Canonical domain: `src/pke/domain/temporal_knowledge.py`

```text
TemporalKnowledge
├── kind: TemporalKind
│     EXACT | RELATIVE | INTERVAL | PARTIAL | HABITUAL | UNKNOWN
├── calendar: TimeValue | None
│     └── TimeValue.precision: TimePrecision
│           DAY | MINUTE | APPROX_DAY | RECURRING | PERIOD | DAY_PERIOD | PARTIAL
├── relation_to_reference?
├── occurrence_status?
├── unknown_reason?
├── interval_start / interval_end?
├── granularity: TemporalGranularity
│     INSTANT | DAY | WEEK | MONTH | YEAR | INTERVAL | RECURRING | UNSPECIFIED
├── tense_evidence?
└── source_kind?
```

Query-side (not persisted fact time):

```text
IrQueryTime.relative_period: RelativePeriod
  THIS_MONTH | LAST_MONTH | THIS_WEEK | LAST_WEEK | TODAY | YESTERDAY | NOW
```

Authorities today:

| Component | Role |
|-----------|------|
| `TemporalResolver` | IrTime → TemporalKnowledge (ingest) |
| `QueryTemporalResolver` | IrQueryTime → AbsoluteRange (query) |
| `range_membership` | TemporalKnowledge × TimeRange → MATCH/NO_MATCH/UNKNOWN |
| `TimePrecision` | On TimeValue + DB `time_precision` + `calendar_precision()` bridge |

## Verdict: PARTIAL conflation is real

```text
IS_TIMEPRECISION_PARTIAL_CURRENTLY_CONFLATING_DISTINCT_TEMPORAL_SEMANTICS?
YES
```

Three distinct “partial” notions coexist:

1. **`TemporalKind.PARTIAL`** — relative/occurrence knowledge without calendar (e.g. `partial_past`, “já troquei”).
2. **`TimePrecision.PARTIAL`** — stored/default precision flag; also returned by `calendar_precision()` when `kind is PARTIAL` (bridges kind → precision).
3. **`TemporalCompleteness.PARTIAL`** (QueryResult) — incomplete query result set (unrelated enum).

Month-level facts are often **`TemporalKind.INTERVAL` + `TemporalGranularity.MONTH`**, not `TimePrecision.PARTIAL` — but audits/docs still label them under the PARTIAL debt, showing naming/authority confusion.

`TemporalKind.EXACT` + `TimePrecision.DAY` further conflates “exact calendar day representation” with “exact instant”.

## Architecture decision (clarified I11.16.1)

```text
SPLIT_PRECISION_FROM_EPISTEMIC_COMPLETENESS
persistence impact = CONDITIONAL
schema v10 = CONDITIONAL
```

Not “schema v10 required” and not “domain/wire-only guaranteed”.
Historical choice label **C** meant conditional persistence — corrected wording here
without rewriting audit evidence.

## Frozen principles (unchanged)

```text
fact time ≠ recorded_at / created_at
unknown membership ≠ false
NOW ≠ TODAY
latest ≠ current truth
termination known ≠ termination time known
LLM interprets; PKE reasons; storage persists
MATCH | NO_MATCH | UNKNOWN preserved
```

## Proposed canonical TemporalKnowledge (future)

Names frozen conceptually; types may adjust in implementation:

```text
TemporalKnowledge
├── temporal_form (kind)
│     UNKNOWN | RELATIVE | CALENDAR_OCCURRENCE | HABITUAL | VALIDITY_SPAN
├── calendar_granularity?
│     YEAR | MONTH | DAY | MINUTE | NONE | …
│     (asserted resolution — not storage fill)
├── calendar / bounds?
│     computational range derived from granularity (occurrence window)
├── temporal_role?
│     OCCURRENCE_WINDOW | VALIDITY_INTERVAL | OBSERVATION_SCOPE
├── relation_to_reference?
├── occurrence_status?
├── unknown_reason?
└── (no TimePrecision.PARTIAL)
```

### Field responsibilities

| Field | Responsibility | Persisted | Wire | Query-only |
|-------|----------------|-----------|------|------------|
| temporal_form | form of knowledge | yes | yes | no |
| calendar_granularity | asserted calendar coarseness | yes | yes | no |
| calendar/bounds | derived computational range | yes (as today) | optional | expansion may be query/ingest shared |
| temporal_role | occurrence vs validity vs observation | yes (new or mapped) | additive | no |
| relation_to_reference | ordering vs reference | yes | yes | no |
| occurrence_status | happened/ongoing/… | yes | yes | no |
| unknown_reason | why calendar missing | yes | yes | no |
| RelativePeriod | linguistic/query convenience | **no** | query IR | **yes** |

### TimePrecision future role

```text
DOES_TIMEPRECISION_REMAIN_CANONICAL?
PARTIALLY → calendar-only subset; NOT authority for epistemic incompleteness
```

Remove/deprecate `TimePrecision.PARTIAL`. Canonical authority = **`TemporalKnowledge`** (`temporal_form` + `calendar_granularity` + role).

### EXACT meaning (frozen)

```text
EXACT_INSTANT = evidence supports a point-in-time observation/event clock time
CALENDAR_OCCURRENCE at DAY/MONTH/YEAR = coarse occurrence window, NOT exact instant
Storage zeros (…:00.000000) ≠ semantic seconds/microseconds
```

## Occurrence window vs validity interval

```text
DOES_TEMPORAL_RANGE_CURRENTLY_MEAN
POSSIBLE_OCCURRENCE_WINDOW, VALIDITY_INTERVAL, OR BOTH?
BOTH — depending on context
```

- **Event / Measurement temporal + `range_membership`**: behaves as **occurrence / observation window**.
- **Relation/State `valid_from`/`valid_to`**: **lifecycle validity** (separate fields; relation_lifecycle forbids recorded_at as calendar endpoint).
- Risk: representing “em 2024” as `[2024-01-01, 2025-01-01)` must not imply continuous validity throughout 2024.

Future `temporal_role` makes this explicit.

## Membership semantics (T1–T10 design)

| Fact | Query | Result | Why |
|------|-------|--------|-----|
| T1 occurred in 2024 | in 2024? | MATCH | query granularity ≤ asserted year window, fully covers |
| T2 year 2024 | Jan 2024? | UNKNOWN | query finer than asserted granularity |
| T3 year 2024 | 2025? | NO_MATCH | disjoint windows |
| T4 Aug 2024 | Aug 10? | UNKNOWN | day finer than month |
| T5 Aug 2024 | September? | NO_MATCH | disjoint |
| T6 already occurred (no calendar) | already? | YES (existence) | relative/occurrence |
| T7 already occurred | in 2024? | UNKNOWN | no calendar |
| T8 historical relation | — | existence known; period unknown | |
| T9 terminated | exact end date? | UNKNOWN | termination ≠ time |
| T10 observed sometime yesterday | at 10:00 yesterday? | UNKNOWN | day ≠ minute |

Containment:

```text
definitely inside → MATCH
definitely outside → NO_MATCH
possible / underdetermined → UNKNOWN
```

## Legacy compatibility

```text
CAN_EXISTING_PERSISTED_PARTIAL_TIME_BE_MIGRATED_WITHOUT_INVENTING_SEMANTICS?
PARTIALLY
```

Safe:

- `temporal_kind=partial` + no calendar → relative/epistemic incomplete (already structured).
- `temporal_kind=interval` + granularity month/year → calendar occurrence at that granularity.
- `time_precision=partial` alone with empty calendar → treat as **unknown calendar / non-invented**.

Unsafe / forbidden:

```text
all PARTIAL → MONTH
all PARTIAL → EPISTEMIC_PARTIAL with finer invention
```

Constraint:

```text
TIME01_LEGACY_MIGRATION_REQUIRES_INVENTION
→ do not invent; leave UNKNOWN_LEGACY where evidence insufficient
```

## Schema impact

```text
WOULD_IMPLEMENTATION_REQUIRE_SCHEMA_V10?
CONDITIONAL
```

Prefer **reinterpret + deprecate `time_precision=partial` semantics** using existing `temporal_kind` / `temporal_granularity` columns.  
v10 only if additive `temporal_role` (or equivalent) is required for safe primitive distinction and cannot be soft-coded.

I11.16 itself: **schema remains v9, migration = none**.

## Wire impact

| Surface | Class |
|---------|-------|
| SemanticProposal / SemanticTime | ADDITIVE (granularity/role cues) |
| WireSemanticEnvelope | ADDITIVE |
| WireIngestIR / IrTime | ADDITIVE / COMPATIBILITY_ADAPTER |
| IngestIR | ADDITIVE |
| QueryIR / RelativePeriod | NONE required for TIME-01 core (NOW/TODAY already fixed) |
| ResolvedQuerySpec | NONE / ADDITIVE if membership gains granularity awareness |

## Primitive impact

| Primitive | Impact | Future change |
|-----------|--------|---------------|
| Event | High | occurrence-window membership by granularity |
| State | Medium | keep valid_* separate; observation temporal split |
| Relation | Medium | termination evidence temporal; no recorded_at endpoints |
| Attribute | Low–medium | historical property time as occurrence/assertion scope |
| Measurement | Medium | preserve observed_at exact-only; unknown time; NOW≠TODAY |

## Canonical authority

```text
WHAT_BECOMES_THE_CANONICAL_TEMPORAL_SEMANTIC_AUTHORITY?
TemporalKnowledge (+ TemporalResolver for write, shared membership for read)

QueryTemporalResolver remains query AbsoluteRange expansion only.
RelativePeriod remains query/linguistic — not persisted fact truth.
```

## Future implementation sequence

```text
I11.16.1  Domain/wire: deprecate TimePrecision.PARTIAL; freeze form/granularity/role vocabulary
I11.16.2  Membership: coarse→fine UNKNOWN; coarse→disjoint NO_MATCH (Event path first)
I11.16.3  Persistence reinterpret / additive v10 only if required; no invented backfill
I11.16-R  Cross-primitive revalidation + TIME benchmark (≥30 cases)
```

Do not merge State/Relation lifecycle redesign, Correction, or recurrence expansion into TIME-01.

## Rejected alternatives

| Alternative | Why rejected |
|-------------|--------------|
| Keep PARTIAL as-is | Documented collision; unsafe membership risk |
| Giant temporal logic / theorem prover | Out of PKE scope |
| Boolean explosion (is_partial, is_exact, …) | Orthogonal typed fields preferred |
| Combined mega-enums | Loses orthogonality |
| Freshness / current_value in TIME-01 | Separate debts; Measurement currentness frozen out |
| Silent year attach for “em agosto” | Only with explicit existing policy |

## Safety metrics (future)

```text
COARSE_TIME_RETURNED_AS_EXACT
POSSIBLE_MEMBERSHIP_RETURNED_AS_MATCH
POSSIBLE_MEMBERSHIP_RETURNED_AS_NO_MATCH
RECORDED_AT_USED_AS_FACT_TIME
STORAGE_PRECISION_USED_AS_SEMANTIC_PRECISION
RELATIVE_TIME_FORCED_TO_CALENDAR
OCCURRENCE_WINDOW_TREATED_AS_VALIDITY_INTERVAL
NOW_COLLAPSED_TO_TODAY
LEGACY_TIME_SEMANTICS_INVENTED
```

Target: all = 0.

## Recommendation

```text
I11.16_CLOSE_PROCEED_TO_TEMPORAL_IMPLEMENTATION
```
