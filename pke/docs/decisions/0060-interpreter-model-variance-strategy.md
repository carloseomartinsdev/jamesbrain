# ADR 0060 — Interpreter Model Variance and Reliability Strategy (I12.9)

## Status

**CLOSED — characterization complete; strategy selected**

## Context

After I12.8 rejected prompt v5-event:

- Downstream Event preservation (I12.7.1) is validated.
- Residual unreliability is Interpreter-side.
- MP1 was misread as “Event omission” when many failures are **structured incompleteness** or **total wire rejection**.

I12.9 characterizes variance without changing Core, Wire, SemanticProposal, or active prompt (v4).

## Failure taxonomy (I12.9)

Primary classes per run:

| Class | Meaning |
|-------|---------|
| CORRECT | Valid proposal + engine outcome matches expectation |
| SAFE_ABSTENTION | Guard/abstention; no unsafe commit |
| SEMANTIC_OMISSION | Valid proposal missing expected primitive/role |
| WRONG_SEMANTIC_DECISION | Valid proposal, wrong primitive routing |
| STRUCTURED_OUTPUT_INVALID | No valid SemanticProposal |
| NORMALIZATION_FAILURE | Transport/normalization failed |
| CONCEPT_RESOLUTION_REJECTION | Valid proposal but nothing wireable |
| TRANSPORT_FAILURE | Provider/empty response |
| DOWNSTREAM_INFORMATION_LOSS | Proposal had semantics; engine lost them |

Stages: S0 provider → S1 normalization → S2 proposal → S3 routing → S4 concept resolution → S8 outcome.

## Live characterization (I12.9, n=251, prompt v4)

| Metric | Value |
|--------|------:|
| VALID_SEMANTIC_PROPOSAL_RATE | 96.4% |
| VALID_AND_SEMANTICALLY_USEFUL_PROPOSAL_RATE | 54.6% |
| FIRST_ATTEMPT_VALID_PROPOSAL_RATE | 88.4% |
| PROPOSAL_INTERNAL_INCONSISTENCY_RATE | 0.8% |
| DOWNSTREAM_INFORMATION_LOSS | **0** |
| PROPOSAL_DISAGREEMENT_RATE (dual-sample) | **0%** (46 pairs) |

Primary failure distribution (live):

- CORRECT 51%
- CONCEPT_RESOLUTION_REJECTION 41%
- STRUCTURED_OUTPUT_INVALID 5%
- Other <3%

## MP1 forensic (critical)

Utterance: `"Medi a temperatura e deu 95°C."` — 10 fresh runs (5×A + 5×B dual-sample):

| Outcome | Count | Mechanism |
|---------|------:|-----------|
| CORRECT (M committed, E non-materialized) | 1 | `subject=temperatura` present |
| CONCEPT_RESOLUTION (total fail) | 9 | Valid E+M proposal but **`subject=null`** → `_measurement_wire` None + Event partial → `wire=None` |

**MP1 is NOT primarily raw Event omission.** In 9/10 runs the model emits **Event + Measurement** assertions with occurrence evidence. Failure is **missing measured-entity subject**, making nothing wireable.

Historical I12.6 MP1 proposals: same pattern (`subject: null`).

I12.7-R/I12.8 artifacts with null raw were runner capture gaps on exception path, not evidence of absent provider JSON.

### §7 audit (representative MP1 resolution failure)

| Question | Answer |
|----------|--------|
| Provider returned structured semantics? | **YES** |
| Normalization succeeded? | **YES** |
| SemanticProposal validated? | **YES** |
| Resolver rejected valid partial proposal? | **NO** — nothing was materializable; partial Event cannot wire alone; Measurement blocked by missing subject |

## Dominant failure class

**MIXED**:

1. **Structured proposal incompleteness** (esp. Measurement entity/subject) — model variance.
2. **Engine all-or-nothing wire gate** when zero primitives materialize — architectural strictness, not silent downstream loss.

Not primarily wrong primitive routing. Downstream loss ≈ 0 post-I12.7.1.

## Proposal-side detection (§50–51)

**PARTIALLY YES** — SemanticProposal exposes:

- `measurement_semantics` + numeric fields without `subject` → incomplete for wire.
- `change_semantics` + `action_expression` without Event in assertions → rare (router derives Event).

**MP1 Event omission with proposal-side evidence?** **NO** (most failures still encode Event). **SOMETIMES** historically when no parseable proposal.

## Strategy evaluation

| Strategy | Safety | Reliability | Cost | Risk | Verdict |
|----------|--------|-------------|------|------|---------|
| SINGLE_PASS_ACCEPT (current) | High | Moderate | Low | Low | Baseline |
| SINGLE_PASS + consistency abstention | High | Moderate+ | Low | Low | **Recommended next** |
| DUAL_PASS disagreement | High | Unclear | 2× | Medium | **Not justified** (0% disagreement) |
| Targeted retry on contract failure | High | Possible | Low+ | Low | Candidate follow-up |
| Model escalation | Uncertain | Low (I12.6) | High | Medium | Not recommended |
| Majority vote | Low epistemic | Poor | 3×+ | High | **Rejected** |
| Semantic union of proposals | Unsafe | — | — | High | **Forbidden** |

No second Interpreter on raw text. No assertion union without epistemic rule.

## Decision

**Recommendation:** `I12.9_CLOSE_PROCEED_TO_STRUCTURED_PROPOSAL_RELIABILITY_HARDENING`

Next increment should:

1. Deterministically detect **materialization-precondition gaps** on valid proposals (e.g. Measurement without measured entity).
2. Replace hard `concept_resolution` total failure with **safe abstention / clarification** where appropriate.
3. **Not** invent missing subject/Event from raw text.

Dual-sample data does **not** support multi-pass for disagreement (0% on 46 pairs).

## Single-proposal architecture (§3)

**INCONCLUSIVE leaning YES with completeness gate** — architecture works when proposal is structurally complete (~55% useful). Incomplete proposals cause avoidable total failure.

## Core freeze

Knowledge Core v1 FROZEN · schema v10 · CORE 65 · holdout untouched.

## Debts

| Debt | Status |
|------|--------|
| INTERPRETER-EVENT-01 | PARTIALLY_MITIGATED (MP1 reframed: completeness not omission) |
| INTERPRETER-STATE-01 | OPEN |
| INTERPRETER-RELATION-01 | OPEN |
| LIVE-INTERPRETER-RELIABILITY-01 | PARTIALLY_MITIGATED |

Highest remaining blocker: **STRUCTURED_PROPOSAL_RELIABILITY**
