# ADR 0020 — Semantic Resolution & Primitive Routing

## Status

Accepted — I11.6

## Context

I11.4-R / I11.5-R showed deterministic State/Relation pipelines are green, but live interpreter knowledge success ~0%. Frontier: CANONICAL/WIRE — LLM must emit exact canonical keys (`record_state`, `relation.employed_by`, etc.).

## Problem

Language → primitive → canonical representation is the main frontier. LLM output was treated as canonical IR; wire validation rejected semantically valid proposals when keys differed.

## Decision

Introduce deterministic layer between LLM and canonical IR:

```text
SemanticProposal (wire v3)
    ↓ PrimitiveRouter
    ↓ SemanticConceptResolver (contextual aliases + constraints)
    ↓ WireIngestIR / IngestIR (existing)
    ↓ existing ingest pipeline
```

### SemanticProposal

Relaxed wire (`ir_kind: semantic_proposal`) with:
- semantic expressions (not canonical keys)
- entity `kind_hint` (person, organization, appliance, …)
- structured signals: `change_semantics`, `condition_semantics`, `link_semantics`, `stable_property_semantics`

### PrimitiveRouter

Routes EVENT/STATE/RELATION/ATTRIBUTE from structured signals — **not** raw-text keyword rules.

### SemanticConceptResolver

Contextual alias registry with constraints (subject/object kind, change vs condition, forbid phrases). Confidence: EXACT | CONTEXTUAL | AMBIGUOUS | UNRESOLVED.

### Provider independence

Resolution lives in `pke.interpretation.semantic.*` — not DeepSeek-specific.

### Prompt v3

`pke.interpret.v3` teaches semantic proposal contract; reduces canonical-key burden. v2 canonical wire remains available.

### Backward compatibility

- FakeInterpreter → canonical IngestIR (unchanged)
- DeepSeek v2 → canonical wire (unchanged)
- DeepSeek v3 (default) → proposal → resolver → canonical

### CORE boundary

Resolver consults CORE only; cannot mutate or auto-promote EXTENDED/PERSONAL.

### Unknown concepts

Prefer UNRESOLVED over WRONG_CANONICAL (e.g. attribute.color not in CORE).

## Deferred

- Adaptive Concept Promotion / PERSONAL alias learning
- Behavioral Memory in resolution scoring
- Vector/embeddings resolver
- Generic Evidence Engine (EVIDENCE-01)

## Consequences

- Live failure observable by stage: proposal parse / primitive routing / concept resolution / canonical IR
- Deterministic PR/SC/PX test suite
- LLM canonical-key dependency: PARTIALLY — optional hints OK, correctness not required
