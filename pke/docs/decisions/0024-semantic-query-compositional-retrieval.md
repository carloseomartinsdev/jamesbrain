# ADR 0024 — Semantic Query & Compositional Retrieval (I11.9)

## Status

Accepted — I11.9

## Problem

Write path (I11.6–I11.8) persists Events using compositional semantics (`action`, optional `event_type`, entities, partial temporal). Query path still used `proposal_query_to_wire()` with hardcoded relation/state keys and treated `event_type` as mandatory identity (`EVENT-QUERY-01`, `SEMANTIC-QUERY-01`).

## Decision

### Shared semantic core (no second ontology)

Introduce `query_resolution.py` that reuses:

- `route_primitive`
- `recognize_senses` / lexical safety (I11.6.1)
- `resolve_concepts` (`SemanticConceptResolver`)
- `EntityResolver` (via existing `ResolvedQueryBuilder`)

Query proposals use the **same conceptual grammar** as ingest proposals (`SemanticProposal`), delivered as `semantic_query` envelopes.

### Query intent vs knowledge semantics

- **Query intent**: existence / historical occurrence (`list` or `aggregate`+`count` when temporal range present)
- **Knowledge semantics**: `primitive`, `action`, optional `event_type`, entities, temporal constraint

Existence questions do not invent missing calendar fields on stored knowledge.

### Compositional Event lookup

`QueryEngine` already supported `action_ids`; I11.9 makes them first-class in semantic query resolution. `event_type_ids` remain **optional** filters.

`EntityAssociation.EVENT_CONTEXT` requires **AND** semantics: all query entity ids must appear on the event (`actor_id` / `subject_id`).

### Safe abstention

Blocked / ambiguous / ontology-gap proposals return unresolved query outcomes (no broad misleading search).

### Compatibility

- Legacy `WireSemanticQuery` still parsed via `parsed_query_proposal()` fallback
- Wave 1 `QueryIR` tests unchanged
- Schema remains **v6** — no migration

## Consequences

- `EVENT-QUERY-01`: **CLOSED** — action+object retrieval without mandatory `event_type`
- `SEMANTIC-QUERY-01`: **REDUCED** — query shares resolver core; transport/assessment still separate stages
- Ingest wire now includes `object` in `entities_mentioned` with role hints (actor/subject) for participant materialization

## Deferred

- Clarification engine for ambiguous queries
- Ontology expansion (`install`, etc.)
- Knowledge Enrichment / Behavioral Memory

## AskStatus contract (I11.9-R)

For COUNT queries with temporal range:

- `AskStatus.ANSWERED` = query executed successfully — **not** “proposition is false”.
- `AskStatus.NO_RESULTS` = complete negative (no indeterminate temporal contributors).
- `count=0` with `temporal_membership_unknown=true` is **not** a complete negative (`_is_empty` returns false).
- Epistemic UNKNOWN for partial past + calendar range is represented as:
  `ANSWERED` + `aggregate.value=0` + `temporal_completeness=PARTIAL` + `temporal_membership_unknown=true`.
