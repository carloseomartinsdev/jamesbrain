# ADR 0035 — Measurement Primitive & Quantitative Observation Design (I11.15)

## Status

Accepted — **design freeze**. Storage / `PrimitiveKind.MEASUREMENT` / schema v9 **not** implemented.

## Decision

```text
IS_MEASUREMENT_A_DISTINCT_FIRST_CLASS_KNOWLEDGE_PRIMITIVE?
YES
```

```text
Recommendation:
PROCEED_TO_MEASUREMENT_IMPLEMENTATION_DESIGN_FREEZE
```

First-class Measurement is justified: recurring, cross-domain, structurally distinct from
Attribute/State/Event, temporally historical, and query-relevant. Current State
`observed_quantity` provisional routing is an incomplete stand-in.

## Definition

```text
Measurement
= an observed quantitative value
  of a measurable dimension
  associated with an entity (and optional context)
  under a temporal observation scope
```

Not:

```text
number + unit ⇒ Measurement
```

Semantic role decides; mutability and syntax do not.

## Boundaries

### vs Attribute (FROZEN)

| Attribute | Measurement |
|---|---|
| descriptive property of what something is/has | recorded observation of a quantity |
| capacity, height, weight, area, model_year, rent amount | fuel level, battery %, odometer, temperature, balance reading |

### vs State (FROZEN)

| State | Measurement |
|---|---|
| world condition in a state dimension | quantitative observation |
| battery depleted / motor overheated / tank full | battery 80% / motor 95°C / tank 20 L |

Composition allowed later (not implemented):

```text
Measurement(battery_charge=0%) + State(depleted)
```

No automatic derivation either direction.

### vs Event (FROZEN)

| Event | Measurement |
|---|---|
| occurrence / act | observation result |
| “Medi a temperatura.” | “Estava em 95°C.” |

Same utterance may assert **both** when both are linguistically present
(`Medi … e deu 95°C`) — multi-primitive assertion, not Knowledge Enrichment.
Enrichment Event→Measurement without stated value remains forbidden.

### vs Relation

Ownership fractions (`possui 50%`) stay Relation metadata — not Measurement.

### Monetary

| Utterance | Primitive |
|---|---|
| aluguel é R$ 550 | Attribute (contractual) |
| paguei R$ 550 | Event (payment quantity) |
| conta veio R$ 550 | Attribute (document amount) |
| saldo é R$ 2500 | Measurement (reported balance observation) |
| Corolla custou R$ 80 mil | Event (acquisition value) |

## Alternatives rejected

| Option | Verdict |
|---|---|
| A — keep as State observed_quantity | Rejected — destroys observation identity/history/query meaning |
| C — Attribute temporal observations | Rejected — reopens Attribute=descriptive freeze |
| D — generic Observation/Evidence | Too broad for this debt; Measurement sufficient for quantitative pattern |
| B — first-class Measurement | **Accepted** |

Not `MEASUREMENT_MODEL_TOO_NARROW`: quantitative observation is the recurring class.

## Conceptual model (freeze for next implementation)

```text
Measurement
├── id
├── user_id
├── entity_id                 # primary measured entity
├── context_entity_id?       # e.g. Corolla for tank; room for temperature
├── dimension_key            # required (fuel_level, battery_charge, …)
├── dimension_concept_id?    # optional — no CORE explosion
├── numeric_value            # Decimal
├── unit?                    # canonical string (L, km, °C, %, …)
├── currency_code?           # separate from unit when monetary (BRL, USD)
├── temporal                 # TemporalKnowledge — observation/measurement time
├── observed_at              # operational clock when asserted
├── source_id
├── raw_input_id?
├── confidence               # interpretation confidence ≠ instrument error
└── created_at               # storage bookkeeping ONLY
```

### Chronology / currentness

```text
created_at ≠ measurement time
is_current: NO (not inherited from Attribute)
new observation does NOT supersede prior observations
identical value at T1 and T2 = two distinct Measurements
latest observation ≠ guaranteed current truth
unknown observation time remains UNKNOWN (no fabricated sort)
```

### Percentage

```text
store 80 + unit=%
do NOT silently normalize to 0.80
```

### Units

Controlled canonical strings initially. No general conversion. Currency via `currency_code`.

## Router / proposal (future)

```text
IS_PRIMITIVE_KIND_MEASUREMENT_REQUIRED? YES (next implementation)
CAN_CURRENT_SEMANTIC_PROPOSAL_EXPRESS_MEASUREMENT_FAITHFULLY? PARTIALLY
```

Minimum future proposal extensions (not done here):

```text
measurement_semantics: bool
quantity_expression / numeric + unit + currency
measurable_dimension cue
```

Today Measurement candidates often use `condition_semantics` + `state_expression` and
route as STATE — acceptable provisional, not final.

## Schema

```text
DOES_FIRST_CLASS_MEASUREMENT_REQUIRE_SCHEMA_V9? YES
IS_SCHEMA_V9_IMPLEMENTATION_AUTHORIZED? NO
schema remains v8 this increment
CORE remains 65
```

## Deferred

- Measurement storage / migration v9
- `PrimitiveKind.MEASUREMENT` enum + router
- query modes (latest_observation, at_time, range)
- State/Attribute/Event derivation
- instrument uncertainty
- unit conversion / FX

## Debt

```text
MEASUREMENT-01 → DESIGN_FROZEN (ready for storage implementation increment)
TIME-01        → UNCHANGED / still OPEN (measurement uses TemporalKnowledge)
```
