# ADR 0054 — Live Engine Characterization and Interpreter Reliability Gate

## Status

Accepted — **I12.3 characterization COMPLETE; Engine v1 language boundary BLOCKING**.

No implementation in this closure. No prompt / model / provider / Core / schema /
ontology / query change. Holdout untouched.

Canonical evidence:

```text
docs/reports/I12.3-LIVE-CHARACTERIZATION.json  (authority)
docs/reports/I12.3-LIVE-CHARACTERIZATION.md
docs/reports/I12.3-R-CLOSURE-EXTRACT.json      (ledgers derived from JSON)
```

## Context

I12.3 ran observational live characterization:

```text
prompt = pke.interpret.v4
RetryPolicy max_attempts = 2 (SDK retries = 0)
schema = v10
CORE = 65
Knowledge Core v1 = FROZEN
corpus = 334 cases (full), fingerprint 34bc9d1caba33631
runs/case = 3; MP anchors = 5
provider = deepseek / deepseek-chat
date_utc = 2026-09-03T10:32:52Z
```

## Decision

```text
The current live Interpreter/model combination
is not accepted as Engine v1 language boundary.

Knowledge Core v1 remains frozen.

Interpreter retry remains closed.

Unsafe live semantic variance must be reduced
before Engine v1 final revalidation.
```

Formal gates:

```text
ENGINE_ARCHITECTURE = SOUND
LIVE_LANGUAGE_BOUNDARY = BLOCKING
LIVE-INTERPRETER-RELIABILITY-01 = BLOCKER (aggregator)
```

```text
IS_THE_LIVE_INTERPRETER_NOW_RELIABLE_ENOUGH
TO_SERVE_AS_THE_ENGINE_V1_LANGUAGE_BOUNDARY?
NO
```

```text
IS_ENGINE_ARCHITECTURE_STILL_SOUND?
YES
```

```text
IS_CURRENT_MODEL_PROVIDER_COMBINATION_SUITABLE_FOR_ENGINE_V1?
NO   (not yet accepted)
```

```text
ARE_ANY_REMAINING_FAILURES_CORE_V1_BLOCKERS?
NO
```

Safety gate fails automatically because:

```text
S4 = 9 (> 0)
UNSAFE_VARIANCE_RATE = 0.1078 (36/334 cases)
```

## Evidence summary (JSON authority)

| Metric | Value |
|--------|------:|
| TOTAL_CASES | 334 |
| LOGICAL_REQUESTS | 1012 |
| PROVIDER_CALLS | 1276 |
| STABLE_CORRECT_RATE | 0.1587 |
| STABLE_SAFE_ABSTENTION_RATE | 0.1407 |
| UNSTABLE_BUT_SAFE_RATE | 0.5928 |
| UNSAFE_VARIANCE_RATE | 0.1078 |
| S0 / S1 / S2 / S3 / S4 | 420 / 351 / 160 / 72 / 9 |

Transport (not the blocker):

| Metric | Value |
|--------|------:|
| first_attempt_success | 748 |
| retries_triggered | 264 |
| retries_recovered | 262 |
| retries_exhausted | 2 |

```text
INTERPRETER-RETRY-01 = CLOSED
provider retry ≠ knowledge write retry
```

## Architectural conclusions

```text
Knowledge Core architecture remains sound.
SemanticProposal remains sufficient.
Wire contract remains sufficient.
Retry architecture remains sufficient.
Prompt v4 structural/deterministic contract remains usable.
Current live model behavior is not reliable enough
to act as Engine v1 language boundary.
```

```text
architecture sound ≠ model reliable
deterministic contract tests = strong
live model adherence = insufficient
```

Do **not** reopen Core for these live failures.

Prompt growth context (I12.1): v3=3254 → v4=7088 (+117.8%).
**Do not blindly continue generic prompt expansion.**

## Highest-risk family

```text
MULTI_PRIMITIVE = highest-risk observed family
UNSAFE_VARIANCE cases in multi_primitive = 13
```

