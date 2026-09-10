# ADR 0030 — Attribute Primitive & Property Representation (I11.12)

## Status

Accepted (design) — I11.12. **Not implemented.** Schema remains v7.

## Context

I11.4–I11.11 established State, Relation, semantic resolution, partial canonicalization, query, EventParticipant (v7), and controlled ontology expansion (`action.install`).

Deferred property cases remain unresolved:

```text
color · new · facilities · area/weight/height/model_year
```

SemanticProposal can route to `ATTRIBUTE`, but persistability **denies** materialization (`attribute_not_materializable`). Existing `Fact` rows are **not** first-class Attribute knowledge (they are event/entity-anchored ontology predicates such as `attribute.amount`).

## Executive definition

```text
WHAT_IS_AN_ATTRIBUTE_IN_PKE?

An Attribute is a descriptive property of an entity in a named dimension,
carrying a typed value that characterizes the entity without asserting a
world-condition in a State dimension, a typed inter-entity link (Relation),
or a temporal occurrence (Event).
```

Refines ADR 0016 wording: Attribute is **not** defined as “immutable.” Many attributes evolve (color after paint, weight, price). The boundary is **semantic role**, not mutability.

## Primitive boundary

| Primitive | Role |
|---|---|
| **Attribute** | Descriptive property/value on one entity (`color=silver`, `area=200 m²`) |
| **State** | Temporally meaningful condition in a State dimension (`open`, `broken`, `overdue`, observed fill) |
| **Relation** | Typed link between two entities (`employed_by`, manufacturer→Toyota) |
| **Event** | Occurrence with change/lifecycle semantics |
| **Type** | Entity classification (`is a car`) — EntityKind / ontology typing, **not** Attribute |

### Attribute vs State

| Signal | Attribute | State |
|---|---|---|
| stable_property_semantics / “é …” descriptive | yes | no |
| condition_semantics / “está …” condition | no | yes |
| lives in State dimension catalog | no | yes |
| example | silver, 200 m², model year | open, broken, overdue, tank has 20 L |

**Do not** use mutable vs immutable.

### Attribute vs Relation

Entity-valued properties that name another entity as participant in a typed link are **Relation** (manufacturer, owner, employer). Do not store as `Attribute.text = "Toyota"`.

### Attribute vs Type

“O Corolla é um carro” is classification. Must not become `attribute.type=car`. Future router/assessment should block TYPE→ATTRIBUTE; today provider-shaped signals may route ATTRIBUTE but **must not persist**.

## Value representation

| form | use |
|---|---|
| concept_value_id | optional enum-like values when curated later |
| text_value | qualitative lexical (color names) — normalized, not free dump |
| numeric_value | quantities, years |
| unit | SI/common unit string for quantities |
| date/year | model_year as int/year; full dates later |
| entity ref | **prefer Relation** — do not default Attribute→entity |

Minimum for first implementation wave: **dimension + value_kind + (text | numeric+unit | year)**.

## Quantity vs MEASUREMENT-01

Descriptive quantities (capacity, area, weight, height) can be Attribute fields:

```text
numeric_value + unit
```

without closing **MEASUREMENT-01**.

Observed quantities (“tanque está com 20 litros”) remain **State** (`state.observed_quantity` / provisional measurement). MEASUREMENT-01 stays open for rich observation/measurement semantics.

## Temporal semantics

```text
historical values: allowed (valid_from / valid_to or supersession chain)
current value:     is_current (or valid_to IS NULL) — do not blindly copy State API
correction:        supersession with correction provenance (future Correction Engine)
evolution:         Event (e.g. repaint) may *cause* Attribute change; Event ≠ Attribute
```

Attribute evolution ≠ automatic State supersession reuse. Correction ≠ evolution (same storage shape, different epistemic intent).

## Cardinality

```text
single-valued dimensions: color (usual), model_year, area, weight, height, capacity
multi-valued dimensions:  languages, tags, possibly materials — metadata later
```

