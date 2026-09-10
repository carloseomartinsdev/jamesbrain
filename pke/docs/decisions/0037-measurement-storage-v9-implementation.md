# ADR 0037 — Measurement Storage Schema v9 Implementation (I11.15.2)

## Status

Accepted — **implemented**.

## Decision

```text
IS_MEASUREMENT_NOW_FIRST_CLASS_PERSISTED_KNOWLEDGE?
YES

Recommendation:
I11.15.2_CLOSE
```

## Schema

```text
schema before = v8
schema after = v9
migration = v8→v9 (Python runner sole authority)
NO semantic backfill of State observed_quantity
fresh v9 == migrated v8→v9
```

## Canonical source

```text
domain: pke.domain.measurements.Measurement
table: measurements
repository: SqlMeasurementRepository / MeasurementRepository
materializer: KnowledgeMaterializer._measurement
```

## Model

```text
Measurement
├── id, user_id
├── entity_id (required for materialization)
├── context_entity_id?
├── dimension_key (required)
├── dimension_concept_id?
├── numeric_value (Decimal / DecimalAsText)
├── unit? XOR currency_code?
├── temporal (TemporalKnowledge columns)
├── observed_at? (exact instant only; never = created_at)
├── source_id, raw_input_id?, confidence
└── created_at (bookkeeping only)
```

Invariants:

```text
no is_current
no supersedes_id
0..N history per entity/dimension
unit/currency exclusivity CHECK
NO_BACKFILL legacy State
COMMIT_VALID_INDEPENDENTLY for Event+Measurement
```

## Multi-primitive write

```text
IngestIR may carry event + measurement together
Materializer processes both without exclusive early-return
Invalid Measurement soft-skips when Event co-present
Duplicate materialization from assertions[] avoided (IR is single source)
```

## Non-materialized preservation (I11.15.2-R)

```text
SEMANTIC_VALIDITY ≠ MATERIALIZATION_READINESS

Omission from materialization IR does NOT remove Measurement from:
  ResolutionResult.assertions
  ResolutionResult.non_materialized_primitives
  ResolutionResult.non_materialized_reasons  (e.g. measurement_entity_required)

Entity-less “Está 38 graus.” → SEMANTICALLY_VALID_NON_MATERIALIZABLE
```

## Query

```text
Measurement QueryIR / QueryEngine / Resolver = NOT IMPLEMENTED
```

## Authority

`src/pke/persist/migrations/v8_to_v9.py`
`src/pke/interpretation/semantic/measurement_contract.py`
