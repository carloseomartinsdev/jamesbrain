# ADR 0045 — Correction Ledger, Typed KnowledgeReference & v10 Storage Contract (I11.17.1)

## Status

Accepted — **storage/transaction contract freeze**. Schema remains **v9** in this increment.
Future implementation = **schema v10**. No migration/code written here.

## Depends on

- ADR 0044 — Correction / retraction / evidence lineage design

## World vs epistemic

```text
IS_CORRECTION_A_WORLD_MODEL_PRIMITIVE? NO
IS_GENERIC_CORRECTION_LEDGER_STILL_THE_CHOSEN_ARCHITECTURE? YES
```

World rows stay immutable for correction status (no `is_retracted` columns).

## Effective assertion invariant (canonical)

```text
An assertion is EFFECTIVE iff
no committed Correction targets its KnowledgeReference.
```

| Situation | Effect |
|-----------|--------|
| no correction targets P | P EFFECTIVE |
| RETRACT P | P INEFFECTIVE |
| REPLACE P→Q | P INEFFECTIVE; Q EFFECTIVE unless later corrected |
| P→Q→R | P,Q INEFFECTIVE; R EFFECTIVE |
| P1,P2 support X; RETRACT P1 | P1 INEFFECTIVE; P2 EFFECTIVE |

No recursive chain walk needed for local effectiveness.
`UNKNOWN` only if ledger reference cannot be validated (corrupt/orphan) — never silently EFFECTIVE.

Ordinary queries use EFFECTIVE only.
Retracted rows remain stored for audit/meta queries (future; not world historical_existence).

## KnowledgeReference

```text
KnowledgeReference
├── kind: "event" | "measurement" | "relation" | "state" | "attribute"
└── assertion_id: str
```

`user_id` lives on `Correction.user_id` (and validated against target/replacement rows).
Not duplicated inside the reference storage columns.

Persisted discriminators are stable string literals (storage contract):

```text
event | measurement | relation | state | attribute
```

```text
CAN_ALL_FIVE_BE_TARGETS? YES
CAN_ALL_FIVE_BE_REPLACEMENTS? YES
(Entity / Source / Time / TYPE are not correction targets)
```

## Target integrity strategy

```text
TARGET_REFERENCE_STRATEGY = APPLICATION_VALIDATED_TYPED_REFERENCE
```

| Strategy | Verdict |
|----------|---------|
| APPLICATION_VALIDATED_TYPED_REFERENCE | **Chosen** — matches bounded I11.17; no Evidence-01 |
| NULLABLE_TYPED_FOREIGN_KEYS | Rejected — schema width; poor extensibility |
| GENERIC_ASSERTION_REGISTRY | Rejected — EVIDENCE-01; out of bound |
| PER_PRIMITIVE_CORRECTION_TABLES | Rejected — duplicated ledger |

Integrity enforced by `KnowledgeReferenceResolver` + `CorrectionRepository` before commit:

```text
kind supported ∧ row exists ∧ row.user_id == correction.user_id ∧ kind matches table
```

```text
CAN_INVALID_TARGET_REFERENCE_BE_COMMITTED? NO
```

FK delete: world rows use `RESTRICT` semantics for privacy-later; orphan ledger → effectiveness UNKNOWN / fail safely (not silent EFFECTIVE).

## Replacement

```text
CAN_REPLACEMENT_PRIMITIVE_DIFFER_FROM_TARGET_PRIMITIVE? YES
IS_REPLACEMENT_FRAME_PERSISTED_BEFORE_MATERIALIZATION? NO
CAN_REPLACE_COMMIT_IF_REPLACEMENT_IS_NON_MATERIALIZABLE? NO
```

Policy unchanged: `NO_RETRACTION_UNTIL_REPLACEMENT_MATERIALIZES`.
Failed/unresolved/invalid replacement → no ledger row; target stays EFFECTIVE.

## Operation enum

Persisted explicit:

```text
retract | replace
```

Checks:

```text
retract  → replacement_* IS NULL
replace  → replacement_* IS NOT NULL
target ≠ replacement (same kind+id forbidden)
```

`operation` is authoritative for validation; not derived-only (auditability).

No separate CORRECT_TIME/VALUE storage ops — compositional REPLACE.

## Branching / repeated correction

```text
CAN_TWO_COMMITTED_CORRECTIONS_TARGET_THE_SAME_ASSERTION? NO
```

Storage: `UNIQUE(user_id, target_kind, target_id)`.

| Sequence | Behavior |
|----------|----------|
| RETRACT P ; RETRACT P | **reject** (P already INEFFECTIVE / unique) |
| REPLACE P→Q ; REPLACE P→R | **reject** |
| RETRACT P ; REPLACE P→Q | **reject** |
| REPLACE P→Q ; RETRACT P | **reject** |
| REPLACE P→Q ; REPLACE Q→R | **allowed** (targets differ) |
| semantic return to “blue” | **new assertion** P2; never reactivate P |

Correction-of-correction = successive REPLACE on lineage tip (Q then R), not dual `supersedes_correction_id`.

```text
Lineage authority = Correction.target → Correction.replacement links
(+ UNIQUE target)
No supersedes_correction_id column
No dual world_row.supersedes_id meaning for Correction
```

## v10 table: `knowledge_corrections`