Identity for single-valued current row: `(user_id, entity_id, dimension)` with history via supersession. Do **not** collapse history into one value.

Cardinality metadata on dimensions is deferred (not required to start).

## Color

```text
representation: AttributeDimension color + normalized lexical text_value
                (optional concept_value later — not a CORE color palette now)
CORE addition now: NO
```

## New / facilities

```text
new:
  primitive: Attribute (relative_age / newness) — context-sensitive; often DEFER
  representation: deferred dimension; never force State
  ontology addition now: NO

facilities:
  subject may be Entity gap (“instalações”)
  newness remains Attribute-candidate
  safe unresolved acceptable until Entity + Attribute storage exist
```

## Candidate models

| model | semantic fidelity | queryability | extensibility | schema complexity | recommendation |
|---|---:|---:|---:|---:|---|
| A entity+concept+value | medium | medium | medium | low | reject — conflates dimension/value |
| B entity+dimension+opaque value | high | low–med | high | low | interim only |
| C entity+dimension+typed columns | high | high | high | medium | **adopt (minimal)** |
| D JSON payload | medium | low | very high | low | reject as primary |

## Recommended model (conceptual — not implemented)

```text
EntityAttribute (name TBD)
  id
  user_id                 # mandatory isolation
  entity_id
  dimension_id / dimension_key   # AttributeDimension ontology concept
  value_kind              # text | number | year | …
  text_value              # nullable
  numeric_value           # nullable
  unit                    # nullable
  concept_value_id        # nullable, optional later
  valid_from / valid_to   # nullable
  observed_at
  is_current
  supersedes_id
  source_id / raw_input_id
  confidence
  created_at
```

Resolver levels (future):

```text
1) dimension resolution
2) value resolution / normalization
```

Analogous conceptually to State Dimension/Value, not required to share tables.

## Query implications (future)

```text
entity + dimension → current value(s)
entity + dimension + temporal → historical
truth: known | unknown | historical_ambiguity | multi-value unresolved
```

QueryIR needs Attribute intent filters later; **not** implemented in I11.12.

## Current persistence audit

```text
IS_ATTRIBUTE_CURRENTLY_PERSISTED_AS_FIRST_CLASS_KNOWLEDGE?
NO

Notes:
- Semantic ATTRIBUTE routes but is non-materializable.
- Fact(attribute.*) exists for event-anchored predicates (amount/mileage) — different concept.
- State/Relation/Event first-class; Attribute is not.
```

## Schema decision

```text
DOES_FIRST_CLASS_ATTRIBUTE_REQUIRE_SCHEMA_V8?
YES
```

Conceptual table only (no migration in I11.12): `entity_attributes` (or `attributes`) as above.

## Ontology (this increment)

```text
none
CORE remains 65
```

Do not add `attribute.color` / color values / `property.new` until storage lands.

## SemanticProposal audit

Present: `attribute_expression`, `stable_property_semantics`, entities, temporal.

Gaps for quantities: no first-class `numeric_value`/`unit` on proposal — acceptable for design; future may extend proposal or parse expression. Prompt redesign not required now.

Router: `stable_property_semantics` → ATTRIBUTE; `condition_semantics` → STATE. Gap: TYPE classification can still look like ATTRIBUTE (AT14) — assessment debt.

## Deferred work

```text
ATTRIBUTE-01          implement first-class Attribute storage (v8) + materializer
ATTRIBUTE-TYPE-01     block TYPE→ATTRIBUTE at assessment/router
ONTOLOGY-COVERAGE-01  color/new/facilities wait on Attribute model
MEASUREMENT-01        unchanged — observed quantity ≠ descriptive Attribute
SEMANTIC-QUERY-01     Attribute query after storage
TIME-01               Attribute temporal validity details
```

## Explicit non-goals (I11.12)

schema v8 · ontology expansion · Correction Engine · event-derived attribute transition · NL Attribute UX · holdout · live
