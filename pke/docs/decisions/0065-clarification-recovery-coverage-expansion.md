# ADR 0065 — Clarification Recovery Coverage Expansion (I12.14)

## Status

**CLOSED — implemented (bounded dimension + state_value)**

## Context

I12.13 shipped entity-reference MVP recovery. Live left **66 / 94** clarifications
unsupported (`dimension` / `value`). Gap ledger freeze required before any new family.

## Decision

### Gap ledger (frozen first)

`docs/reports/I12.14-CLARIFICATION-GAP-LEDGER.json`

| Family | Count | Candidate v1 |
|--------|------:|--------------|
| VALUE (`state_value`) | 43 | YES |
| DIMENSION (`attribute_dimension` 13, `measurement_dimension` 10) | 23 | YES |
| CORRECTION_TARGET | 0 | NO |
| TEMPORAL | 0 | NO |

### SAFE_FOR_ENGINE_V1

```text
entity_reference   (I12.13)
dimension          measurement_dimension, attribute_dimension
value              state_value only
```

### Remain UNSUPPORTED_RECOVERY_SLOT

```text
correction_target
temporal
state_dimension
measurement_value / attribute_value (generic)
```

### Authority delegation (no generic filler)

| Family | Authority |
|--------|-----------|
| entity_reference | EntityResolver (+ apply_clarification_evidence) |
| measurement_dimension | `resolve_measurement_dimension_key_from_answer` → `measurable_dimension_key` |
| attribute_dimension | `resolve_attribute_dimension_key_from_answer` → attribute_resolution |
| state_value | `resolve_state_value_key_from_answer` → STATE ContextualAlias (+ CORE labels as alias expressions) |

### Boundedness

- Original `SemanticProposal` / `raw_input` immutable
- Exactly one authorized slot may change
- Extra content after comma ignored for head token
- `condition_semantics` required for state_value (no invent)
- Max clarification rounds = **1**
- No Interpreter / LLM / Wire / Proposal / Core change

## Consequences

- Live total useful capture after recovery: **~51%** (was ~42% in I12.13)
- Autonomous capture unchanged ~**37%**
- Supported clarification coverage rate (live): **100%** of current clarify slots
- Supported recovery success ~**56%**
- MP1 entity recovery still **100%**
- Correction target deferred (0 ledger hits; mutation sensitivity)
- Engine v1 reliability still **NO** — State vocabulary gaps + Relation/Event debt remain

See `docs/reports/I12.14-CLARIFICATION-COVERAGE-EXPANSION.md`.
