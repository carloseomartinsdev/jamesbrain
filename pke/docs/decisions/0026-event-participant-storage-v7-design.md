# ADR 0026 — Event Participant Storage v7 Design (I11.10.1)

## Status

Proposed — design only. **Not implemented.** Schema remains **v6**.

## Context

I11.10 approved semantic role resolution (`ResolvedEventRoles`: actor / object / context / affected) with false-role = 0. Storage representation was held:

```text
I11.10 SEMANTIC ROLE RESOLUTION = APPROVED
I11.10 STORAGE REPRESENTATION = HOLD
EVENT_ROLE_STORAGE_CHANGE_REQUIRED
```

## Problem

v6 Event persists at most two entity FKs:

```text
events.actor_id
events.subject_id
```

Unrepresentable without information loss or role falsification:

```text
"O mecânico trocou a embreagem do Corolla."
actor=mechanic, object=clutch, context=Corolla
→ actor_id=mechanic, subject_id=clutch, context LOST
```

Or role falsification to keep association:

```text
"Troquei a embreagem do Corolla."
→ actor_id=Corolla (context stored as actor_id), subject_id=clutch
```

Principle:

```text
Entity participation ≠ semantic role
MISSING_ROLE > WRONG_ROLE
Storage must preserve known semantics; must not manufacture unknown ones.
```

## v6 Audit Summary

### Persisted Event fields

Identity / type: `id`, `user_id`, `type_id`, `action_id`, `status`, `raw_input_id`, `created_at`  
Participants (only): `actor_id`, `subject_id`  
Domains: `event_domains`  
Temporal: calendar + recurrence + `temporal_*` (I11.3)  
Provenance: via `raw_input_id` / facts `source_id` — not per-participant

### Historical `actor_id` semantics

| Class | When | Evidence |
|---|---|---|
| ACTOR | Explicit person/provider with `role.actor` / `role.provider` | Materializer role map |
| CONTEXT | Vehicle/place with `role.context` when no explicit actor (I11.10) | Materializer fallback |
| LEGACY_UNKNOWN | Pre-I11.10: automobile forced to `role.actor`; first-mention fallback | Pipeline/materializer history |
| OTHER | Provider-as-actor (appointments) | `role.provider` → actor slot |

### Historical `subject_id` semantics

| Class | When |
|---|---|
| OBJECT | `role.object` / historically `role.subject` for acted-upon entity |
| AFFECTED_ENTITY | `role.patient` (intransitive) |
| GRAMMATICAL_SUBJECT / PRIMARY_ENTITY | Legacy IR subject slot; overloaded name |
| LEGACY_UNKNOWN | First-mention fallback when roles absent |

### EVENT_CONTEXT

```text
IS_EVENT_CONTEXT_CURRENTLY_A_SEMANTIC_ROLE
OR A_GENERIC_ENTITY_ASSOCIATION_FILTER?
→ GENERIC_ENTITY_ASSOCIATION_FILTER
```

`QueryEngine._entity_match(EVENT_CONTEXT)` requires `wanted ⊆ {actor_id, subject_id}`. It is **not** a semantic CONTEXT role predicate.

## Alternatives

| Model | Fidelity | Queryability | Migration safety | Complexity | Extensibility | Decision |
|---|---:|---:|---:|---:|---:|---|
| Dedicated columns (`actor_id`/`object_id`/`context_id`/`affected_id`) | 3 | 4 | 3 | 2 | 1 | Reject — 0..1 caps; Place/Manner force new columns |
| **EventParticipant** | 5 | 5 | 4 | 3 | 5 | **Recommend** |
| Hybrid (legacy columns + participants) | 4 | 3 | 2 | 4 | 3 | Reject as permanent — dual truth; OK only as short transition |
| Generic SemanticFrame persistence | 5 | 3 | 2 | 5 | 5 | Reject — premature generalization |

### WHY EventParticipant

