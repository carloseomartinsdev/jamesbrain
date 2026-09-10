# ADR 0067 — Relation Interpretation Reliability Boundary (I12.16)

## Status

**CLOSED — characterization complete; bounded clarification hygiene implemented**

## Context

After I12.15, Relation was the highest Engine v1 interpretation blocker.
Live Relation category (I12.11 baseline, re-evaluated):

| Outcome | Runs |
|---------|-----:|
| RELATION_CORRECT (autonomous commit) | 14 |
| VALID_RELATION_CANONICAL_UNRESOLVED | 22 |

Downstream loss = 0. Omission / wrong primitive = 0 on this set.

## Decision

### Dominant cause

```text
CANONICALIZATION_FAILURE
```

Model usually emits `link_semantics` + `relation_expression`; many expressions
(`member of`, `insured by`, `não trabalha mais`, …) are outside frozen CORE
(6 relation types). Ontology expansion is out of scope.

### Deterministic hygiene (I12.16)

When:

```text
relation_expression present
+ subject present
+ object present
+ relation_type unresolved against CORE
```

classify:

```text
relation_type_canonical_unresolved
→ SAFE_ABSTAIN
```

Do **not** CLARIFY endpoints for that case (false recoverable gap).

When an endpoint is missing, keep endpoint `entity_reference` clarification
(alias constraints often need the endpoint to match).

### Not done

- No prompt change (v4)
- No ontology expansion
- No raw Relation detector
- No Proposal / Wire / Core change
- No inverse/symmetric invention

### Endpoint recovery

Missing subject/object with resolvable CORE expression remain recoverable via
existing I12.13 `entity_reference` family — no second Relation endpoint system.

## Consequences

- Relation useful capture unchanged without Core reopen (~39% autonomous on live set)
- `INTERPRETER-RELATION-01` = **PARTIALLY_MITIGATED**
- Remaining limitation class matches State: **ONTOLOGY_COVERAGE** (POST_V1)
- Knowledge Core v1 remains FROZEN

See `docs/reports/I12.16-RELATION-INTERPRETATION-HARDENING.md`.
