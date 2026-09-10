# ADR 0028 — EventParticipant Storage v7 Implementation (I11.10.3)

## Status

Accepted — implements I11.10.1 design via I11.10.2 runner.

## Decision

```text
schema = v7
canonical participants = event_participants
legacy actor_id / subject_id = COMPATIBILITY_ONLY (still written as projection)
```

### Table

```text
event_participants
  id         TEXT PK
  event_id   TEXT NOT NULL FK events(id) ON DELETE CASCADE
  entity_id  TEXT NOT NULL FK entities(id)
  role       TEXT NOT NULL  -- stable key
  UNIQUE(event_id, entity_id, role)
indexes: event_id, entity_id, (event_id, role), (entity_id, role)
  (UNIQUE covers event_id+entity_id+role)
```

### Roles

`role.actor` | `role.object` | `role.patient` | `role.context` | `role.unspecified`

`role.unspecified` added to CORE ROLE seeds for migration vocabulary.

### Write path

Materializer builds `EventParticipant` from resolved mention roles.  
Legacy columns projected:

- `actor_id` ← first `role.actor` only (never context)
- `subject_id` ← first `role.object` / `role.patient`

```text
ARE_LEGACY_COLUMNS_STILL_WRITTEN? YES
```

as compatibility projection only — not canonical.

### Query path

`EVENT_CONTEXT` / association filters use `event.participant_entity_ids()`.  
No permanent dual-truth: participants are authoritative after migration backfill.

### Migration v6→v7

Deterministic backfill (**I11.10.3-R**):

```text
EntityKind ≠ SemanticRole
v6 has no persisted participant-role provenance
→ every legacy actor_id / subject_id → role.unspecified
```

Every non-null actor_id/subject_id → ≥1 participant row. No LLM.  
No promotion of person→actor or vehicle→context.

`role.unspecified` means: participation known; semantic role not safely established.

### Implicit user

Not persisted as participant (deferred).

## Consequences

- Actor+object+context simultaneous persistence works (P1)
- Context never stored canonically as actor
- I11.9 discrimination remains green
- `EVENT-ROLE-01` closed for persistence scope

## Non-goals

Place role, principal/self Entity, participant provenance, dropping legacy columns.
