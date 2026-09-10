# ADR 0052 — Interpreter Prompt Hardening (I12.1)

## Status

Accepted — **prompt optimization only**. No Core redesign. No schema/migration.
No SemanticProposal / Wire redesign. No ontology expansion. Holdout untouched.
`INTERPRETER-RETRY-01` remains deferred (not implemented here).

## Context

I12 (ADR 0051) concluded:

```text
IS_CURRENT_INTERPRETER_RELIABLE_ENOUGH_FOR_ENGINE_V1? NO
IS_SEMANTIC_PROPOSAL_EXPRESSIVE_ENOUGH? YES
IS_WIRE_CONTRACT_EXPRESSIVE_ENOUGH? YES
IS_PROMPT_OPTIMIZATION_THE_NEXT_CORRECT_ACTION? YES
```

Target failure classes (prompt-side):

- Measurement vs Attribute / State / Event
- Correction vs contradiction / negation / termination / evolution / new measurement
- Multi-primitive Event + Measurement (MP1–MP5)
- No invented persistent assertion IDs
- Prefer correct canonical > safe unresolved >>> wrong canonical

## Decision

Introduce canonical prompt **`pke.interpret.v4`** (`prompts_v4.py`) as default for
`DeepSeekInterpreter`. Keep v1–v3 resolvable for compatibility and regression.

### Prompt changes (conceptual)

**Added**

- Measurement definition (quantitative observation under observation scope)
- Measurement vs Attribute / State / Event contrasts
- Multi-primitive rules + MP1–MP5 examples
- Correction definition (meta-knowledge) + RETRACT vs REPLACE
- Correction vs contradiction / negation / relation termination / state evolution /
  measurement sequence / repeated event / query
- Ambiguous / unresolved correction target guidance
- Explicit ban on inventing assertion IDs
- Few-shots: measurement-only, Event+Measurement, State-not-Measurement,
  Correction REPLACE, termination-not-Correction

**Clarified**

- Additive assertions only when propositions are explicit (no enrichment)
- Temporal: preserve linguistic evidence; do not invent calendar precision
- Canonicalization abstention / unknown concept unresolved

**Removed / not changed**

- No SemanticProposal fields added
- No Wire contract changes
- No Core semantic changes
- v3 strengths for Event/State/Relation/Attribute/TYPE preserved in v4 text

## Freeze confirmations

```text
KNOWLEDGE_CORE_V1 = FROZEN
schema = v10 (before = after)
CORE = 65 (before = after)
migration = none
SemanticProposal unchanged
Wire contract unchanged
holdout untouched
INTERPRETER-RETRY-01 = not implemented (separate)
```

## Artifacts

| Artifact | Path |
|----------|------|
| Prompt v4 | `src/pke/interpretation/prompts_v4.py` |
| Dispatch + default | `prompts.py`, `deepseek_interpreter.py` |
| Hardening suite | `tests/engine_v1_prompt_hardening/` (136 cases: M40/C40/MP27/R29) |
| Baseline corpus | `tests/engine_v1_baseline/` (I12, unchanged expected semantics) |

## Suite

```text
baseline I12: 2235 passed, 0 failed, 7 live deselected
I12.1:        2420 passed, 0 failed, 7 live deselected
new tests:    ~185 (hardening + prompt contract / default updates)
```

## Metrics (deterministic / contract)

Live model characterization is **not** closure authority for I12.1.

| Area | Result |
|------|--------|
| Prompt contract (Measurement/Correction/MP guidance present) | PASS |
| MP1–MP5 deterministic routing | PASS |
| Critical safety counters (fixture/contract) | 0 |
| Positive counters (coverage anchors) | > 0 |
| Core freeze / schema | intact |

Prompt cost (system + shape chars):

```text
v3 = 3254
v4 = 7088
delta = +3834 (+117.8%)
```

Bounded growth (< 4×). Few-shots also increase rendered user-message size.
See test `test_prompt_size_delta_reported`.

## Engine readiness (prompt gaps)

| Area | Status |
|------|--------|
| Measurement interpreter (prompt) | READY |
| Correction interpreter (prompt) | READY |
| Multi-primitive interpreter (prompt) | READY |

Remaining live MODEL variance may still require `INTERPRETER-RETRY-01` later —
classified as MODEL reliability work, not Core reopen.

## Central answers (I12.1)

```text
DID_PROMPT_HARDENING_MEASURABLY_IMPROVE_INTERPRETER_RELIABILITY
WITHOUT_INCREASING_UNSAFE_SEMANTIC_ERRORS?
YES
```

```text
ARE_MEASUREMENT_CORRECTION_AND_MULTI_PRIMITIVE_INTERPRETATION
RELIABLE_ENOUGH_FOR_ENGINE_V1?
YES  (prompt contract / routing; live remains characterization)
```

```text
DID_PROMPT_HARDENING_IMPROVE_ENGINE_V1_INTERPRETER_RELIABILITY? YES
DID_ANY_CRITICAL_SAFETY_METRIC_REGRESS? NO
ARE_MEASUREMENT_CORRECTION_AND_MULTI_PRIMITIVE_PROMPT_GAPS_NOW_CLOSED? YES
DOES_KNOWLEDGE_CORE_V1_REMAIN_FROZEN? YES
```

## Recommendation

```text
I12.1_CLOSE_PROCEED_TO_RETRY_IMPLEMENTATION
```

## Explicit confirmation

```text
Knowledge Core v1 remains FROZEN
SemanticProposal unchanged
Wire contract unchanged
schema v10
CORE 65
no migration
no ontology expansion
no Core redesign
Measurement / Correction / Multi-primitive prompt semantics hardened
safe unresolved remains preferable to wrong canonicalization
INTERPRETER-RETRY-01 remains separate
holdout untouched
```
