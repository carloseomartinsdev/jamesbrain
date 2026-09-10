# PKE E1 Patch P1 — Live Provider Query Completeness

**Status:** `ACCEPTED` — corrective patch on frozen E1  
**Date:** 2026-09-04  
**Base:** `PKE E1 = FROZEN` (ADR 0079)  
**Does not reopen E1 for semantic expansion.**

## Context

Beta live name queries (`Qual é o meu nome?`, `Como me chamo?`) returned Product
`unsupported` / `operation.kind=none` while Knowledge already held
`principal.attribute.name`. Diagnosis: live provider emitted incomplete
`semantic_query` (no `attribute_expression` / `stable_property_semantics`) →
`proposal_semantics:insufficient:semantic_signals` before `QueryIR`.

E1.2 contract tests used `FakeInterpreter` + handcrafted proposals and did not
cover this provider gap.

## Decision

1. **Deterministic repair (primary):** tighten `repair_my_name_query` (whitelist
   whole-utterance self-name questions; hard negatives) and apply
   `apply_e1_self_repairs` **before** the semantic sufficiency gate in
   `DeepSeekInterpreter`.
2. **Prompt reinforcement (secondary):** v4/v5 spell out self-name ATTRIBUTE query shape.
3. **Presenter:** interpretation_error text must not say “registrar”.
4. **Regression:** fixture captured incomplete proposals + EngineGateway + Product API path.

## Non-goals

No new attributes, relations, primitives, domains, or E2 work.

## Evidence

- `tests/e1_patch_p1/test_p1_live_provider_query_completeness.py`
- Report: `docs/reports/E1-PATCH-P1-LIVE-PROVIDER-QUERY-COMPLETENESS.md`
