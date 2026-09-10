# ADR 0078 — Clarification Quality: CLARIFY vs UNSUPPORTED vs ABSTAIN (E1.3)

## Status

**Accepted** — E1.3 Clarification Quality.

Does not add Attributes, primitives, relations, or everyday domain concepts.
Does not authorize E1.4.

Extends CapabilityStrategy (I12.12) and D-E1-15/16.

## Context

Before everyday Attribute expansion, utterances such as `Meu nome é Carlos.` failed with
`missing_attribute_dimension` and rendered as CLARIFY (`Pode detalhar um pouco mais?`).
The user had already supplied sufficient information; the gap was Engine capability.

## Decision

### Unlockability rule

```text
missing / ambiguous information
AND user can provide the missing information
→ CLARIFY

information already sufficient for intent
BUT Engine lacks semantic capability
→ UNSUPPORTED

unsafe / contradictory / non-actionable
AND no useful clarification question
→ SAFE_ABSTAIN (or INVALID)
```

### CapabilityOutcome

Adds explicit `UNSUPPORTED` alongside existing `CLARIFY` / `SAFE_ABSTAIN` / execute outcomes.

### Attribute persistability split

| Persistability note | Readiness reason | Typical outcome |
|---------------------|------------------|-----------------|
| `attribute_value_required` | `missing_attribute_value` | CLARIFY (user unlockable) |
| `unsupported_attribute_dimension` | `unsupported_attribute_dimension` | UNSUPPORTED |
| `attribute_dimension_value_required` | `missing_attribute_dimension` | CLARIFY (legacy empty cue) |

Incomplete surface cues (`Meu carro é...`) remain unlockable.
Present but unresolvable expressions (`signo Áries`) are capability gaps.

### Authority

`decide_capability(readiness, proposal=...)` remains the sole capability decision authority.
LLM does not choose clarify/unsupported/abstain.
Ingest maps Interpreter `execution_incomplete` through CapabilityStrategy (not a hardcoded
`missing_attribute_dimension → CLARIFY` table).

### Observability

`CapabilityDecision` exposes `user_unlockable`, `primary_reason`, and `diagnostic` tuples
(`capability_outcome=…`, `reason=…`, `user_unlockable=…`, `question_key=…`).

### Clarification questions

Prefer slot-specific `question_key` (e.g. `clarify.attribute.vehicle_value`).
Generic `Pode detalhar um pouco mais?` remains fallback only when CLARIFY is correct and
no safer specific key exists (`clarify.generic`).

### Product / JAMES

Public DTO unchanged. Presenter gains question strings only. JAMES remains presentation-only.

## Consequences

- Corpus soft family `attribute_incomplete` still expects CLARIFY for empty expressions.
- Known unsupported Attribute dimensions no longer fake-clarify.
- E1.2 valid everyday writes remain AUTO_EXECUTE → commit.
