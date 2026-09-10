# ADR 0036 — Measurement Routing, Multi-Primitive Semantics & v9 Storage Contract (I11.15.1)

## Status

Accepted — **contract freeze**. Schema v9 / Measurement persistence **not** implemented.

## Decision

```text
IS_MEASUREMENT_ROUTING_AND_V9_STORAGE_CONTRACT_FROZEN?
YES

Recommendation:
PROCEED_TO_MEASUREMENT_V9_IMPLEMENTATION
```

## PrimitiveKind.MEASUREMENT

```text
IMPLEMENTED = YES (enum + routing + resolve + persistability deny)
ROUTING_ONLY_AT_THIS_STAGE = YES
materialization = blocked until schema v9
```

## Routing evidence

```text
measurement_semantics = true
(+ optional measurable_dimension_key / measurement_numeric_value / unit / currency)
```

**Not** used:

```text
number present → Measurement
unit present → Measurement
```

Attribute quantities keep `stable_property_semantics`.

Mandatory contrasts: MR1–MR6 → non-Measurement; MR7–MR10 → MEASUREMENT;
MR11 balance → MEASUREMENT; MR12 count → MEASUREMENT when measurement_semantics;
MR13–MR15 → STATE; MR16–MR17 → EVENT (act without result).

## Multi-primitive assertion

```text
MULTI_PRIMITIVE_ASSERTION ≠ KNOWLEDGE_ENRICHMENT
```

Mechanism (Option A+D hybrid — additive, no broad rewrite):

```text
SemanticProposal (utterance transport, backward compatible)
collect_assertions(proposal) → list[SemanticAssertionFrame]
  each: primitive, confidence, notes
ResolutionResult.assertions + non_materialized_primitives
```

Event+Measurement when both occurrence and measurement evidence are explicit.
List order ≠ epistemic priority (no primary/secondary epistemic ranking).

MP decisions:

| Case | Outcome |
|---|---|
| MP1 Medi…95°C | EVENT + MEASUREMENT |
| MP2 Olhei tanque…20L | EVENT + MEASUREMENT (observe act + reading) |
| MP3 Pesei…10kg | EVENT + MEASUREMENT |
| MP4 Consultei saldo… | EVENT + MEASUREMENT |
| MP5 Sensor mediu 38°C | MEASUREMENT only (instrument reading, not user measure act) |

Partial materialization policy:

```text
COMMIT_VALID_INDEPENDENTLY
```

Independent candidates: Event may commit today; Measurement stays in
`non_materialized_primitives` until v9. Malformed Measurement must not
corrupt Event. Same `raw_input` / source provenance for all assertions.

Confidence: assertion-level preferred (`assertion_confidence` map);
utterance-level `confidence` remains fallback.

## SemanticProposal / Wire

```text
CAN_REPRESENT_SINGLE_MEASUREMENT? YES (measurement_* fields)
CAN_REPRESENT_EVENT_PLUS_MEASUREMENT? YES via assertions[] (no loss at semantic layer)
```

Additive fields: `measurement_semantics`, `measurement_expression`,
`measurable_dimension_key`, `measurement_numeric_value`, `measurement_unit`,
`measurement_currency_code`, `context`, `assertion_confidence`.

Wire: same fields on `WireSemanticProposal` — additive, backward compatible.
LLM proposes evidence; PKE owns routing/materialization.

## Entity / context

```text
OPTION B (materialization rule): entity_id REQUIRED to materialize
entity-less ambient readings remain semantically valid but non-materializable
context_entity_id OPTIONAL (tank↔vehicle, temp↔room)
measured entity ≠ context entity
no EventParticipant clone; no fabricated Environment entity
```

## Dimension / numeric / unit / currency

```text
dimension_key REQUIRED (semantic meaning: temperature, battery_charge, …)
dimension_concept_id OPTIONAL (CORE need not expand)
numeric_value: Decimal domain; DB DecimalAsText (reuse Attribute v8)
unit XOR currency_code (no coexistence)
80% → numeric_value=80, unit="%"
currency_code ISO-like (BRL); not unit="R$"
dimensionless count: unit=NULL, currency=NULL allowed
```

## Temporal

```text
TemporalKnowledge for observation scope (partial/relative/unknown OK)
observed_at? exact instant when known
created_at = record creation ONLY — never observation-time fallback
unknown observation time remains UNKNOWN
chronology: only by known observation times — never created_at/id
no is_current; no ordinary supersession
latest observation ≠ current truth
```

## Identity / history

```text
canonical identity = measurement id (observation-level)
0..N per entity/dimension
same value different times = distinct
no unique(entity, dimension, value)
```

## V9 Measurement model (frozen)

```text
Measurement
├── id
├── user_id
├── entity_id              # required for materialization
├── context_entity_id?     # optional context
├── dimension_key          # required (not a unit string)
├── dimension_concept_id?
├── numeric_value          # Decimal (DB: DecimalAsText)
├── unit?                  # XOR currency_code
├── currency_code?
├── temporal               # TemporalKnowledge
├── observed_at?
├── source_id
├── raw_input_id?
├── confidence             # interpretation ≠ instrument error
└── created_at             # bookkeeping ONLY
```

Table: `measurements`. No cascade convenience from Entity.
User isolation: measurement.user_id == entity/context.user_id at repository.

FKs/CHECKs/indexes: see `measurement_contract.py` FUTURE_* constants.
No precision/error metadata in base contract.

## Legacy / migration

```text
NO_BACKFILL of State observed_quantity → Measurement
(legacy rows lack safe Measurement-vs-Attribute/State evidence)
Python runner sole migration authority when v9 later authorized
Alembic non-authoritative
fresh v9 == migrated v8→v9 (requirement for future implementer)
```

## Future query (preview only)

```text
modes: latest_observation | observation_at_time | observations_in_range | proposition
no rows ≠ false; latest ≠ current truth
no aggregation / unit conversion / derived State|Attribute|Event
```

## Schema this increment

```text
schema = v8 (unchanged)
migration = none
CORE = 65
SCHEMA_V9_AUTHORIZED = False (storage implementation is next increment)
```

## Authority

`src/pke/interpretation/semantic/measurement_contract.py`