- Supports 0..N per role (João+Maria actors; tires+pads objects; vehicle+place contexts)
- New roles without ALTER TABLE per role (stable role key column)
- Clear cascade with Event
- Query: generic entity association OR role-constrained match
- Migration can emit `UNSPECIFIED` without inventing ACTOR/CONTEXT

### WHY NOT dedicated columns

Cannot store multi-actor / multi-object / multi-context without further schema churn. Confirms the same 2-slot trap for Place vs Context later.

### WHY NOT permanent hybrid

`WHAT_IS_THE_CANONICAL_SOURCE_OF_EVENT_PARTICIPANTS?` must be singular. Hybrid write forever → role divergence.

### WHY NOT SemanticFrameParticipant for all primitives

```text
IS_THIS PREMATURE GENERALIZATION? YES
```

State and Relation already have closed models. Event-only participant table is sufficient for v7.

## Decision

### Recommended model

```text
event_participants
  id              TEXT PK
  event_id        TEXT FK events.id ON DELETE CASCADE
  entity_id       TEXT FK entities.id NULLABLE
  role            TEXT NOT NULL   -- stable key
  principal_kind  TEXT NULLABLE  -- future: 'user' | null
  principal_id    TEXT NULLABLE  -- future: users.id; not used in v7 initial writes
  UNIQUE(event_id, entity_id, role) WHERE entity_id IS NOT NULL
  -- user isolation via events.user_id (no denormalized user_id required)
```

### Participant cardinality (v7)

```text
ACTOR:            0..N
OBJECT:           0..N
AFFECTED_ENTITY:  0..N
CONTEXT:          0..N
```

Same entity may appear with **more than one role** on the same event (identity includes role). Accidental duplicate `(event, entity, role)` forbidden by UNIQUE.

### Initial role vocabulary (storage)

```text
role.actor
role.object
role.patient      -- AFFECTED_ENTITY
role.context
role.unspecified  -- legacy / unknown association only
```

Place ≠ Context conceptually (`ARE_CONTEXT_AND_PLACE_THE_SAME_ROLE? NO`). Place **not** introduced in v7 initial set; place entities may temporarily use `role.context` until a later role addition (key column avoids schema migration for that add).

Ordering / position: **not** required in v7.

### Role identity

```text
ROLE_IDENTITY_MODEL = STABLE_KEY
```

Stable string keys aligned with existing `role.*` vocabulary. Optional validation against ontology ROLE concepts at write time; storage does not require ontology FK for every row (avoids CORE churn for `role.unspecified` if kept storage-only initially). Provider-independent.

Not ENUM (harder extensibility). Not mandatory ontology FK for every participant (migration/legacy flexibility).

### Implicit current user

```text
SHOULD_IMPLICIT_CURRENT_USER_BE_PERSISTED_AS_EVENT_PARTICIPANT_IN_V7?
DEFER
```

Rationale:

- PKE account identity ≠ world-model Entity
- Fabricating Entity("eu") is prohibited
- Principal-reference (`entity_id=NULL`, `principal=user`) is a future option; introducing it now expands account↔entity architecture without evidence
- Accept: semantic actor known upstream; no participant row for implicit user; Event still valid under I11.8 partial canonicalization

### Provenance / confidence / temporal

```text
independent participant provenance required: NO (Event/raw_input sufficient initially)
independent participant confidence required: NO (future debt if needed)
participant temporal validity: NO (belongs to Event occurrence)
```

### Canonical source of truth

```text
WHAT_IS_THE_CANONICAL_SOURCE_OF_EVENT_PARTICIPANTS?
event_participants (after cutover)
```

Transition strategy **B then C**:

1. Add `event_participants`; migrate data; keep `actor_id`/`subject_id` readable (deprecated)
2. All new writes populate participants only (columns mirrored optionally for one release)
3. Later remove `actor_id`/`subject_id` once read path fully switched

Never permanent dual write as truth.

## Legacy migration (design only)

```text
DOES_V7_NEED_A_LEGACY_UNSPECIFIED_PARTICIPANT_ROLE?
YES
```

