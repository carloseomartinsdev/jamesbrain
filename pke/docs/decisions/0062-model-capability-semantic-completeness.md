# ADR 0062 — Model Capability Re-evaluation for Semantic Completeness (I12.11)

## Status

**CLOSED — evaluation complete**

```text
I12.6 = CLOSED (historical only; ranking not reused)
I12.11 = NEW EVALUATION UNDER BETTER-INSTRUMENTED ENGINE
```

## Context

I12.10 closed structured proposal execution readiness:

- zero-materializable safe outcomes controlled
- false Event canonicalization eliminated
- `SAFE_HANDLED_INTERACTION_RATE ≈ 91.7%`
- `USEFUL_KNOWLEDGE_CAPTURE_RATE ≈ 57.6%` (I12.10 corpus)
- MP1 useful capture ≈ 20% with safe handling ≈ 100%

Principal residual blocker: **SEMANTIC_COMPLETENESS** (execution-critical slots omitted).

I12.6 ranked models **before** Event preservation / safe partial / execution-readiness instrumentation.
I12.11 re-evaluates available model/provider configurations under the post-I12.10 Engine, with primary metric:

```text
USEFUL_KNOWLEDGE_CAPTURE_RATE
```

Safety measured separately and used as veto.

## Decision

1. Vary **only** model/provider configuration.
2. Keep prompt v4, SemanticProposal, Wire, RetryPolicy, Correction Guard,
   execution readiness, router, persistability, materialization, Core identical.
3. No prompt-per-model, no multi-pass, no silent production switch, no Core/schema change.
4. Material win threshold frozen a priori:

```text
USEFUL_KNOWLEDGE_CAPTURE_RATE >= baseline + 10 pp
AND no safety regression
```

MP1 material improvement discussion threshold: `MP1_USEFUL_CAPTURE_RATE >= 70%`.

## Candidates (callable in this environment)

| ID | Provider | Model | Status |
|----|----------|-------|--------|
| baseline_deepseek_chat | deepseek | deepseek-chat | evaluated (baseline) |
| deepseek_reasoner | deepseek | deepseek-reasoner | evaluated |
| openai_gpt4o_mini | openai | gpt-4o-mini | NOT_EVALUATED — no `OPENAI_API_KEY` |
| openai_gpt4o | openai | gpt-4o | NOT_EVALUATED — no `OPENAI_API_KEY` |

## Frozen controls

See `docs/reports/i1211_artifacts/FREEZE.json`.

```text
prompt = pke.interpret.v4
schema = v10
CORE = 65
Knowledge Core v1 = FROZEN
holdout = untouched
sdk retries = 0
Interpreter RetryPolicy unchanged
temperature/top_p/max_tokens = provider default (unset by PKE)
```

## Results (summary)

| Candidate | Safe handled | Useful capture | Exec-ready | Invented | POST_S4 | Verdict |
|-----------|-------------:|---------------:|-----------:|---------:|--------:|---------|
| baseline_deepseek_chat | 90.4% | 37.0% | 38.1% | 3 | 0 | CURRENT_BASELINE (no winner) |
| deepseek_reasoner | 34.5% | 12.1% | 15.5% | 220 | 0 | REJECTED_SAFETY |

```text
BEST_CANDIDATE = NONE
CURRENT_BASELINE_REMAINS = YES
```

MP1 (N=10 each): both candidates keep Event+Measurement on proposal with **missing subject**;
baseline useful capture 10% (edge empty-subject partial), reasoner 0%. Neither reaches 70%.

Proposal expressiveness is demonstrated by MP2/MP3/MP5 capture when slots are filled —
failure mode is **model omission / invention**, not missing schema fields.

## Consequences

- Do **not** adopt deepseek-reasoner.
- Do **not** switch production default in I12.11.
- Do **not** reopen I12.6.
- Next increment preference: model capability strategy (additional providers/models when credentials exist)
  and/or Event completeness strategy for subject/entity gaps — without inventing from raw text.

Full metrics: `docs/reports/I12.11-MODEL-CAPABILITY-SEMANTIC-COMPLETENESS.md`.