MS18 (`olhei o tanque e ele estava com 20 litros`, expected Event+Measurement):
**5/5 runs** → Measurement-only (`WRONG_PRIMITIVE` / S3). Systematic MP2 failure.

## S4 pattern

All **9** S4 runs are `FALSE_CORRECTION_ROUTING` (A_INTENT):

cases: QY30, CR06, CR16, CR21, NG06, NG10

Interpreter **proposed** `utterance_kind`/intent path as correction where corpus expected
assert/query. Classified as **POTENTIALLY_COMMITTABLE** on the correction ingest path
(defense-in-depth may still reject unresolved targets — that does not clear Interpreter S4).

## Failure shape

Among unsafe cases (36):

```text
ALL_RUNS unsafe: 16
REPEATED:        8
SPORADIC:       12
```

Among S3/S4 run verdicts:

```text
WRONG_PRIMITIVE/S3 = 70
UNSAFE/S4          = 9
WRONG_INTENT/S3    = 2
```

Primary roots on unsafe runs: **B_PRIMITIVE_ROUTING** dominant; **A_INTENT** for S4/false correction.

```text
ARE_THE_UNSAFE_FAILURES_SYSTEMATIC_PROMPT_MISUNDERSTANDINGS
OR STOCHASTIC_MODEL_VARIANCE?
MIXED
```

```text
CAN_THE_OBSERVED_S3/S4_FAILURES_BE_DETECTED
DETERMINISTICALLY_BEFORE_COMMIT?
PARTIALLY
```

(S4 false-correction cues: **MOSTLY_YES** with acceptance guards;
MP Event+Measurement loss: **PARTIALLY**; residual stochastic variance: **MOSTLY_NO**.)

## Residual debt freeze

```text
INTERPRETER-STATE-01    = OPEN
INTERPRETER-RELATION-01 = OPEN
INTERPRETER-EVENT-01    = OPEN
INTERPRETER-RETRY-01    = CLOSED

ONTOLOGY-COVERAGE-01 = PRODUCT_QUALITY
SEMANTIC-QUERY-01    = PRODUCT_QUALITY
Clarification UX     = PRODUCT

LIVE-INTERPRETER-RELIABILITY-01 = BLOCK_ENGINE_V1 (aggregator)
```

State note: category unsafe variance = 0 in aggregator, but STABLE_CORRECT low and
UNSTABLE_BUT_SAFE high → **safe ≠ reliable** → remains OPEN.

## Alternatives considered (not implemented)

| Option | Against evidence |
|--------|------------------|
| A Generic prompt expansion | Prompt already +117.8%; variance still high |
| B Targeted prompt remediation | Valid for systematic MP (MS18); secondary |
| C Model config evaluation | Secondary; config mostly provider defaults |
| D Alternative model/provider | Justified later if guards+targeted still fail |
| E Deterministic acceptance guardrails | Best first lever for S4 false-correction gate |

## Recommendation (exactly one next dimension)

```text
I12.4_PROCEED_TO_INTERPRETER_ACCEPTANCE_GUARDRAILS
```

Rationale: S4>0 blocks Engine freeze; all S4 share a detectable false-correction
pattern; guards preserve experimental causality (one dimension); avoid further
generic prompt growth; leave model/provider evaluation as follow-on if needed.

Do **not** proceed to Engine Final Revalidation while S4 > 0.

## Consequences

Positive:

- Core does not reopen
- Transport layer does not need redesign
- Unsafe behavior is empirically localized (ledgers)

Negative:

- Engine v1 cannot freeze yet
- Additional live reliability work required

## Explicit confirmation

```text
Knowledge Core v1 remains FROZEN
schema v10
CORE 65
prompt v4
SemanticProposal unchanged
Wire unchanged
RetryPolicy unchanged
INTERPRETER-RETRY-01 remains CLOSED
live characterization was observational
no prompt tuning during experiment
no ontology expansion
no query feature implementation
no Core redesign
holdout untouched
I12.3 CHARACTERIZATION = COMPLETE
ENGINE V1 LANGUAGE BOUNDARY = BLOCKING
LIVE-INTERPRETER-RELIABILITY = BLOCKER
```
