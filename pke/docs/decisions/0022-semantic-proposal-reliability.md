# ADR 0022 — Semantic Proposal Reliability

## Status

Accepted — I11.7

## Context

I11.6-R measured live semantic resolution. Deterministic architecture was green (0 false
canonicalization), but live primary frontier was mislabeled `PROPOSAL_WIRE` (29/54 runs).

Audit of I11.6-R corpus revealed:

- All 29 `PROPOSAL_WIRE` runs had `provider_response_success=false` (no raw content)
- Actual cause: **provider empty/failed response**, not transport parse failure
- 25 runs parsed; 14 parsed but no knowledge (semantic/resolution/canonical stages)
- `DeepSeekInterpreter` raised invalid `ValidationError` (KeyError) on semantic unresolved

Primary frontier reclassified: **PROPOSAL_QUALITY** with sub-stages:

```text
PROVIDER_EMPTY → RAW_OUTPUT_FORMAT → NORMALIZATION → PROPOSAL_TRANSPORT
→ PROPOSAL_SEMANTICS → … → KNOWLEDGE
```

## Decision

### Separate transport from semantics

```text
Provider Raw Output
→ Raw Output Normalization (SemanticProposalNormalizer)
→ ProviderEnvelopeDispatcher (v3 semantic | v2 canonical | invalid)
→ Proposal Transport Validation (Pydantic wire)
→ Semantic Proposal Assessment (actionable | partial | insufficient | contradictory)
→ existing semantic pipeline
```

### Safe normalization only (N1–N4)

Recover deterministically:

- Markdown JSON fences
- Single JSON object in harmless prefix/suffix text
- Missing envelope wrapping flat `SemanticProposal` shape
- Known enum casing (`STATE` → `state`)
- Documented field drift (`expression` → `text` on entities; `primitive` → `primitive_hint`)

**Forbidden:** invent subject/object, relation expressions, actions, or primitives from raw NL.

### Semantic completeness validator

`assess_semantic_proposal()` returns ACTIONABLE / PARTIAL / INSUFFICIENT / CONTRADICTORY
with primitive-specific minimum roles — without canonical concepts.

INSUFFICIENT → `InterpretationError(proposal_semantics:…)`  
PARTIAL → allow resolution (ontology gap OK)  
Unresolved canonical → `InterpretationError(semantic_resolution:…)` — not wire failure

### v2 compatibility explicit

Canonical v2 wire detected → `V2_CANONICAL` route with `v2_compat_fallback=true` metric.
Not counted as v3 proposal success.

### Prompt v3 refinements

- JSON only (no markdown)
- `primitive_hint` optional when semantic signals suffice
- Partial honest proposals encouraged
- Contrastive examples (state/event/relation/partial install)

### No LLM retry

Retry policy deferred as INTERPRETER-RETRY-01 if evidence warrants.

## Consequences

### Positive

- Failure frontier no longer opaque
- Transport recovery without semantic invention
- Semantic unresolved no longer masquerades as wire/KeyError failure
- I11.6.1 safety invariants preserved

### Negative / deferred

- Provider empty responses require retry or provider reliability (not fixed by normalizer)
- Event live 0% may persist until proposal quality improves or EVENT_REPRESENTATION
- SEMANTIC-QUERY-01, ONTOLOGY-COVERAGE-01 unchanged

## References

- ADR 0020, 0021
- I11.6-R report
- I11.7 specification
