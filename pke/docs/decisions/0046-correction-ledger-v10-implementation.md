# ADR 0046 — Correction Ledger v10 Implementation (I11.17.2)

## Status

Accepted — **implemented**. Schema **v10**.

## Depends on

- ADR 0044 — Correction semantics / evidence lineage
- ADR 0045 — Correction ledger v10 storage contract

## Implemented

| Component | Location |
|-----------|----------|
| `knowledge_corrections` ORM | `pke.persist.sqlite.tables.KnowledgeCorrectionRow` |
| Migration v9→v10 | `pke.persist.migrations.v9_to_v10` |
| Domain | `pke.domain.corrections` |
| Kind registry + resolver | `pke.application.knowledge_reference` |
| CorrectionRepository | `SqlCorrectionRepository` |
| CorrectionService | `pke.application.correction_service` |
| AssertionEffectivenessResolver | `pke.query.effectiveness` |
| Query integration | `QueryEngine` filters via shared resolver (all five primitives) |

## Schema

```text
schema before = v9
schema after = v10
migration = v9→v10
correction backfill = NONE
world-row mutation = NONE
CORE = 65
```

Table matches ADR 0045: operations `retract|replace`, UNIQUE target, no status/reason/supersedes_correction_id.

## Effectiveness invariant

```text
An assertion is EFFECTIVE iff
no committed Correction targets its KnowledgeReference.
```

## Transactions

```text
RETRACT: validate → Correction.add → commit
REPLACE: materialize replacement (flush) → validate refs → Correction.add → commit
rollback removes replacement + ledger together
```

`KnowledgeMaterializer` does not commit; `CorrectionService` coordinates UoW.

## Query integration

```text
PRIMITIVE_RESOLVERS_SHARED_EFFECTIVENESS
```

`QueryEngine` loads `graph.corrections` and filters Event/Measurement/Relation/State/Attribute pools through `AssertionEffectivenessResolver` before ordinary reasoning.

## Evidence-01

Deferred. Typed KnowledgeReference + application validation sufficient.

## Legacy

`IrCorrection` / `LAST_EVENT` remains non-canonical; not effectiveness/target authority.

## Remaining Correction Engine work

- Natural-language CorrectionTargetResolver / ingest revalidation
- Audit/meta query (`include_retracted`)
- Privacy deletion integrity
- Deprecate LAST_EVENT correction path

## Recommendation

```text
I11.17.2_CLOSE_PROCEED_TO_CORRECTION_INGEST_REVALIDATION
```
