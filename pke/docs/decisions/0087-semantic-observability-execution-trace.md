# ADR 0087 — Semantic Observability and Execution Trace Expansion

## Status

**Accepted** — incremental on ADR 0081 / 0084 / 0086. Does not reopen:

- ADR 0081 — Language Independence
- ADR 0082 — Class vs Instance
- ADR 0083 — Possessive + Intrinsic Entity Properties
- ADR 0084 — LLM Response Presenter
- ADR 0085 — Named Entity Resolution with Non-Binding Class Hints
- ADR 0086 — Semantic Decomposition & Multi-Claim Ingest

Filename `0086-semantic-observability-…` was requested; **0086 is already used**,
so this decision is **0087**.

Does not change Interpreter prompts, resolver outcomes, materializer
persistence, or Presenter speech. Observability-only.

## Context

The request log already recorded:

```text
llm_response → normalize → proposal → repair → assessment
→ query_resolution? → canonical → engine
```

That is enough to catch many interpretation failures. It is not enough to
answer, in one correlated file:

> What did the user mean?
> What did the PKE do with that meaning?
> How did JAMES present the result?

`engine` nested only **counts** of persisted objects. Entity resolution
strategy / candidates / `no_match` vs unresolved were invisible. The
Presenter wrote INFO lines without the structured payload it actually used.
`claims` from ADR 0086 had no stage.

## Decision

Request logs are **semantic diagnostics**, not only infrastructure diagnostics.

Each executed layer logs what it received, decided, and produced. Stages that
did not run are omitted. Failures to write a stage do not abort the operation.

```text
llm_response
normalize
proposal
repair
claims?                 # only when SemanticProposal.claims is non-empty
assessment
query_resolution?       # queries
canonical
entity_resolution?      # only when EntityResolver ran
engine                  # only when IngestService / AskService ran
materialization?        # writes that persisted
presenter_request       # jamesCore
presenter_response      # jamesCore
```

Correlation IDs already in the request (`client_request_id`, `pke_request_id`,
`interpreter_request_id`, `conversation_id`, `user_message_id`) are reused.
No new IDs are minted for logging.

`claim_id` values `c1`, `c2`, … are **trace-local labels** for the claims
stage, not persistent identifiers.

`entity_resolution.outcome`:

| outcome | meaning |
|---|---|
| `resolved` | concrete entity id |
| `ambiguous` | selector valid, multiple candidates |
| `no_match` | selector valid, zero candidates (`possessive_no_match`, `query_entity_not_found`, …) |
| `create_candidate` | ingest will create |
| `unresolved` | resolution failed for another reason |

`engine` records path, status, resolved ids, and a compact `value` when the
ask result already has one. It does not repeat materialization objects.

`materialization` lists persisted entities / relations / attributes /
measurements from the UnitOfWork already in hand. No extra database query.

Presenter stages live in jamesCore. They log `llm_payload.structured_result`
and the delivered text — not prompts, secrets, graph dumps, or full history.

Truncation is explicit: `truncated`, `original_size`, `logged_size` (cap
65_536). Silent `…[truncated]` is not used.

## Consequences

- Old log files remain readable. New stages appear on later requests.
- Knowledge Inspector linking remains provenance-based (`request_id` already
  on the file). Heuristic name matching is not introduced.
- A future Query Trace UI can parse stages in order without re-deriving
  semantics from `raw_input`.
- Logging must not re-read `raw_input` to explain a later stage (ADR 0081).
