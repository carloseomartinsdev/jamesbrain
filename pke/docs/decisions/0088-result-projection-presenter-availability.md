# ADR 0088 — Structured Result Projection and Presenter Availability Boundary

## Status

**Accepted** — incremental on ADR 0084 / 0087. Does not reopen:

- ADR 0081 — Language Independence
- ADR 0082 — Class vs Instance
- ADR 0083 — Possessive + Intrinsic
- ADR 0085 — Named non-binding class hints
- ADR 0086 — Multi-claim ingest
- Interpreter prompts
- EntityResolver
- Measurement ingest / materializer

## Context

A live query `qual o peso da Luna?` produced:

```text
Engine ............. answered
Presenter request .. no_results / kind=absence
Presenter .......... unavailable / fallback
```

Those are two independent failures.

1. **Projection loss.** Ask/Engine had found a measurement (often `temporally_unknown` with numeric values only on `candidate_observations`). Product `render_query` only inspected `measurement_values` / other populated lists and fell through to `status=no_results`. Truthiness (`if not value`) would have made `0` and `false` look like absence as well.
2. **Presenter availability.** jamesCore copied the Interpreter API key from PKE `.env` but aborted hydration as soon as a key existed, so `DEEPSEEK_MODEL` (working Interpreter model, e.g. `deepseek-flash`) was not applied. Presenter then defaulted to `deepseek-chat`. Transport errors were collapsed to `presenter llm unavailable`.

Fallback remained correct as a safety net, but it became the normal path and restated Product templates such as “Encontrei 4.” / “Não encontrei um registro sobre isso.”

## Decision

```text
Engine / Ask     → knowledge (status, kind, values)
Response projection → public structured result
Presenter        → speech (LLM) or structured fallback
```

> **Engine result ≠ Presenter result.**

> **Presentation failure must not alter knowledge semantics.**

If the Engine knows the answer, no later layer may rewrite it as absence. If the Presenter fails, the reply may be less natural, but it must stay factually aligned with the structured result.

### Projection

Product `result_projection` is the contract mapper. Ask status is authoritative:

| Engine/Ask result | Structured `kind` | Structured `status` |
|---|---|---|
| relation yes/no | `relation` | `answered` (`false` stays answered) |
| attribute value | `attribute` | `answered` (`0` stays answered) |
| intrinsic name | `attribute` / `intrinsic_property` | `answered` |
| measurement value | `measurement` | `answered` |
| state | `state` | `answered` |
| Ask `no_results` | `absence` | `no_results` |
| ambiguous | clarification / unknown | not absence |
| error | `error` | `error` |

Absence is only projected when Ask/Engine status is actually `no_results` (or there is no query result and Ask is not `answered`). Scalars are tested with `is not None`, never with truthiness.

QueryEngine still reports epistemic `measurement_status` unchanged. It now also exposes observable numeric identities from `candidate_observations` when `groups` is empty, so temporally unknown observations (weight without `observed_at`) remain visible to projection.

Stage `response_projection` logs source vs projected status/kind/value/unit. Engine stage logs `answer_kind` plus a compact `result` (dimension, numeric_value, unit) — not full internal graphs.

### Presenter

Presenter keeps its own prompt and role. It may reuse the Interpreter provider family (`DEEPSEEK_*`) with independent `PRESENTER_MODEL` / `PRESENTER_API_KEY` / `PRESENTER_BASE_URL`. Missing Presenter fields hydrate from PKE `.env` **per key**, including model, even when an API key is already in the process environment.

Health reports configuration only (enabled, model, base URL, credentials present). No startup LLM call.

Fallback remains mandatory. When structured result has enough facts, fallback uses that contract (e.g. `A Luna pesa 4 kg.`, `Pelo que sei, não.`, `Ainda não sei isso.`, `Entendi.`) and does not reread `raw_input`. Capability templates are last resort.

jamesCore envelope `data` / operation outcome stay the knowledge status. Presenter outcome lives in presenter trace (`fallback_used`, provider error). A failed presentation never rewrites `answered` into `no_results` or `error`.
