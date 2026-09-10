# ADR 0021 — Lexical Sense & Canonicalization Safety

## Status

Accepted — I11.6.1

## Context

I11.6 introduced SemanticProposal → PrimitiveRouter → SemanticConceptResolver → Canonical IR.
Initial benchmarks showed acceptable pass rates, but **semantic safety failures** were discovered:

- PX1: *"O técnico fez a instalação do ar."* → wrongly canonicalized as `action.replace`
- PX2: *"As instalações da empresa são novas."* → wrongly canonicalized as `state.value.working`

Root cause: **lexical alias matching without sense constraints** — isolated expression similarity
coerced nearest available canonical concept.

I11.6-R is **HOLD** until canonicalization safety is proven.

## Decision

### Precision before recall

Freeze ordering:

```text
correct canonical > unresolved > ambiguous >>> wrong canonical
```

The resolver must **abstain** when evidence is insufficient. Coverage must not increase at the
cost of false canonicalization.

### Sense vs concept (polysemy architecture)

```text
lexeme → contextual sense → semantic role → canonical concept candidate
```

Not:

```text
lexeme → canonical concept
```

New module `sense.py` recognizes contextual senses (install, facilities, replace_physical,
exchange_idea, currency_exchange, property_new, etc.) **independently** of CORE keys.

### Two evaluation dimensions

- **PRIMITIVE_CORRECT** — routing by structured semantic signals
- **CONCEPT_CORRECT** — canonical key only when gate passes

Safe partial resolution (`SAFE_PARTIAL`, `ONTOLOGY_GAP`) is valid: primitive correct, concept
unresolved.

### Canonicalization gate

Before emitting a canonical concept key, require compatibility between:

- expression sense
- semantic role / primitive
- subject/object entity kinds
- change/condition/link semantics
- concept constraints

A lone lexical alias match is **insufficient**.

### Safe abstention & resolution status

`ResolvedConcepts` extended with:

- `resolution_status`: resolved | ambiguous | unresolved | safe_partial | ontology_gap | blocked
- `recognized_sense`, `surface_expression`, `ontology_gap`, `safe_abstention`, `abstention_reason`

Downstream can distinguish *understood but no safe concept* from *total failure*.

### Alias constraints tightened

Removed unsafe aliases:

- installation → `action.replace` (install ≠ replace)
- facilities/new → `state.value.working`

`action.replace` requires **physical component evidence** (`REPLACE_PHYSICAL` sense), not bare
"trocar"/"substituir".

### Entity constraints

- `relation.employed_by`: person subject + organization object only
- Mechanical *"trabalha"* (motor) blocked at alias constraints + gate

### State constraints

- `property_new` sense blocks `working`, `open`, `broken` coercion
- `broken`/`open` require operational/openness semantics, not adjective similarity

### Ambiguity & determinism

- Equal-evidence candidates → `AMBIGUOUS`, no arbitrary pick
- Tie-break uses `(priority, min(expression), canonical_key)` — **not registry insertion order**

### Ontology gap classification

When sense is recognized but CORE lacks concept (e.g. `install`, `facilities`, `currency_exchange`):

- status `ONTOLOGY_GAP`
- register debt **ONTOLOGY-COVERAGE-01**
- **do not** add CORE concepts in this increment to green tests

### I11.6 reclassification

I11.6 initially overclassified PX1/PX2 as PASS. I11.6.1 corrects semantic acceptance criteria.

## Consequences

### Positive

- FALSE_CANONICALIZATION_RATE target 0% on mandatory polysemy matrix (LS1–LS11)
- World model protected from contaminated canonical knowledge
- Clear path for future ontology growth via registered gaps, not coercion

### Negative / deferred

- CANONICAL_COVERAGE may decrease vs I11.6 (acceptable)
- Event live coverage remains deferred (safety first)
- CORE not expanded: `action.install`, facilities concepts, currency exchange — ONTOLOGY-COVERAGE-01
- ADAPTIVE-ALIAS-01 remains deferred
- I11.6-R, Knowledge Enrichment, Behavioral Memory — not started

## References

- ADR 0020 — Semantic Resolution & Primitive Routing
- I11.6.1 specification — Lexical Sense & Canonicalization Safety
