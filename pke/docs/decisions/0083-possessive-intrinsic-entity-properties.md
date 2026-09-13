# ADR 0083 — Possessive Entity Resolution & Intrinsic Entity Properties

## Status

**Accepted** — incremental on ADR 0081 / 0082. Does not reopen Class vs Instance
or Interpreter prompts.

## Context

`qual o nome do meu gato?` already arrived as language-independent IR:

- `reference_kind = possessive`
- `class_hint → entity.learned.cat`
- `attribute_expression → name`

EntityResolver treated `possessive` like `contextual` (recent mention, plus a
vehicle-only `relation.owns` shortcut). A cat named Luna owned by the actor was
not selected. The Engine then looked for `attribute.name` rows that ingest never
wrote — the name already lived on `Entity.canonical_name`.

## Decision

### A. Possessive entity resolution

`reference_kind=possessive` with type hint `T` means:

```text
X such that relation.owns(actor, X) AND type(X) = T
```

Graph walk lives in `owned_entity_ids` (`application/ownership.py`). Resolution
filters that list by type in `EntityResolver._from_possessive`. No `raw_input`,
no possessive lexeme table, no animal-specific branch.

`relation.owns` is the canonical possession relation (same as E1.2 vehicles),
generalized to every entity type.

| Candidates | Query result |
|------------|----------------|
| 0 | `entity.no_match` → Ask `no_results` (not `entity.unresolved`) |
| 1 | `resolved` (`OWNED_BY_PRINCIPAL`) |
| N | existing `entity.ambiguous` / `clarify.entity.which_one` |

QUERY does not pick among N via recency. INGEST of vehicles keeps the E1.2
create/recent path.

### B. Intrinsic entity properties

`Entity` has `canonical_name` only (no `display_name`). Ingested "Luna" is stored
as `canonical_name = "Luna"` (surface preserved; not a separate display field).

Product-facing intrinsic key: **`name`** → `Entity.canonical_name`.

Not exposed as attribute queries: `id`, `type_id`, `user_id`, `aliases`,
`created_at`.

Principal (`__principal__`) still uses Attribute `name` (E1.2 "meu nome é
Carlos"). Intrinsic lookup skips the principal entity so those tests stay on
Attribute rows.

Color / other dimensions stay on Attribute assertions after possessive
resolution of the entity.

Do not materialize `attribute.name` on every entity.

## Consequences

- Opaque `raw_input` after Interpreter still executes (ADR 0081).
- "eu tenho uma gata?" remains a CLASS + `relation.owns` query (ADR 0082).
- Prompts v4/v5 unchanged.
