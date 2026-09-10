# ADR 0051 — Engine v1 Reliability Baseline & Interpreter Hardening Design Freeze (I12)

## Status

Accepted — **design / characterization freeze**. No Core redesign. No schema/migration.
No CORE expansion. No prompt optimization in this increment. Holdout untouched.

## Phase shift

```text
Knowledge Core v1 = FROZEN (ADR 0050)
Focus = ENGINE_V1_RELIABILITY
Language boundary = Interpreter / Provider → SemanticProposal → Frozen Core
```

Do **not** change Core to absorb Interpreter errors.

## Central answers

```text
IS_THE_CURRENT_INTERPRETER_RELIABLE_ENOUGH_TO_SERVE_AS_THE_ENGINE_V1_LANGUAGE_BOUNDARY?
NO
```

Deterministic Fake/fixture path + frozen Core are solid.
Live provider path lacks measured reliability, retry policy, and prompt coverage for
Measurement/Correction cues.

```text
IS_SEMANTIC_PROPOSAL_EXPRESSIVE_ENOUGH_FOR_ENGINE_V1?
YES
```

```text
IS_WIRE_CONTRACT_EXPRESSIVE_ENOUGH_FOR_ENGINE_V1?
YES
```

```text
IS_PROMPT_OPTIMIZATION_THE_NEXT_CORRECT_ACTION?
YES
```

(after this freeze — schema is sufficient; primary gaps are PROMPT/MODEL/PROVIDER,
not SemanticProposal redesign)

No `SEMANTIC_PROPOSAL_SCHEMA_GAP` requiring Core/proposal redesign was found for
currently supported Core v1 semantics.

## Failure taxonomy (frozen)

```text
A. INTENT FAILURE
B. PRIMITIVE ROUTING FAILURE
C. SEMANTIC FRAME FAILURE
D. CANONICALIZATION FAILURE
E. TRANSPORT / PROVIDER FAILURE
```

Severity:

```text
S0 SAFE_ABSTENTION          — acceptable
S1 COVERAGE_MISS            — product quality
S2 SEMANTIC_INFORMATION_LOSS — investigate
S3 WRONG_PRIMITIVE_OR_CANONICAL — Engine blocker
S4 UNSAFE_WORLD_MUTATION_RISK — critical
```

Priority:

```text
correct canonical > safe unresolved/ambiguity >>> wrong canonical
```

## Debt characterization

| Debt | Nature | Engine impact |
|------|--------|---------------|
| INTERPRETER-STATE-01 | live State proposal variance (MODEL/PROMPT) | Engine reliability |
| INTERPRETER-RELATION-01 | live Relation variance | Engine reliability |
| INTERPRETER-EVENT-01 | live Event/Action preservation | Engine reliability |
| INTERPRETER-RETRY-01 | transport/provider robustness — **not implemented** | Engine reliability |
| ONTOLOGY-COVERAGE-01 | lexical/concept coverage (safe abstention OK) | coverage S1 |
| SEMANTIC-QUERY-01 | NL query convenience / expressiveness residual | coverage / query UX |
| Clarification UX | product — observed only | Product |

## Retry policy design (frozen, not implemented)

```text
provider retry != knowledge write retry
retry only before commit
max attempts = 2 (bounded)
```

**Retryable:** timeout, empty response, invalid JSON, schema-invalid structured output,
HTTP 5xx, temporary provider failure.

**Non-retryable:** ambiguous entity, unresolved concept, ontology gap, wrong-but-valid
JSON proposal, safe abstention outcomes.

**Allowed normalization:** recover JSON envelope; structural field equivalence.
**Forbidden:** invent entity/time/primitive/concept.

Idempotency: no duplicate persisted knowledge from provider retry.
Observability: log attempt, failure class, raw preview, schema issues.

## Prompt audit (no tuning)

`prompts_v3` documents State/Event/Attribute/TYPE distinctions well.
Likely under-documents:

- `measurement_semantics` / multi-primitive composition
- `correction_semantics` / correction vs negation/evolution

Classify observed future live failures primarily as **PROMPT/MODEL** until proven otherwise.
Do not treat Core as broken for Interpreter misses.

## Development corpus

```text
tests/engine_v1_baseline/corpus.py
TOTAL_CASES >= 250 (currently ~330)
NOT holdout
```

Deterministic baseline tests:

```text
tests/engine_v1_baseline/test_engine_v1_reliability_baseline_i12.py
```

Live characterization remains `-m live`, deselected by default, not closure authority.

## Engine v1 acceptance (proposed)

Unsafe errors (S3/S4, false canonicalization, false correction, mutation from interpreter
failure) ≈ **0**.

Safe abstention measured separately and acceptable.

Coverage (S1) tracked, not a freeze blocker for Core (already frozen).

## Intentionally out of scope here

```text
prompt wording optimization
retry implementation
clarification UX
ontology concept addition
QueryEngine new modes
Core changes
holdout
```

## Next increment candidates

1. Prompt/schema-hint hardening for Measurement + Correction + multi-primitive (no Core change)
2. INTERPRETER-RETRY-01 implementation per frozen policy
3. Live characterization suite (deselected) against development corpus labels
4. Clarification UX (Product)

## Checkpoint

```text
schema = v10
CORE = 65
KNOWLEDGE_CORE_V1 = FROZEN
holdout = untouched
```
