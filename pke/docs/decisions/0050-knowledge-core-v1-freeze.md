# ADR 0050 — Knowledge Core v1 Freeze (I11-R)

## Status

**Accepted — KNOWLEDGE_CORE_V1 = FROZEN.**

Final cross-layer revalidation. No feature / schema / migration / CORE / prompt work.
Holdout untouched. Live provider remains deselected by default.

## Depends on

- ADR 0049 — Core debt inventory & V1 readiness (BLOCKS_CORE_V1 = NONE)
- ADR 0043 — TIME-01 CLOSED
- ADR 0027 — MIGRATION-01 CLOSED
- ADR 0044–0048 — Correction Engine CLOSED
- Primitive ADRs for Event/State/Relation/Attribute/Measurement

## Operational definition

```text
NL ingest → SemanticProposal → routing/resolution → materialization → persistence
+ Entity / Temporal / Ontology authorities
+ Event(+Action) · State · Relation · Attribute · Measurement
+ Correction ledger v10 + shared AssertionEffectivenessResolver
+ Query with epistemic uncertainty
+ user isolation + history preservation
+ LLM proposes; PKE commits
```

## Final authority map

| Concern | Authority | Competing? |
|---------|-----------|------------|
| Semantic Proposal | Interpreter → SemanticProposal | NO |
| Primitive Routing | semantic router | NO |
| Concept Resolution | SemanticConceptResolver | NO |
| Entity Resolution | EntityResolver | NO |
| Temporal Resolution | TemporalResolver / TemporalKnowledge | NO |
| Temporal Membership | shared temporal.membership | NO |
| Materialization | KnowledgeMaterializer | NO |
| Persistence | storage (no semantic truth) | NO |
| Migration | Python migration runner | NO |
| Query | QueryEngine + primitive resolvers | NO |
| Event / Measurement / Relation / State / Attribute truth | respective epistemic resolvers | NO |
| Correction intent | SemanticProposal / correction pipeline | NO |
| Correction target | CorrectionTargetResolver | NO |
| Correction reference integrity | KnowledgeReferenceResolver | NO |
| Correction effectiveness | AssertionEffectivenessResolver | NO |

## Supported primitives

All five: WRITE · READ · temporal · Correction · user isolation — READY.

Action remains compositional with Event.

## Unsupported Core v1 (canonical)

```text
Measurement current_value / analytics / freshness
proposition-wide / multi-target correction
audit/meta correction query
Evidence-01
TYPE first-class persistence
adaptive aliases
behavioral hypotheses
advanced recurrence expansion
provider/live robustness guarantees
Product/API UX
```

## Freeze checkpoint

```text
schema = v10
CORE = 65
TIME-01 CLOSED
MIGRATION-01 CLOSED
Correction Engine CLOSED
holdout untouched
```

## Benchmark

`tests/core_v1_freeze/` — ≥150 deterministic cases including adversarial C01–C40.

## Remaining outside freeze

**Product/Engine:** INTERPRETER-STATE/RELATION/EVENT/RETRY, ONTOLOGY-COVERAGE-01,
SEMANTIC-QUERY-01, Clarification UX.

**Post-v1:** EVIDENCE-01, MEASUREMENT-ANALYTICS, TYPE persistence, ADAPTIVE-ALIAS-01,
behavioral hypotheses.

## Decision

```text
KNOWLEDGE_CORE_V1_FREEZE
```

## Resume boundary

After pause, resume from Product/Engine track — do not reopen Core contracts without
explicit “alter core” decision and new ADR.
