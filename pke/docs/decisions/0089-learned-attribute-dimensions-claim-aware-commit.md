# ADR 0089 — Learned Attribute Dimensions and Claim-Aware Write Outcome

## Status

**Accepted** — incremental on ADR 0084 / 0086 / 0087 / 0088. Does not reopen:

- ADR 0081 — Language Independence
- ADR 0082 — Class vs Instance
- ADR 0083 — Possessive + Intrinsic
- Interpreter prompts
- EntityResolver
- CORE attribute registry contents (`color`, `name`, …)

## Context

A live write `a luna tem pelos brancos` produced a correct Interpreter claim:

```text
kind=attribute  subject=Luna  predicate=fur color  value_text=branco
```

The PKE then dropped it:

```text
execution_outcome = valid_execution_incomplete
unsupported_attribute_dimension
additional_attributes = []
materializer committed = 0  deferred = 1
Engine status = committed
Presenter status = committed
```

Two independent failures sat on top of each other:

1. **Closed attribute vocabulary.** `_attribute_from_claim` required `is_registered_dimension`. Unknown structured predicates were discarded instead of learned, unlike `entity.learned.*` / `relation.learned.*`.
2. **False `committed`.** Ingest returned `IngestStatus.COMMITTED` after a successful transaction even when the user's semantic claim was not materialized (entity reuse / raw_input / no exception).

A third, already-known Presenter availability issue still collapsed provider errors; fallback said "Entendi." whenever the Product typed the write as committed.

## Decision

### Learned attribute dimensions

Interpreter structured predicates that are not CORE dimensions become:

```text
Interpreter predicate
        ↓
canonicalização (slug + CORE alias exact match)
   ↙          ↘
 yes          no
 ↓             ↓
attribute.*   attribute.learned.{slug}
```

Example: predicate `fur color` → `attribute.learned.fur_color`.

Identity is the Interpreter's semantic predicate (`fur color` / optional `predicate_key`), not `raw_input` and not a PT/EN/ES glossary. CORE aliases always win (`color` stays `color`; `fur color` does not substring-match `color`).

Values are stored as given (`value_key` if present, else `value_text`). The PKE does not translate `branco` → `white`.

Learned specs live in a runtime overlay. The CORE `ATTRIBUTE_DIMENSION_REGISTRY` tuple remains frozen. Restart hydrates from `entity_attributes.dimension_key` and republishes the overlay.

### Semantic IR

Optional fields on `SemanticClaim`:

- `predicate_key` — Interpreter-owned dimension identity (e.g. `fur_color`)
- `value_key` — Interpreter-owned value identity (e.g. `white`)

No parallel contract. Surfaces (`predicate`, `value_text`) remain for provenance.

### Canonicalization

1. Try `predicate_key`, then `dimension`, then `predicate`.
2. Exact CORE alias / key wins.
3. Else slug via existing `slug_from_expression` (normalize + `[^a-z0-9]+` → `_`).
4. Prefix `attribute.learned.`.
5. Do not learn from `raw_input` or from `attribute_expression` alone (preserves E1.3 `signo Áries` → `unsupported_attribute_dimension`).
6. Query uses the same identity (`learn=False` still slugs; does not invent CORE `color` from `fur color`).

### Deduplication

Same slug → same overlay spec / ontology concept (`ext:attribute.learned.{slug}`). CORE keys and CORE aliases are never overwritten. Repeated writes of the same learned dimension reuse the key; `singleton_current` closes prior current rows.

`fur_color` is **not** equivalent to `color`. Hierarchy / `is_a` is a future increment.

### Materializer

Learned attribute claims overlay onto existing `IrAttribute` slots. `dimension_concept_id = ext:attribute.learned.{slug}`. Tally `committed` for Interpreter claims counts fact rows (attribute / relation / measurement / state / event), not reused entities. Classification-only create may count `created_entity_ids` when there are no fact slots.

### Claim-aware write outcome

When the Interpreter supplied `claim_report.received > 0`:

| tally | status |
|---|---|
| committed > 0, deferred == 0 | `committed` (assumed-drop `rejected` does not force partial) |
| committed > 0, deferred > 0 | `partial` |
| committed = 0, deferred > 0 | `deferred` |
| committed = 0, otherwise | `unsupported` |

`committed` means at least one semantic fact was materialized. Entity reuse, raw_input persistence, and exception-free transactions are not enough.

Without Interpreter claims, the legacy post-transaction `committed` path is unchanged.

Enums reused: `IngestStatus.PARTIAL` / `DEFERRED`; `ApiOperationOutcome.PARTIAL` / `DEFERRED`.

### Presenter

The Presenter verbalizes `structured_result.status`. It must not invent success. Deterministic fallback:

- committed → `Entendi.`
- partial → `Entendi parte disso, mas não consegui guardar tudo.`
- deferred / write unsupported → understood the meaning, could not store it

Provider diagnostics log `presenter_provider`, `presenter_model`, `attempt`, `exception_class`, `provider_error_code`, `safe_error_message`, `latency_ms`, `fallback_reason` — never API keys.

Product write envelope carries `status` + `claims` tally. `response_projection` logs ingest as well as ask.

### Logging

Stages kept / extended: `llm_response`, `normalize`, `proposal`, `repair`, `claims`, `assessment`, `canonical`, `entity_resolution`, `materialization`, `engine`, `response_projection`, `presenter_request`, `presenter_response`.

`claims` records identity before/after canonicalization (`predicate`, `canonical_dimension`, `dimension_source`, `value`). `materialization.claim_results` records `committed` / `deferred` with `attribute_id` / `entity_id` when persisted.

## Consequences

- New everyday attributes do not require a code change to the CORE registry.
- `fur_color` does not imply `color`. Hierarchy/equivalence is a future increment.
- Interpreter still owns language: if two languages emit different predicates, they learn different keys unless `predicate_key` is shared.
- Product and jamesCore gained `partial` and `deferred` write outcomes.

## Invariants

> The LLM interprets language. The PKE interprets, organizes, relates, persists, and queries knowledge.

> If the PKE understood a structured concept it did not previously know, it tries to learn it generically rather than requiring every possible fact to be pre-registered.

> `committed` means knowledge was actually materialized — never merely that the pipeline ran without an exception.

## Limitations

- Possessive first-mention create remains vehicle-scoped (ADR 0083 / E1.2). Multi-claim house/notebook possessive ingest can still reject with `entity.contextual_unresolved`; named subjects (Luna, notebook as named) learn attributes.
- `kind_hint=organization` + `class_hint=company` still prefers CORE `entity.organization` when the lemma aliases to a kind — not reopened here.
- I11.8 PI1 (`trabalha` without CORE alias) is aligned with learned *relations* (`relation.learned.trabalha`), not dropped. That contract predates this ADR.
- Learned attribute labels are presentation only (slug with underscores → spaces, or ontology `presentation.label`). Portuguese Inspector copy is not stored as identity.
