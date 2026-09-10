# ADR 0076 — Principal Binding and Contextual Self Resolution (E1.1)

## Status

**Accepted** — E1.1 Everyday Knowledge Foundation (Principal / Self).

Additive to Knowledge schema **v10 → v11**. Does not collapse Product identity into Entity identity.
Does not implement everyday Attribute dimensions (`name`, `brand`, …) — those remain E1.2.

Extends ADR 0026 (deferred principal-reference), ADR 0071 (AuthUser ≠ Entity), and
`docs/PKE-E1-EVERYDAY-KNOWLEDGE-PLAN.md` decisions D-E1-01…D-E1-05, D-E1-12…D-E1-14, D-E1-20.

## Context

JAMES Beta showed that first-person everyday speech cannot bind to a world-model person Entity.
ADR 0026 deferred principal-reference; E1 supplies an explicit Knowledge binding instead of
fabricating `Entity.id = AuthUser.id`.

## Decision

### Binding ownership

```text
PrincipalBinding lives in Knowledge (principal_bindings).
Product remains auth / isolation / conversation / public DTO only.
```

### Identity invariant

```text
AuthUser.id != Entity.id
```

Binding is explicit: `(user_id) → (entity_id)`.

### Lifecycle

- Lazy: create Principal Entity + binding only when self resolution is required.
- Bootstrap creates `entity.person` with neutral canonical placeholder `__principal__`.
- Bootstrap does **not** copy spoken attributes (e.g. name) from the triggering utterance.
- `ensure_principal_entity(user_id)` is deterministic and idempotent (one active binding per user).

### Self resolution

Contextual self lexemes (`eu`, `me`, `meu`, … when used as self reference) resolve via
`PrincipalBinding` to the principal Entity.

Deterministic repair (before prompt tuning) corrects high-precision misparses such as:

```text
"Meu nome é Carlos." → subject named Carlos
```

into:

```text
subject = contextual self ("eu")
attribute_expression retains name value for later E1.2 dimension support
```

Repair is conservative and must not rewrite `Eu vi Carlos ontem.` into `self.name`.

### Schema

```text
STORAGE_SCHEMA_VERSION = 11
table principal_bindings(user_id PK, entity_id FK entities, created_at, updated_at)
```

## Consequences

- Knowledge schema version assertions move from `10` → `11`.
- Ontology CORE count (65) and Engine prompt v4 remain unchanged in E1.1.
- Self write/query of everyday `name` awaits E1.2 Attribute registry expansion.
- E1.1 may still demonstrate self write/query using already-materializable dimensions (e.g. height).
