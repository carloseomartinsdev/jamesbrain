# ADR 0093 — Graph Semantic Core and Domain-General Knowledge Model

## Status

**Accepted** — incremental on ADR 0081 / 0086 / 0090 / 0091 / 0092. Does not reopen:

- ADR 0076 — Principal binding (technical `principal_id` / `__principal__` name may remain internally)
- ADR 0081 — Language Independence
- ADR 0090 — Owned Object Semantic Decomposition
- ADR 0091 — Conversation Discourse Context
- ADR 0092 — Engine-Anchored Discourse Writes / identity-role fold

Does **not** introduce `GraphIR2`, `NewKnowledgeEngine`, or a second claim contract.

## Context

Recent everyday cases (pet, house, accountant, notebook, vehicle) were being
absorbed as **repairs and domain branches**. Semantically they are combinations of
a small set of graph primitives. Domain examples must stay **fixtures, not
features**.

After the Interpreter, `raw_input` is opaque. The PKE must already know what to
create, update, relate, and query.

## Problem

1. Language repairs that reread `raw_input` (PT/EN lexemes) keep growing.
2. Identity-role ingest stored a person–principal **relation** but not the
   **profession property** that the same utterance also asserts.
3. Inverse relation keys (`owned_by`, `employs`) existed only as documentation;
   Query/Materializer could not execute them without a second stored edge.
4. Directionality was a free-text `direction` string plus a boolean `symmetric`;
   undirected query semantics were unspecified.
5. Atomic Claims already covered the primitives, but the mapping was implicit.

## Decision

```text
Natural Language
      ↓
LLM Interpreter          (language, discourse, decomposition)
      ↓
Semantic Graph Proposal  (= Atomic Claims on SemanticProposal)
      ↓
PKE Graph Semantic Core  (identity, ontology, consistency)
      ↓
Materializer / Query Engine
      ↓
Knowledge Graph
      ↓
Presenter                (natural language; out of PKE)
```

**Domain examples are fixtures, not features.**

**Language produces graph semantics; graph semantics do not reconstruct language.**

No new `raw_input` linguistic repair without an ADR explaining why the
Interpreter cannot emit the structure. No domain repair when the six primitives
suffice.

## Primitives

Existing `SemanticClaimKind` maps to the Graph Semantic Core:

| Core primitive   | Existing kind                          |
|------------------|----------------------------------------|
| ENTITY           | `ENTITY`                               |
| CLASSIFICATION   | `CLASSIFICATION` (router: `TYPE`)      |
| PROPERTY         | `ATTRIBUTE` + `INTRINSIC_PROPERTY`     |
| RELATION         | `RELATION`                             |
| EVENT            | `EVENT`                                |
| MEASUREMENT      | `MEASUREMENT`                          |

`STATE` remains a PKE condition primitive; it is **not** folded into PROPERTY.

Cross-cuts already on persisted rows: temporality, confidence, provenance.

Do not add a parallel Graph Proposal JSON. Claims with shared mention identity
(plus Discourse `known_entity_id`) are the intra- and inter-turn `entity_ref`.

## Relation semantics

`RelationConceptMetadata.directionality`:

- `directed` — stored `from_id → to_id`; inverse is metadata only
- `symmetric` — one stored row; query matches either endpoint (existing)
- `undirected` — same query/storage canonicalization as symmetric; semantics
  are “the connection”, not “A Rel B implies B Rel A as a distinct fact”

Inverse keys (`relation.owned_by`, `relation.employs`, …) stay **out of CORE**.
Query Builder and Materializer call `stored_relation_query`: rewrite to the
stored key and swap endpoints. Learned relations may **register** optional
metadata; the engine never infers inverse/direction from a slug.

Edge properties (since, contract) remain a future additive field on Relation;
not implemented here.

## Identity semantics

Surface mentions (`meu contador`, `Angelo`) bind to **one** semantic person.

- classification: `person` (not a second entity named after the role)
- property: `profession = {role lemma from Interpreter class_hint}`
- relation: principal `-- {role} -->` person (learned type; not `relation.named`)

`Angelo é contador` is profession (and/or classification) **without** a required
principal relation. `Angelo é meu contador` adds the relation.

## Property semantics

