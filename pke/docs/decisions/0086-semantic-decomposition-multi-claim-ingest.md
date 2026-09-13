# ADR 0086 — Semantic Decomposition, Atomic Claims and Multi-Claim Knowledge Ingest

## Status

**Accepted** — incremental on ADR 0081 / 0083. Does not reopen:

- ADR 0081 — Language Independence
- ADR 0082 — Class vs Instance
- ADR 0083 — Possessive + Intrinsic Entity Properties
- ADR 0084 — LLM Response Presenter
- ADR 0085 — Named Entity Resolution with Non-Binding Class Hints

Does not implement Named Entity Resolution, Presenter changes, or a world
ontology hierarchy (`cat ⊂ animal`). Filename `0085-semantic-decomposition-…`
was requested; **0085 is already used**, so this decision is **0086**.

## Context

The pipeline reduced one utterance to one primary primitive, then one knowledge
operation. A manifestation such as “Minha gata se chama Luna.” could persist
`owns` and drop independently explicit facts (classification, sex, intrinsic
name). `status=committed` did not mean semantic completeness.

`primitive_hint` is still useful for routing. It must not cap extracted
knowledge.

## Decision

```text
utterance ≠ fact
utterance → N atomic claims

explicit ≠ derived
derived ≠ assumed
```

```text
User utterance
      ↓
LLM Interpreter   (language → semantics; no world-knowledge invention)
      ↓
Semantic Proposal + claims[]
      ↓
PKE               (validate, canonicalize, persist; do not re-read raw_input)
      ↓
Knowledge Graph
      ↓
Safe ontological derivation (future; not materialized here)
```

### Atomic claim

Existing IR slots are reused, not replaced:

- `SemanticProposal.claims[]` — Interpreter atomic units
- `IngestIR.additional_relations` / `additional_measurements` — plurality
- `additional_attributes` already existed (E1.2 companions)
- `ClaimTally` on ingest/materialization results

Kinds: `entity`, `classification`, `relation`, `attribute`,
`intrinsic_property`, `measurement`, `state`, `event`.

### Persistence policy

| Origin | Policy |
|--------|--------|
| EXPLICIT | Persist |
| DERIVED | Not materialized in this increment (invalidation/hierarchy not ready) |
| ASSUMED | Never auto-persist |

Classification is `Entity.type_id` (including `entity.learned.*`), not
`Attribute(species=…)`. Intrinsic `name` is `Entity.canonical_name` (ADR 0083),
not a duplicate `attribute.name` on non-principal entities.

`primitive_hint` remains. Companion claims overlay the primary wire. Event +
Measurement `COMMIT_VALID_INDEPENDENTLY` is unchanged; other families no longer
early-return and drop siblings.

After the Interpreter, `raw_input` may be `OPAQUE-MULTICLAIM-001` without
changing claims.

The Engine has no linguistic tables such as `gata → female`. Conceptual
dimension keys (`sex`, `profession`, `color`) are registry dimensions; values
arrive already interpreted.

### Ontology hierarchy

Prepared, not implemented: `instance_of` / `subclass_of`, learned-class
subsumption, query-time or materialized DERIVED types. Tests for `cat ⊂ animal`
are `xfail` until that increment.

## Consequences

- Multi-claim ingest is domain-agnostic (`synthesizer`, `drone` via learned types).
- Presenter must not dump every persisted claim (ADR 0084 already).
- Graph viewer should later distinguish EXPLICIT vs DERIVED.
- Future correction of one claim (color) must not retract siblings from the
  same utterance — versioning already exists; multi-claim provenance shares
  `raw_input_id`.