Cannot assume `actor_id → ACTOR` for all rows (I11.10 documented context-in-actor_id; pre-I11.10 automobile→actor).

| v6 evidence | v7 mapping | confidence |
|---|---|---|
| Entity kind person/org in actor_id | role.actor | medium–high |
| Entity kind vehicle/place in actor_id | role.context | medium (post-I11.10 pattern; still ambiguous for legacy) |
| Unknown / mixed / no kind | role.unspecified | safe |
| subject_id any | role.object **or** role.unspecified | prefer unspecified unless object/patient role metadata exists elsewhere |
| both slots populated | two participant rows | preserve associations |

Rules:

- No LLM / raw-NL reinterpretation during migration
- No Event deleted; no association dropped
- Unknown → `role.unspecified`, never invent ACTOR/CONTEXT when unsafe

### Migration phases (no execution)

```text
Phase 0  Resolve MIGRATION-01 (single canonical runner path)
Phase 1  Create event_participants (+ indexes); SCHEMA_VERSION → 7
Phase 2  Backfill from actor_id/subject_id with classification heuristics + unspecified fallback
Phase 3  Dual-read: QueryEngine prefers participants; falls back to columns
Phase 4  Cutover writes: materializer → participants only
Phase 5  Drop deprecated columns (later increment; optional)
```

SQLite: forward-only preferred; rollback = restore backup / reverse script optional but not required for design approval.

## Query impact (future)

I11.9 `EVENT_CONTEXT` becomes:

```text
generic: all query entity_ids ⊆ participant.entity_ids for event
optional: role-constrained predicates when QueryIR knows role
```

Compatibility invariant: `"Já troquei a embreagem do Corolla?"` remains MATCH after migration (generic association).

Future: `"João trocou a embreagem?"` can constrain João as ACTOR — storage enables; query expansion not in this design increment.

## Ingest impact (future)

```text
ResolvedEventRoles → Mentions/bindings → Materializer → EventParticipant rows
```

Materializer consumes resolved roles only (no NL). Missing optional roles remain valid (I11.8).

## ROLE seeds / CORE inconsistency (I11.10)

```text
WHAT_ARE_ROLE_SEEDS?
CORE ontology concepts (ConceptKind.ROLE) used as semantic vocabulary
for wire/catalog validation — structural participant vocabulary, not domain knowledge.
```

```text
DID_I11.10_CHANGE_CORE?
YES
```

Added: `role.object`, `role.patient`, `role.context` (pre-existing: `role.actor`, `role.subject`, `role.provider`).  
I11.10 report "CORE unchanged" was incorrect for ROLE seeds. No ontology change in I11.10.1.

## MIGRATION-01

```text
SHOULD_MIGRATION_01_BE_RESOLVED_BEFORE_V7?
YES
```

v7 is the first Event participant rewrite with ambiguous backfill. Dual Python vs Alembic paths must be reduced to one operational canonical path before executing v7 (Python `persist/migrations/` is de-facto today; document/enforce).

## Schema justification

```text
IS_SCHEMA_V7_JUSTIFIED?
YES
```

Exact capability impossible in v6: persist **actor + object + context** simultaneously without dropping a known role or storing context as actor.

## Safety / preservation invariants

```text
DATA:     no Event lost; no known entity association lost
SEMANTIC: known roles preserved; unknown → unspecified (not false ACTOR)
QUERY:    I11.9 discrimination remains MATCH/NO_MATCH as today after cutover
SAFETY:   false canonicalization = 0; false role assignment = 0; S4 = 0
```

## Deferred

- Place as distinct role
- Implicit user principal participant
- Canonical user Entity architecture
- Independent participant confidence/provenance
- WHO/WHERE query expansion
- Removing actor_id/subject_id (phase 5)
- Implementing any of the above

## Explicit non-implementation

This ADR does **not** change `STORAGE_SCHEMA_VERSION`, ORM, repositories, materializer, or QueryEngine.