Descriptive values (`ThinkPad T14`, `3`, `32 GB`) are PROPERTY values, not
entities, unless the Interpreter marks a named/conceptual entity.

## Discourse integration

0091/0092 Discourse State remains the binding abstraction. Pronouns are resolved
by the Interpreter copying `known_entity_id`. Cardinality: multiple owned
instances of the same class → Engine clarification, not unique-possessive
assumption.

## Anti-overfitting rule

A semantic feature is generalized only when it works on **unrelated domains**
with the **same executable path** (no `if house` / `if luthier` in the Graph
Core). New domains should need ontology/learned data, not Core branches.

## Repair classification (audit)

| Module | Class | Action this increment |
|--------|-------|------------------------|
| `self_repair.repair_self_name_misparse` | LANGUAGE | Freeze; compatibility |
| `vehicle_repair` | DOMAIN + LANGUAGE | Freeze; already skipped when claims exist |
| `possessive_attribute_repair` | LANGUAGE | Skip when explicit claims exist |
| `likes_query_repair` | LANGUAGE / COMPATIBILITY | Freeze |
| `slot_align` | SEMANTIC NORMALIZATION | Keep |
| `identity_naming` | SEMANTIC NORMALIZATION | Keep; add profession property |
| `class_reference` | ONTOLOGY | Keep |
| Resolver owns-alias preemption | COMPATIBILITY | Keep |

## Phase A audit (spec §64)

1. **Primitives** — ENTITY, CLASSIFICATION, RELATION, ATTRIBUTE, INTRINSIC_PROPERTY, MEASUREMENT, STATE, EVENT.
2. **Duplicates** — PROPERTY = ATTRIBUTE + INTRINSIC_PROPERTY (name). Not renamed.
3. **Domain branches** — `vehicle_repair`, noun→kind map in possessive repair (compatibility).
4. **raw_input readers** — self_name, vehicle, possessive, likes, some query_resolution measurement modes.
5. **Linguistic repairs** — listed above; frozen.
6. **Semantic repairs** — identity_naming, slot_align, owned_object, claims overlay.
7. **Ontology** — CORE + learned entity/relation/attribute.
8. **Relation model** — `from_id`/`to_id` + concept key.
9. **Directionality** — now an enum on metadata.
10. **Inverse** — metadata + query/materializer rewrite; not a second edge.
11. **Symmetric** — existing canonical storage + bidirectional query.
12. **Property** — EntityAttribute dimensions (CORE + learned).
13. **Classification** — entity type / class_hint; dedicated TYPE query still insufficient (`type_query_not_attribute`).
14. **Event** — Event + participants; unchanged.
15. **Measurement** — Measurement rows; unchanged.
16. **Binding** — mention identity + `known_entity_id` + DiscourseState.
17. **Atomic Claims** — the graph proposal.
18. **Materializer** — IR/claims only; inverse rewrite added.
19. **Query** — QueryIR graph ops; inverse rewrite added. Multi-hop traversal **not** implemented (must not be blocked).
20. **Deprecation candidates** — language/domain repairs above; retire only with Interpreter coverage.

## Migration strategy

Incremental: formalize mapping → claims (profession) → query/materializer
directionality → skip claim-covered language repairs → cross-domain suite.
No rewrite of IngestIR / QueryIR.

## Compatibility

Learned keys, CORE inverses-as-metadata-only (`inverse_accidentally_core` empty),
and principal technical identity stay. Presenter remains outside the Engine.

## Rejected alternatives

- New GraphIR / engine v2
- CORE concepts for every inverse
- Profession word lists / `luthier_repair`
- Persisting two edges for inverses or symmetric relations
- PKE reading `meu` / `ela` / `my`

## Testing strategy

Cross-domain fixtures (house, cat, computer, synthesizer, camera, professional
roles including unseen `luthier`, adversarial `theremin`). Opaque `raw_input`
per primitive. PT/EN/ES same structure. Inverse and undirected queries.
Grep guard: Graph Core source must not mention adversarial fixture nouns.

## Consequences

The PKE answers “what knowledge is this?” not “what sentence is this?”.
Adding a domain should add ontology or learned concepts, not a Core branch.
Dedicated classification boolean query and multi-hop traversal remain follow-ups.
