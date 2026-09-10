# ADR 0077 — Everyday Attribute Registry Expansion (E1.2)

## Status

**Accepted** — E1.2 Everyday Attributes (`name`, `brand`, `model`) + vehicle ownership integration.

Does not authorize E1.3 (CLARIFY vs UNSUPPORTED policy completion) or E1.4.

Extends ADR 0076 (Principal Binding), D-E1-06…D-E1-11, D-E1-17.

## Context

E1.1 bound AuthPrincipal → Entity without collapsing identities, but everyday descriptive
properties (`name`, vehicle `brand`/`model`) were still outside the controlled Attribute set.
JAMES / Product must not invent semantics; the Engine expands the registry.

## Decision

### Controlled registry

```text
candidate attribute
       ↓
ATTRIBUTE_DIMENSION_REGISTRY (static)
       ↓
dimension known? → typed resolution
               └── no → safe abstention (no IR / no commit)
```

LLM proposals never register dimensions at runtime.

### Dimensions added (E1.2)

| key | value kind | notes |
|-----|------------|-------|
| `name` | text (name-like normalize) | singleton_current; sensitive |
| `brand` | text (controlled brand list) | Attribute — not Relation manufacturer |
| `model` | text (model-like) | distinct from brand; companion write allowed |

Core v1 dimensions (`color`, `height`, …) remain unchanged. Color stays multi-evidence
(no forced supersession) to preserve Attribute evidence semantics from v8.

### Name write / query

```text
"Meu nome é Carlos." → PrincipalBinding → principal Entity → Attribute name=Carlos
"Qual é o meu nome?" / "Como eu me chamo?" → Knowledge Attribute lookup (not chat history)
```

Name is changeable: `singleton_current` closes prior current rows on rewrite.

### Vehicle + ownership (D-E1-08)

```text
Principal Entity
       ↓ relation.owns
Vehicle Entity (entity.automobile / vehicle)
       ├── brand
       ├── model
       └── color
```

Forbidden: `principal.car_brand` flattening.

Contextual `meu carro` resolves via current owned vehicles; first write may
`CREATE_CANDIDATE` then ensure `relation.owns`. Subsequent attributes enrich the same Entity.

Exception (narrow): validation allows contextual `CREATE_CANDIDATE` only when
`create_type_id` is `entity.vehicle` or a descendant (e.g. `entity.automobile`).
General contextual create remains forbidden.

Brand+model companions materialize in one ingest (`attribute` + `additional_attributes`).
Identity query `Qual é o meu carro?` presents `brand` (+ `model` composition in Ask).

### Safety

```text
no safe dimension/value → no valid IR → no commit
```

Unknown / invented dimensions abstain. Cross-user isolation via existing Knowledge scoping.

## Consequences

- `additional_attributes` on IngestIR / WireIngestIR for companion Attribute writes.
- ResolutionContext carries `owned_vehicle_entity_ids`.
- Materializer may emit `relation.owns` as ownership ensure after vehicle Attribute commit.
- Product / JAMES remain consumers only — no portal semantic logic for name/brand/ownership.
