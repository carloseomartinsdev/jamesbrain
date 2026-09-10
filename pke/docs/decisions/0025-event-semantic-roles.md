# ADR 0025 — Event Semantic Roles & Participant Representation (I11.10)

## Status

Accepted — I11.10

## Problem

I11.9-R showed that compositional query discrimination worked, but **semantic roles were collapsed** on the ingest path:

```text
"Troquei a embreagem do Corolla."

semantic:  actor=user (implicit), object=clutch, context=Corolla
physical:  Event.actor_id=Corolla, Event.subject_id=clutch
```

Root causes:

1. `pipeline.py` forced `entity.automobile` → `role.actor` when role was absent (I11.9 workaround).
2. `proposal.object` was wired as `role.subject`, conflating object/affected with grammatical subject.
3. `materializer._roles()` fell back to **first mention** for empty actor/subject slots.
4. Event storage (v6) exposes only `actor_id` + `subject_id` — no dedicated context slot.

Principle reaffirmed:

```text
Entity association ≠ semantic role
Actor = entity performing/initiating action (not frame/context)
Object = entity directly acted upon
Context = frame without actor/object identity
```

## Decision

### Semantic role layer (no schema migration)

Introduce `event_roles.py` with `ResolvedEventRoles`:

| Semantic role | Source |
|---|---|
| `actor` | explicit person/org in `subject` or `participants` |
| `actor_implicit` | first-person change verbs without explicit actor entity |
| `object` | `proposal.object` |
| `affected` | intransitive change (`A porta abriu.`) — thing subject, no object |
| `context` | `entities_mentioned` vehicle/place not already actor/object |

Wire roles (minimal ROLE seeds added):

- `role.object`, `role.patient`, `role.context` (+ existing `role.actor`)

Pipeline builds Event participants from `resolve_event_roles()` — **no raw NL heuristics**, no automobile→actor hack.

### v6 physical mapping (compatibility)

| Semantic | Wire role | Event field (v6) |
|---|---|---|
| explicit actor | `role.actor` | `actor_id` |
| object / affected | `role.object` / `role.patient` | `subject_id` |
| context (no explicit actor) | `role.context` | `actor_id` *(physical context slot)* |
| context (explicit actor present) | `role.context` | **not persisted** *(completeness gap)* |
| implicit user actor | — | no entity fabricated |

Query `EVENT_CONTEXT` continues AND-matching on `{actor_id, subject_id}` — discrimination preserved.

Materializer **does not infer roles**; it maps resolved wire roles only. Removed first-entity fallback.

### Implicit first-person actor

```text
semantic actor = current user (known)
persistent actor entity = absent (by design)
```

No `Entity(name="eu")` fabrication.

### Subject terminology debt

`Event.subject_id` historically overloaded (grammatical subject / object / affected). I11.10 documents:

- **Semantic**: `subject_id` = object or affected entity when wired via `role.object` / `role.patient`
- **Not**: grammatical topic; not context frame
- Rename deferred (physical compatibility)

### Query path alignment

`query_resolution._collect_entities()` assigns `role.context` to vehicle/place mentions (was `role.subject`).

## Storage

```text
schema = v6
migration = none
```

Full three-way persistence (actor + object + context simultaneously) would require v7 participant model — **not required** for I11.10 acceptance; missing context with explicit actor is completeness, not wrong role.

## Metrics

Deterministic audit helpers:

- `SEMANTIC_ROLE_PRESERVATION` — per-dimension status
- `FALSE_ROLE_ASSIGNMENT` — mandatory matrix target **0**

## Legacy compatibility

```text
WOULD_EXISTING_V6_EVENTS_BE_INTERPRETED_DIFFERENTLY? PARTIALLY
```

- Stored rows remain readable; query EVENT_CONTEXT unchanged.
- Old ingests may have Corolla in `actor_id` with actor semantics (legacy).
- New ingests: semantic layer distinguishes actor/object/context; physical slot may still reuse `actor_id` for context when actor implicit.

## Consequences

- `ARE_OBJECT_AND_CONTEXT_COLLAPSED_SEMANTICALLY?` → **NO** at semantic layer; **PARTIALLY** at storage when explicit actor + context (context not stored).
- `EVENT-ROLE-01`: **REDUCED** (core roles preserved; full participant persistence deferred)
- Prompt: **unchanged**
- Ontology: +3 ROLE seeds only (`role.object`, `role.patient`, `role.context`) — no action/domain expansion

## Deferred

- `EventParticipant` table / `context_id` (schema v7)
- WHO/WHERE query answers
- `part_of` relations from event context
- Universal `SemanticFrame` persistence
- Third-person alias coverage (`trocou` vs `troquei`) — interpreter evidence, not role layer

## Tests

`tests/event_roles/` — ER1–ER6 audit matrix, RT1–RT6, v6 slot mapping, I11.9 query regression.

Full non-live suite: **458 passed** (439 baseline + 19 new).
