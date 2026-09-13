# ADR 0084 — LLM Response Presenter and Conversational Boundary

## Status

**Accepted** — incremental on ADR 0074 / 0081. Does not reopen:

- ADR 0081 — Language Independence
- ADR 0082 — Class vs Instance
- ADR 0083 — Possessive + Intrinsic Entity Properties

Does not change Interpreter prompts or PKE Engine / resolver / query / materializer semantics.

## Context

PKE already returns the right structured knowledge. Product templates then verbalize it as:

```text
Sim.
Encontrei Luna.
Não encontrei um registro sobre isso.
Certo. Registrei essa informação.
```

Those sentences are epistemically honest and operationally correct. They are not conversational. The user talks to JAMES, not to JAMES's database.

Putting prettier sentences inside the PKE Engine would collapse presentation into knowledge. Reusing the Interpreter prompt would collapse meaning into speech.

## Decision

```text
Interpreter  →  meaning   (language → Semantic IR)
PKE          →  knowledge (IR → structured result)
Presenter    →  language  (structured result → speech)
```

> **The Presenter may express knowledge, but may not create knowledge.**

The Presenter is a jamesCore orchestration concern (`jamescore.presentation.ResponsePresenter`). It is capability-agnostic. PKE is the first producer of structured results; Weather and other capabilities may follow the same envelope later.

PKE continues to return structured results. Existing Product templates remain the deterministic fallback when the Presenter is unavailable, times out, or returns a malformed / unfaithful reply.

### Contract

Input is derived from the existing PKE/jamesCore envelope (no parallel knowledge DTO):

```text
user_message
structured_result.status
structured_result.operation / kind
structured_result.value / values / matched_entities
structured_result.relation_answer
clarification candidates
error code
minimal conversation snippets (pronouns / tone only)
```

The structured result is the only factual authority for that turn. The user message is linguistic context.

Product `data` is enriched with `status` (`answered`, `no_results`, `committed`, …) and matched names so the Presenter can distinguish **false** from **no_results** without parsing templates. Templates themselves are unchanged.

### Prompt

Own prompt (`PRESENTER_SYSTEM_PROMPT`). Not the Interpreter prompt. Same provider/model family is allowed; roles stay separate.

### Epistemic invariants

| Structured status | Spoken meaning |
|---|---|
| `answered` + value | State the fact. Do not add unattested properties. |
| `relation_answer=true` | Confirm; mention matched names when present. |
| `relation_answer=false` | Negative knowledge. Never “ainda não sei”. |
| `no_results` | Absence of knowledge. Never a factual “Não.” |
| `unknown` | Uncertainty. Do not coerce to yes/no. |
| `needs_clarification` | Natural question; list candidates. |
| `insufficient` | Ask for the missing piece. |
| `unsupported` | Did not understand / cannot do it. Distinct from not knowing. |
| `error` | Operational failure. Never “ainda não sei”. |
| `committed` | Knowledge acknowledgement (“Entendi”, “vou lembrar”). |

Ordinary conversation must not expose implementation terms (`registro`, `PKE`, `entidade`, …) unless the user asks a technical question.

### Fallback and observability

Presenter failure must not discard a successful PKE result. Logs:

```text
stage=presenter_request
stage=presenter_response
```

Fields: `request_id`, `provider_request_id`, `model`, `latency_ms`, `status`, `fallback_used`.

## Consequences

- JAMES sounds like someone who knows or does not know something.
- PKE remains the knowledge authority.
- Interpreter remains the meaning authority.
- A second LLM call is added on the conversational path; timeout/fallback keeps the product usable.
