# ADR 0082 — Class vs Instance Semantic Resolution

## Status

**Accepted** — incremental contract extension on ADR 0081.

## Context

Queries such as "eu tenho uma gata?" were compiled as instance resolution of the
surface noun (`gata` → `entity.unresolved`). The Interpreter already identified
a relation query (`owns`, subject=self, object=gata) but had no slot for
**class/type constraint** versus **specific instance**.

`reference_kind` only allowed `named | contextual | possessive`. Repair then
overwrote the object to `contextual` via a Portuguese possession heuristic.
The Engine tried to resolve an entity named "gata".

Live write of "eu tenho uma gata chamada luna" persisted:

- entity `luna` with `type_id = entity.thing` (no class `cat`)
- relation `relation.learned.tem_uma_gata_chamada` (not `relation.owns`)

TYPE assertions remain non-materializable; class on a named instance must travel
as `class_hint` on the instance mention of a RELATION write.

## Decision

1. **Interpreter** distinguishes CLASS vs INSTANCE. `reference_kind=class` plus
   optional `class_hint` (language-independent lemma). Surface language stays in
   `text`. `kind_hint` stays the closed coarse bucket.
2. **PKE** canonicalizes `class_hint` → existing `entity.*` or
   `entity.learned.{slug}`. It MUST NOT slug Portuguese surface forms to invent
   types.
3. **Repair** MUST NOT overwrite explicit `class` or `named` slots with
   `contextual`.
4. **Query builder** does not resolve CLASS mentions to entity ids. The Engine
   filters relation targets by `object_entity_type_ids` (exact type match).
5. Ontological hierarchy (`cat` → `pet` → `animal`) is **out of scope**.

## Consequences

- "Do I have Luna?" → instance boolean on `relation.owns`.
- "Do I have a cat?" → exists X: `owns(actor, X)` AND `X.type == cat`.
- Opaque `raw_input` after Interpreter must still execute (ADR 0081).
- Standalone TYPE writes ("Luna is a cat" with no relation) remain deferred.
