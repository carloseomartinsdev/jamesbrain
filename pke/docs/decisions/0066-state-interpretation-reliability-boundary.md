# ADR 0066 — State Interpretation Reliability Boundary (I12.15)

## Status

**CLOSED — characterization complete; bounded clarification hygiene implemented**

## Context

After I12.14, State remained the highest Engine v1 blocker. Live State category
(I12.11 baseline, re-evaluated on current Engine):

| Outcome | Runs |
|---------|-----:|
| STATE_CORRECT (autonomous commit) | 12 |
| VALID_STATE_CANONICAL_UNRESOLVED | 27 |

No downstream loss of correctly resolved State. No State omission when
`condition_semantics` / `state_expression` present.

## Decision

### Dominant cause

```text
CANONICALIZATION_FAILURE
```

Model usually emits State signals; expressions such as `ligado`, `paid`,
`connected` are **not** in frozen CORE (65). Expanding ontology is out of scope.

### Deterministic Engine defect found (bounded)

Present `state_expression` that fails alias→CORE resolution was mapped to
`missing_state_value` → **CLARIFY**, which is not user-answerable into CORE.

**Fix (I12.15):**

```text
state_expression present + unresolved
→ state_value_canonical_unresolved
→ SAFE_ABSTAIN (non-clarifiable)
```

Truly empty `state_expression` still → `missing_state_value` → CLARIFY +
`state_value` recovery (I12.14).

Also corrected `question_key` for State/measurement/attribute slots
(away from mistaken `clarify.attribute.amount` for State).

### Not done

- No prompt change (v4 remains active)
- No ontology expansion
- No raw-text State detector
- No SemanticProposal / Wire / Core change

### Clarification matrix (State)

| State gap | Detectable | Clarify eligible | Recovery supported | Outcome |
|---|---:|---:|---:|---|
| missing entity | weak* | no* | entity_reference (if routed) | *persistability does not require subject |
| missing dimension (`state_dimension`) | yes | policy medium | **NO** | unsupported recovery slot |
| missing value (empty expression) | yes | yes | **YES** (`state_value`) | clarify → recover |
| present uncanonical value | yes | **NO** (I12.15) | n/a | safe abstain |
| ambiguous entity | resolver | existing | entity_reference | unchanged |
| unknown canonical value | yes | no | no | abstain / ontology debt |

`WHAT_EXACT_STATE_DIMENSION_GAPS_ARE_RECOVERABLE_TODAY?` → **none**.
I12.14 `dimension` recovery covers `measurement_dimension` and
`attribute_dimension` only — not `state_dimension`.

## Consequences

- False State clarifications eliminated for non-CORE expressions
- State useful capture **unchanged** without ontology reopen
- `INTERPRETER-STATE-01` remains **PARTIALLY_MITIGATED**
- Highest blocker shifts toward **RELATION_INTERPRETATION** (or remaining State ontology debt)
- Knowledge Core v1 remains FROZEN

See `docs/reports/I12.15-STATE-INTERPRETATION-HARDENING.md`.
