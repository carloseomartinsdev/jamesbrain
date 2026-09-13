# ADR 0085 — Named Entity Resolution with Non-Binding Class Hints

## Status

**Accepted** — incremental on ADR 0082 / 0083. Does not reopen:

- ADR 0081 — Language Independence
- ADR 0082 — Class vs Instance
- ADR 0083 — Possessive + Intrinsic Entity Properties
- ADR 0084 — LLM Response Presenter

Does not change Interpreter prompts v4/v5. Does not add a type hierarchy
(`cat ⊂ animal`). Does not add linguistic rules.

## Context

`quanto a Luna pesa?` already arrived as language-independent IR:

- `reference_kind = named`
- `text = Luna`
- `class_hint → entity.learned.animal`
- `measurable_dimension_key = weight`

Luna already existed as `entity.learned.cat`. `_lexical_candidates` treated
`type_hint` as a hard filter (`canonical_name = Luna AND type = animal`) and
dropped the only nominal match. Ask surfaced `entity.unresolved`.

The Interpreter did not need to know that Luna is stored as `cat`. That
classification belongs to the PKE.

## Decision

```text
reference_kind = class
→ type is identity constraint

reference_kind = possessive
→ relation + type define identity

reference_kind = named
→ name defines identity
→ type is secondary hint
```

For `named`:

1. Collect candidates by canonical name / alias (no type hard-filter).
2. One candidate → resolve. If a type hint is present and does not match,
   keep the entity and record `named_match_with_nonbinding_type_hint` /
   `type_hint_mismatch`.
3. N candidates → use type hint only when it uniquely distinguishes.
   Otherwise clarification (`named_multiple_candidates`). Never silent pick.
4. Zero candidates → existing query miss / ingest create-candidate contract.

`class_hint` is preserved on the mention. It is not discarded.

`hierarchy=exact` remains a query-engine concern. It must not block a unique
named identity because a hint is broader than the stored type.

## Location

`pke.resolution.entities.EntityResolver._from_named` /
`_lexical_candidates`. Not measurement-specific. Not Interpreter.

## Consequences

- Unique `Luna` (cat) resolves under hint `animal`.
- CLASS queries still constrain by type; they do not become name lookup.
- POSSESSIVE remains `owns(actor, X) AND type(X)=T`.
- Future ontology (`cat ⊂ animal`) may turn a mismatch into
  `TYPE_DESCENDANT_MATCH`; this increment does not implement that hierarchy.
