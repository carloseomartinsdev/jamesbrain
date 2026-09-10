# ADR 0029 — Controlled Ontology Coverage Expansion (I11.11)

## Status

Accepted — I11.11

## Context

After I11.6–I11.10, semantic safety is green but useful coverage still abstains when a recognized sense has no CORE concept. Debt **ONTOLOGY-COVERAGE-01** tracked gaps such as `install`, facilities, currency exchange, color, and `new`.

Freeze for this increment:

```text
Ontology expansion must reduce safe abstention.
Ontology expansion must NOT increase false canonicalization.
```

Not in scope: mass generation, LLM-created CORE, adaptive aliases, taxonomy redesign, schema change.

## Observed gaps (candidates)

| candidate | prior observation |
|---|---|
| install | LS1–LS3 / PX1 / E6 ontology gap |
| facilities | PX2 / LS4 attribute sense |
| currency_exchange | LS8 |
| color | ATTR color utterances |
| new | property_new sense |
| return / give / cancel / reserve / book / renew / update / travel / arrive / document / place / home_component / product | historical audit only |

## Governance criteria

| Layer | When |
|---|---|
| CORE | broadly reusable, foundational, stable, not user-specific |
| EXTENDED | valid/reusable but domain-oriented (no auto-promotion) |
| PERSONAL | conceptual only here — no user ontology learning |
| DEFER | sense exists; representation or evidence insufficient |
| REJECT | would coerce nearest concept or blur senses |

## Candidate matrix

| candidate | sense | primitive | layer | parent | add now? | reason |
|---|---|---|---|---|---|---|
| install | install | ACTION/EVENT | CORE | *(root action)* | **YES** | cross-domain (home appliance, software, service); stable; distinct from replace/repair |
| facilities | facilities | ENTITY/ATTRIBUTE | DEFER | — | NO | entity/property “instalações”; PX2 safe unresolved OK; not action |
| currency_exchange | currency_exchange | ACTION | DEFER | — | NO | valid sense; sparse evidence; “trocar” polysemy risk without richer constraints |
| color | (attribute) | ATTRIBUTE | DEFER | — | NO | representation unclear (dimension vs value payload vs concept) |
| new | property_new | ATTRIBUTE | DEFER | — | NO | relative age descriptor; not State; do not force State |
| return/give/cancel/… | mixed | mixed | DEFER | — | NO | insufficient controlled evidence this increment |

## Approved additions

```text
key:    action.install
kind:   ACTION
layer:  CORE
parent: none (root action; sibling of buy/pay/attend — not under maintain)
aliases: instalou, instalei, instalaram, instalar, install(ed), instalação / instalação do, fez a instalação
         (forbid facilities plurals / “são novas”)
reason: recognized INSTALL sense was safe-abstaining; concept is foundational and cross-domain
```

CORE count: **64 → 65** (ACTION 6 → 7). EXTENDED unchanged (0). PERSONAL unchanged (0).

## Rejected / deferred

- **facilities** — lexical sense ≠ `action.install`; no CORE entity this round; safe unresolved remains correct.
- **currency_exchange** — defer until alias/sense constraints can keep FALSE_CANONICALIZATION=0 vs replace / exchange ideas.
- **color / new** — representation debt; Attribute safety forbids State coercion.
- Historical verbs/nouns — not promoted on frequency alone.

## Hierarchy

`action.install` is **not** a child of `action.maintain` or `action.replace`. Install is placement/commissioning, not repair or substitution. No safe specialized parent → root ACTION placement.

## Alias safety

- Contextual aliases only; gate requires `SemanticSense.INSTALL`.
- Facilities plural and “são novas” forbidden on install alias.
- Bare “trocar” is **not** a global alias for replace or currency_exchange.
- General physical replace cues (`troquei o/a`) require `REPLACE_PHYSICAL` sense and forbid idea/currency/clothing/install.

## Regression safety

- OC1–OC3 → `action.install`; OC4 → `action.replace`; OC5 → `action.maintain`; OC6 → not install.
- PX1 may canonicalize to install; PX2 must never become install.
- Nearest-concept coercion unchanged: recognized sense + gap → unresolved (unless approved concept exists).
- I11.8 partial canonicalization preserved; I11.10 EventParticipant unchanged; schema **v7**.

## Coverage impact (focused OC corpus, n=6)

```text
canonical coverage: 5/6 (was 3/6 with install gap on OC1–OC3)
safe abstention:    1/6 (OC6 facilities)
ontology gaps:      ≥1 (facilities)
false canonicalization: 0
```

Do not extrapolate to global ontology percentages.

## Deferred ontology work

```text
ONTOLOGY-COVERAGE-01 → PARTIAL (install closed; facilities/currency/color/new remain)
ADAPTIVE-ALIAS-01    unchanged (not implemented)
INTERPRETER-RETRY-01 unchanged
SEMANTIC-QUERY-01    residual (broader query coverage)
TIME-01              unchanged
```

## Explicit non-goals confirmed

adaptive aliases · Knowledge Enrichment · Behavioral Memory · Clarification · interpreter retry · holdout · schema v8
