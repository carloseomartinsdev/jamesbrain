# ADR 0057 — Engine v1 Model and Provider Evaluation (I12.6)

## Status

Accepted — **I12.6 Stage A complete** (see closure report for live numbers).

```text
Stage A executed: baseline_deepseek_chat + deepseek_reasoner
OpenAI candidates: NOT_EXECUTED_NO_CREDENTIAL
Stage B: not run (no VIABLE superior candidate)
```

```text
ENGINE V1
MODEL EVALUATION
PROVIDER EVALUATION
CONTROLLED LIVE EXPERIMENT
```

No Knowledge Core change. No schema/migration. No CORE expansion.
No SemanticProposal / Wire / router / guard / prompt change.
No production model switch in this increment.

## Context

After I12.3–I12.5:

- Correction S4 blocked deterministically
- Explicit Event+Measurement assertions preserved when already on proposal
- Residual Engine language-boundary risk attributed primarily to **MODEL_VARIANCE**

I12.6 isolates model/provider as the sole experimental variable.

## Experimental controls

Frozen a priori (`tests/model_provider_evaluation/freeze.py` +
`docs/reports/i126_artifacts/FREEZE.json`):

```text
prompt = v4
SemanticProposal / Wire / Correction Guard / MP preservation / RetryPolicy unchanged
temperature/top_p/max_tokens = provider default (identical policy for all candidates)
sdk/http retries = 0
application max attempts = 2
effective max provider calls <= 2
schema v10 / CORE 65 / Knowledge Core FROZEN / holdout untouched
```

Thresholds locked before first live call:

```text
POST_ENGINE_S4 = 0
POST_ENGINE_UNSAFE_VARIANCE <= 1%
critical correction safety = 100%
MP1–MP5 post-engine safety = 100%
intent/primitive/temporal targets as in freeze module
```

## Candidates

| ID | Provider | Model | Role |
|----|----------|-------|------|
| baseline_deepseek_chat | deepseek | deepseek-chat | baseline |
| deepseek_reasoner | deepseek | deepseek-reasoner | alt_same_provider (MODEL_EFFECT) |
| openai_gpt4o_mini | openai | gpt-4o-mini | alt_other_provider |
| openai_gpt4o | openai | gpt-4o | alt_other_provider |

OpenAI candidates require `OPENAI_API_KEY`. Experimental adapter:
`src/pke/llm/openai_compatible.py` (not production default).

## Corpus

Stage A discriminative set (~80–120): all I12.3 unsafe cases, MP1–MP5,
Correction S4 patterns, stratified Event/State/Relation/Attribute/Measurement/
Query/Temporal/Ambiguity/Unknown.

## Dual evaluation

```text
RAW_MODEL_OUTCOME
POST_ENGINE_ACCEPTANCE_OUTCOME  (guards + routing + resolution)
```

Raw false Correction may be S4 while post-engine is safe abstention if the
Correction Acceptance Guard blocks it. Both are reported.

## Persistence

```text
docs/reports/i126_artifacts/{candidate}.jsonl
docs/reports/i126_artifacts/FREEZE.json
docs/reports/I12.6-MODEL-PROVIDER-EVALUATION.json
```

Resume: completed `(candidate, case, run)` not re-called.
Raw provider response + validated proposal retained for development characterization.

## Decision rule

Priority: Safety → Semantic reliability → Transport → Coverage → Latency → Cost.

Statuses: `REJECTED_SAFETY` | `REJECTED_RELIABILITY` | `VIABLE` | `PREFERRED` | `INCONCLUSIVE` | `NOT_EXECUTED_NO_CREDENTIAL`.

No silent production promotion.

## Consequences

See `docs/reports/I12.6-MODEL-PROVIDER-EVALUATION-CLOSURE.md` for Stage A numbers.

### Key findings

1. **POST_ENGINE_S4 = 0** for both DeepSeek candidates — Correction Guard effective.
2. **Neither candidate VIABLE** — POST unsafe variance 18–26% vs <=1% threshold; stable correct ~24%.
3. **BEST_CANDIDATE = NONE** — reasoner reduces some S3/unsafe but no material stable-correct gain; ~8× latency.
4. **MS18 proposals now captured** — explicit Event semantics present; post-engine loses Event → **MIXED** blocker (model + downstream Event routing/canonicalization).
5. **MP1–MP4 raw = multi CORRECT** on both models; post-engine systematic Event loss.

### Recommendation

```text
I12.6_CLOSE_PROCEED_TO_EVENT_ROUTING_HARDENING
```

Not candidate adoption. Not final revalidation.
