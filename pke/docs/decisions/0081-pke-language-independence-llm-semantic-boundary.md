# ADR 0081 — PKE Language Independence & LLM Semantic Boundary

## Status

**Accepted** — incremental boundary (not a rewrite).

Extends ADR 0001 (LLM interpreta / PKE raciocina), ADR 0020 (SemanticProposal),
ADR 0074 (Product conversation vs Knowledge authority). Does not reopen Engine
v1 freeze or Knowledge Core schema.

## Context

E1 repairs started compensating live Interpreter gaps by re-parsing Portuguese
after the LLM (`qual?`, `meu carro`, `antes`, `pintei`, …). That makes the PKE
a second NLP stack and blocks adding languages without touching the knowledge
core.

The LLM often already emits structured meaning. Downstream must not invent
linguistic rules to “fix” later stages.

## Decision

### PKE Language Independence Principle

The PKE core MUST NOT depend on rules specific to Portuguese, English, or any
other natural language.

The LLM Interpreter converts natural language into a language-independent
Semantic IR. The PKE operates on that IR: identity, resolution, relations,
attributes, events, temporality, history, confidence, consistency, versioning,
persistence, and query.

The LLM Presenter (today: Product presenter templates) verbalizes structured
results. It MUST NOT invent facts, query knowledge, or silently correct the PKE.

```text
Natural language
    → Interpreter (linguistic meaning)
    → Semantic IR (language-independent)
    → PKE (knowledge operations)
    → Structured result
    → Presenter (wording)
    → Natural language
```

Mental test: if the PKE must reread `raw_input` to discover what the user meant,
the boundary is still wrong. `raw_input` may travel for audit/logging only.

### Linguistic vs knowledge ambiguity

| Kind | Example | Owner |
|------|---------|--------|
| Linguistic (ellipsis, pronoun, “qual?”) | Interpreter + discourse context | Interpreter |
| Knowledge (three cars, no discriminator) | `needs_clarification` / candidates | PKE |

### Conversation context ≠ knowledge dump

`InterpretationContext.recent_utterances` is discourse context for anaphora and
ellipsis. It is not a dump of the knowledge store. The PKE remains the
authority on facts.

### Canonicalization stays

`vehicle` → `entity.automobile`, `owns` → `relation.owns`, `cor` → `attribute.color`
remain PKE semantic/canonical work. Discovering that “meu” means possession is
Interpreter work (`reference_kind=possessive`).

### Safety unchanged

LLM proposes meaning. PKE validates meaning. Incomplete, contradictory, or
unsafe IR still yields clarification / unsupported / conflict. Deterministic
gates stay.

## Current map (as of this ADR)

| Stage | Owner | Role |
|-------|--------|------|
| Interpreter (DeepSeek + prompt v4) | `interpretation/` | NL → SemanticProposal |
| Transport normalize | `proposal_normalizer` / `llm_vocab` | Closed-slot coercion |
| Slot align | `slot_align` | Structured widen-to-narrow (possessive head noun) |
| E1 repairs | `self_repair`, `vehicle_repair`, `possessive_attribute_repair` | **Compatibility NLP fallback** (Class A/E) |
| Proposal assessment | `proposal_assessment` | Semantic sufficiency |
| Query resolution | `query_resolution` | Proposal → QueryIR |
| Canonical / engine | `resolver`, ingest, `AskService`, `QueryEngine` | Knowledge authority |
| Presenter | `product/conversation/presenter.py` | Structured result → copy (not an LLM yet) |

Class A repairs remain in the Interpreter pipeline as a compatibility layer.
They MUST NOT grow. New linguistic coverage goes to the Interpreter prompt /
discourse context, not to PKE regexes.

## Incremental change in this ADR

1. Prompt v4/v5 receive bounded discourse (`recent_utterances`) and must emit
   complete IR (ellipsis, temporal `relation_to_reference` / `selection`).
2. Attribute query mode prefers structured slots (`utterance_kind`, temporal
   selection) over scanning `qual` / `era` / `antes` in `raw_input`.
3. `AskService` identity composition keys off `attribute_query_mode=snapshot`,
   not Portuguese phrases.
4. Vehicle identity fallback maps to snapshot, not `marca` via `qual`+`meu carro`.
5. Previous/first attribute history uses existing `version_policy` + `sort` +
   `limit` (PKE knowledge), not the word `antes`.
6. Architectural tests: equivalent PT/EN/ES proposals; execution with opaque
   `raw_input`; the seven regression cases as structured IR.

## Not in this increment

- Deleting E1 Portuguese repairs (fixtures still use them as Interpreter fallback).
- Full multilingual live provider coverage.
- LLM Presenter (Product templates remain).
- Paint as mandatory Event+Attribute multi-primitive (existing attribute commit
  path stays; Event preservation is a later increment).
- Dumping PKE memory into the Interpreter prompt.

## Consequences

- Adding a language should not require PKE core edits.
- Live provider gaps are closed by better IR + discourse, not new phrase lists.
- `raw_input` remains on the wire for observability.
