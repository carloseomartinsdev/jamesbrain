# ADR 0049 — Core Debt Inventory & V1 Readiness Gate (I11.18)

## Status

Accepted — **audit only**. No schema/migration/ontology/prompt/feature work.

## Question

```text
HOW_CLOSE_IS_THE_KNOWLEDGE_CORE_TO_V1_FREEZE?
```

## Operational definition — PKE Knowledge Core v1

Frozen contract based on built architecture (not future roadmap):

```text
NL knowledge ingest
structured SemanticProposal interpretation
entity resolution
temporal knowledge (TIME-01)
Event (+ Action compositional)
State
Relation (lifecycle)
Attribute
Measurement (WRITE/READ observation modes; no analytics/current_value)
Correction / retraction (ledger v10 + effectiveness)
persistence (schema v10)
query/retrieval with epistemic uncertainty
user isolation
history preservation
deterministic authority boundaries
LLM proposes; PKE decides commit
```

Explicitly **out of Knowledge Core v1**:

```text
API / conversation orchestration / clarification UX
provider robustness / live prompt hardening
observability / deployment
Measurement analytics / current_value
Evidence-01 generic assertion registry
TYPE first-class persistence
adaptive aliases / ontology learning
behavioral hypothesis layer
proposition-wide / multi-target correction
audit meta-query for corrections
holdout execution
```

## Product v1 (separate)

Requires Knowledge Core freeze **plus** product shell: API, orchestration,
provider reliability, clarification, observability, config, errors, deploy.

## Debt classification (I11.18)

See completion report tables. No debt left as unclassified `OPEN`.

Key decisions:

| Debt | Decision |
|------|----------|
| EVIDENCE-01 | POST_V1 |
| MEASUREMENT-ANALYTICS (+ current_value) | POST_V1 |
| TYPE persistence | POST_V1 (routing-only acceptable) |
| ONTOLOGY-COVERAGE-01 | BLOCKS_PRODUCT_V1 / coverage |
| INTERPRETER-*-01 / RETRY | BLOCKS_PRODUCT_V1 (provider robustness) |
| ADAPTIVE-ALIAS-01 | POST_V1 |
| SEMANTIC-QUERY-01 | BLOCKS_PRODUCT_V1 (coverage; residual convenience) |
| behavioral patterns | POST_V1 |
| CORRECTION_ENGINE_DEBT | ALREADY_RESOLVED |
| TIME-01 / MIGRATION-01 | ALREADY_RESOLVED |
| MEASUREMENT-01 (base) | ALREADY_RESOLVED → analytics split POST_V1 |
| LAST_EVENT legacy path | OBSOLETE as authority; remnant compatibility only |

## Core v1 blockers found

```text
NONE
```

No hidden dual-authority / created_at-as-fact-time / insertion-order authority /
LLM persistence authority regressions identified in this audit that reopen closed
invariants. Characterization remains consistent with ADRs 0043–0048.

## Recommendation

```text
PROCEED_TO_CORE_V1_FINAL_FREEZE
```

Minimum path:

```text
CURRENT (v10, CORE 65, Correction CLOSED)
  → I11-R / Knowledge Core v1 Freeze revalidation (deterministic suite + invariants ADR)
  → (optional) Product track: interpreter hardening, API, clarification
```

## Checkpoint

```text
schema = v10
CORE = 65
baseline = 1587 passed / 0 failed / 7 live deselected
Correction Engine = CLOSED
TIME-01 = CLOSED
holdout = untouched
```
