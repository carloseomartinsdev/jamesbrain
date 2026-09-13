# ADR 0090 — Owned Object Semantic Decomposition and Claim Consistency

## Status

**Accepted** — incremental on ADR 0083 / 0086 / 0089. Does not reopen:

- ADR 0081 — Language Independence (Engine still does not re-read `meu` / `my` / `mi`)
- ADR 0082 — Class vs Instance
- ADR 0089 — Learned Attribute Dimensions

Filename requested as `0089-owned-object-semantic-decomposition.md`; **0089 is already used**, so this decision is **0090**.

## Context

`meu carro é um City` produced an inconsistent stack:

```text
proposal  →  vehicle_attribute_repair rewrote primitive / subject
claims    →  leftover Classification(carro, vehicle, value=City)
canonical →  Entity(carro) + Entity(City)
graph     →  no relation.owns, no attribute.model
status    →  committed
```

`City` persisted because `entities_mentioned` / `reference_kind=named` were treated as persistable identity. `owns` was not materialized because possessive CREATE and ownership backup were vehicle-shaped, and claims never carried `relation.owns`. `vehicle_attribute_repair` changed proposal semantics without updating Atomic Claims (I4 violation).

The Knowledge Inspector was not the bug: orphan entities correctly do not appear under `__principal__`.

## Decision

```text
possessive reference  →  actor relation (typically relation.owns)
descriptive value     ≠  entity identity
repair semantics      ==  claim semantics
Atomic Claims         →  materialization source of truth
```

```text
LLM IR
  ↓
normalize
  ↓
minimal repair (skip when explicit claims exist)
  ↓
semantic decomposition / claim overlay
  ↓
Atomic Claims + persistable mentions
  ↓
canonical IR
  ↓
resolve / materialize
```

### A. Owned Object Reference

`reference_kind=possessive` + type `T` means an instance `X` such that:

```text
relation.owns(actor, X) AND type(X) = T
```

Write:

| Owned matches of type T | Action |
|---|---|
| 0 | CREATE `X` (anonymous identity) + `owns(actor, X)` + remaining claims |
| 1 | reuse `X` + apply claims |
| >1 | clarification (`possessive_ambiguous`) — no recency pick |

Query with 0 matches remains `possessive_no_match` (ADR 0083). The Engine does not re-read surface possessives.

Vehicle recency (`last_by_type` / unique recent) stays on **contextual** vehicle mentions (`o carro`). Possessive write does not inherit that compatibility path.

### B. Entity vs attribute value vs classification

| Role | Example | Persist |
|---|---|---|
| Entity identity | `meu carro se chama Thor` | Entity + intrinsic name |
| Attribute value | `meu carro é um City` | `Attribute(model=City)` — not `Entity(City)` |
| Classification | `meu veículo é um carro` | type `entity.automobile` on the instance |

`named` is not sufficient to persist an entity. Persist only identity roles on explicit claims (relation endpoints, attribute/classification/measurement **subject**, entity claim). Values of attributes / classifications / intrinsic properties are not entities because they are capitalized.

`entities_mentioned` is context. New entities require a persistable identity role.

### C. `vehicle_attribute_repair` — option B (restrict)

Do not grow a model lexicon (City / Civic / Corolla). Do not add `laptop_attribute_repair`.

- Explicit Atomic Claims present → **skip** the repair (never overwrite rich IR).
- Legacy E1.2 path (no claims) may still translate `meu carro é …` into attribute slots and **clears `object`** so the descriptive token is not left as a named mention.

Repairs that change primitive / subject / object / attribute / relation / classification must update, invalidate, or regenerate claims — or run before claims are final. Divergent `proposal=attribute` + `claims=old classification` is forbidden (I4).

Preferred: linguistic repairs before final Atomic Claims. Today's Interpreter often emits claims; therefore repairs that still run must be claim-aware. Decision recorded: **restrict**, do not delete yet (E1.2 no-claim path).

### D. Identity of unnamed owned instances

Class lemmas (`carro`, `notebook`) are not proper names. Possessive CREATE uses generated `canonical_name`:

```text
owned:{type-slug}:{ulid-suffix}
```

`City` as model is not `canonical_name`. Named identity (`Thor`, `Luna`) still uses the mention text / intrinsic name.

### E. Claim overlay

Possessive identity mentions synthesize `relation.owns(self, X)` when missing. Overlay drops value-only mentions from `entities_mentioned`. Materializer follows claims/roles, not raw mentions.

Materializer backup `_ensure_principal_ownership` links `owns` for possessive (any type) and for vehicle contextual CREATE. Orphan possessive CREATE logs `knowledge.orphan_owned_entity` (trace only).

### F. Interpreter prompt (v4 and v5, same block)

Owned object + copular description is domain-independent: split classification, ownership, and descriptive properties (model / brand / name / color / …). Do not emit descriptive values as standalone named entities. Examples use laptop / bike / company — not cars only.

The PKE does not invent `model=City` from `raw_input`.

## Consequences

- `class_hint=vehicle` continues to resolve to canonical `entity.automobile`, not `entity.learned.vehicle`.
- Unknown types (`synthesizer`) remain `entity.learned.*` (ADR 0086).
- Future product-model ontology (`Honda City` as `VehicleModel`) is out of scope; this increment stores `Attribute(model)`.
- Company vs organization alias (`company` → `organization`) is unchanged (ADR 0085 / kind aliases).