| Column | Type | Null | Constraint | Responsibility |
|--------|------|-----:|------------|----------------|
| id | VARCHAR(32) | NO | PK | Correction identity |
| user_id | VARCHAR(64) | NO | FK users.id | Isolation |
| operation | VARCHAR(16) | NO | CHECK retract\|replace | Op authority |
| target_kind | VARCHAR(16) | NO | CHECK five kinds | Target discriminator |
| target_id | VARCHAR(32) | NO | — | Target assertion id |
| replacement_kind | VARCHAR(16) | YES | CHECK kinds or NULL | Replacement discriminator |
| replacement_id | VARCHAR(32) | YES | — | Replacement assertion id |
| raw_input_id | VARCHAR(32) | YES | FK raw_inputs.id | Correcting utterance |
| source_id | VARCHAR(32) | YES | FK sources.id | Provenance |
| recorded_at | DATETIME(tz) | NO | — | Bookkeeping time ≠ fact time |

Constraints / indexes:

```text
UNIQUE (user_id, target_kind, target_id)
CHECK operation/replacement consistency
CHECK NOT (target_kind = replacement_kind AND target_id = replacement_id)
INDEX (user_id, target_kind, target_id)
INDEX (user_id, replacement_kind, replacement_id)
FK raw_input / source RESTRICT or SET NULL only if privacy architecture says so later
```

No `status` column — **committed rows only** (failed attempts stay in ingest result / logs).
No free-form `reason` (raw input suffices).
No Correction `TemporalKnowledge`.
Confidence stays on proposal/replacement assertion, not required on ledger.

## AssertionEffectivenessResolver

```text
resolve(reference) → EFFECTIVE | INEFFECTIVE | UNKNOWN
resolve_many(references) → mapping
```

Optional audit payload: `correction_id`, `operation`, `replacement_reference`.

Shared across all five primitives. Repositories remain retrieval-only.

## Query integration

```text
PRIMITIVE_RESOLVERS_SHARED_EFFECTIVENESS
```

Each path (Event via QueryEngine, Measurement/Attribute/Relation/State resolvers) filters candidates through shared resolver before ordinary positive-evidence reasoning.

Retracted ≠ UNKNOWN temporal contributor (known INEFFECTIVE → exclude).
Corrupt UNKNOWN effectiveness → epistemic uncertainty / fail-safe (not silent include).

Historical world queries still use EFFECTIVE evidence only.
Correction audit queries (future) may include INEFFECTIVE — distinct intent.

## Transaction ownership

```text
CURRENT_MATERIALIZER_TRANSACTION_OWNER = IngestService (uow.commit)
CURRENT_INTERNAL_COMMIT_SITES = only SqliteUnitOfWork.commit / IngestService after materialize
REQUIRED_FUTURE_TRANSACTION_OWNER = CorrectionService (or IngestService correction branch) coordinating UoW
CAN_USE_FLUSH_BEFORE_FINAL_COMMIT = YES (repos already flush, not commit)
CAN_ROLLBACK_REPLACEMENT_AND_CORRECTION_TOGETHER = YES
```

Feasible REPLACE sequence:

```text
1. open UoW
2. materialize replacement via KnowledgeMaterializer (flush → ids)
3. CorrectionRepository.add(ledger row)
4. uow.commit()
# on any failure: uow.rollback() — target unchanged EFFECTIVE
```

```text
CAN_EXISTING_MATERIALIZATION_BE_COMPOSED_INTO_ONE_CORRECTION_TRANSACTION? YES
CAN_REPLACE_BE_IMPLEMENTED_AS_ONE_ATOMIC_TRANSACTION? YES
```

No premature `session.commit()` inside materializer/repositories.

## Materializer IDs

`MaterializationResult` already exposes `event_ids`, `measurement_ids`, attribute/state/relation ids (audit in implementation) — ADDITIVE if any missing for KnowledgeReference construction.

Legacy `_correction` / `LAST_EVENT` remains **non-canonical**; I11.17.2 must not use it as effectiveness/target authority.

## Bounded I11.17.2 implementation scope

```text
single resolved EFFECTIVE target
RETRACT | REPLACE
0|1 replacement assertion (any of five primitives)
replacement fully materialized before REPLACE commit
UNIQUE target enforcement
single-user UoW
no multi-target / proposition-wide / privacy / audit query
```

## v10 migration contract (future)

```text
v9 → v10 only
create knowledge_corrections (+ indexes/checks)
no correction backfill
no world-row mutation
CORE unchanged
version advances only after success
fresh v10 == migrated v10
Python migration runner sole authority
failed migration does not advance version
```

## Evidence-01

```text
DOES_V10_CORRECTION_REQUIRE_FULL_EVIDENCE01? NO
```

Typed KnowledgeReference + application validation substitutes for a generic assertion registry.

## Wire impact (future)

| Layer | Impact |
|-------|--------|
| SemanticProposal | ADDITIVE |
| WireSemanticEnvelope | ADDITIVE |
| WireIngestIR / IngestIR | ADDITIVE / COMPATIBILITY (deprecate LAST_EVENT authority) |
| ResolutionResult | ADDITIVE |
| KnowledgeCandidate | ADDITIVE |
| KnowledgeMaterializer | ADDITIVE (expose refs; no internal commit) |
| QueryEngine / resolvers | ADDITIVE (effectiveness filter) |

## Recommendation

```text
I11.17.1_CLOSE_PROCEED_TO_V10_IMPLEMENTATION
```

## Debt

```text
CORRECTION_ENGINE_DEBT     STORAGE_CONTRACT_FROZEN (impl OPEN → I11.17.2)
EVIDENCE-01                DEFERRED
TIME-01                    CLOSED
```
