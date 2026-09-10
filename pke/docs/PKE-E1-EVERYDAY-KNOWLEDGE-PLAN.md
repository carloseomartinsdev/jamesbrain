# PKE E1 — Everyday Knowledge Foundation (Plan)

**Status:** `E1.1 COMPLETE` · `E1.2 COMPLETE` · `E1.3 COMPLETE` · `E1.4 COMPLETE` — **`PKE_E1 = FROZEN`**  
**Project:** `pkeagent`  
**Origin:** JAMES Beta × PKE v1 integration  
**Date:** 2026-09-04  
**ADR E1.1:** `docs/decisions/0076-principal-binding-and-self-resolution.md`  
**ADR E1.2:** `docs/decisions/0077-everyday-attribute-registry-e12.md`  
**ADR E1.3:** `docs/decisions/0078-clarification-quality-e13.md`  
**ADR E1.4 / Freeze:** `docs/decisions/0079-e1-everyday-knowledge-foundation-freeze.md`  
**Freeze note:** `docs/PKE-E1-FREEZE.md`  
**Report:** `docs/reports/E1.4-FULL-REVALIDATION-AND-FREEZE.md`

```text
PKE v1          = FROZEN (do not reopen casually)
Product API v1  = FROZEN public DTO contract
JAMES Portal    = semantically read-only for this build
Knowledge schema = v11 (PrincipalBinding); E1.2 Attribute registry; E1.3 capability policy
PKE E1          = FROZEN (Everyday Knowledge Foundation)
E2              = NOT AUTHORIZED (Beta evidence first)
```

## Frozen review decisions (D-E1-01 … D-E1-20)

See authorization brief. Summary of constraints in force:

| ID | Decision |
|----|----------|
| D-E1-01 | PrincipalBinding ∈ Knowledge |
| D-E1-02 | AuthUser.id ≠ Entity.id |
| D-E1-03 | Lazy principal Entity creation |
| D-E1-04 | Bootstrap is attribute-neutral |
| D-E1-05 | Self lexemes resolve via binding |
| D-E1-06 | `brand` = Attribute in E1 (not required Relation) |
| D-E1-07 | `manufacturer` ≠ automatic alias of `brand` |
| D-E1-08/09 | `meu carro` → vehicle Entity (+ ownership), not flattened on principal |
| D-E1-10/11 | Controlled Attribute registry; LLM cannot invent dimensions |
| D-E1-12 | Deterministic repair before prompt tuning |
| D-E1-13/14 | Schema v11; idempotent binding |
| D-E1-15/16 | CLARIFY only if user can unblock; else UNSUPPORTED |
| D-E1-17 | No IR / no commit remains safety rule |
| D-E1-18/19 | Product API + JAMES unchanged semantically |
| D-E1-20 | Finish E1.1 (+ regression) before E1.2 |

---

## 1. Executive summary

Beta use exposed two **independent structural gaps** that block everyday continuity:

| Gap | Symptom | Root |
|-----|---------|------|
| **E1-A Principal / Self** | `Meu nome é Carlos.` → subject=`Carlos` named | No AuthPrincipal → world-model Entity binding; no safe contextual self |
| **E1-B Everyday Attributes** | same utterance → `missing_attribute_dimension` → CLARIFY | Controlled Attribute dimensions omit `name` (and brand/model/…) |

Observed positive safety property (preserve):

```text
unknown / unsafe dimension → no IngestIR → no Knowledge commit
```

E1 goal is **not** permissiveness. It is:

> Expand what PKE can represent **safely**, so JAMES Beta can continue everyday tests without Portal-side semantic hacks.

Success bar (stop criterion):

- Self name write + cross-conversation query works.
- Owned vehicle brand/model/color can be represented when resolution is safe.
- Unknown / invented dimensions still abstain or unsupported — **never** auto-create dimensions or false-commit.

---

## 2. Current architecture (relevant slice)

```text
JAMES / Web
    ↓ public DTO only
Product /api/v1  (schema 1.4) — identity, conversation, idempotency, recovery
    ↓ AuthUser.id as Engine user_id
EngineGateway → Engine v1 FROZEN
    Interpreter (prompt v4) → SemanticProposal (proposal, never truth)
    Resolution / AttributeResolution / EntityResolver
    Persistability → ExecutionReadiness → CapabilityStrategy
      EXECUTE | CLARIFY | SAFE_ABSTAIN
    ↓
Knowledge Core v1 FROZEN (schema v10, CORE 65)
    entities, entity_attributes (since v8), relations, events, …
```

### Identity today

| Layer | ID | Role |
|-------|----|------|
| Product | `AuthUser.id` (e.g. `james-1`) | Auth, Product ownership, Engine user scope |
| Knowledge | `entities.id` | World-model Entity |
| Binding | **none** | ADR 0026 deferred principal-reference; ADR 0071 forbids `AuthUser.id == Entity.id` |

`PersonalContext` already carries `user_id`, `recent_entity_ids`, `confirmed_aliases`, `last_by_role_key` — conversational memory, **not** durable principal Entity binding.

### Attribute today

| Piece | Location | Notes |
|-------|----------|--------|
| Storage | `entity_attributes` (schema ≥8, current **v10**) | Typed `value_kind`, `is_current`, `supersedes_id`, temporal fields |
| Write resolution | `attribute_resolution.py` | Controlled aliases only |
| Materializable dimensions (code) | `color`, `model_year`, `weight`, `height`, `area`, `capacity` | Explicit comment: brand/name/plate remain unresolved |
| CORE Attribute concepts | `attribute.amount`, `mileage`, `maintenance_type` | Not the same set as write dimensions |
| Persistability | requires `attribute_dimension_key` + `attribute_value_kind` | Else `attribute_dimension_value_required` |
| Capability | `missing_attribute_dimension` → CLARIFY (medium) | Even when user already supplied a clear unsupported property |

### Ownership / vehicle today

- `relation.owns` exists in semantic aliases (`possui`, `é meu`, …).
- Entity create-on-write exists via `EntityResolver` + materializer `CREATE_CANDIDATE`.
- No dedicated “my car” shortcut Attribute; correct shape is **Entity (vehicle) + Relation/context to self + Attributes on vehicle**.

### Clarification UX today

- Engine owns `question_key` (e.g. `clarify.attribute.dimension`).
- Product `presenter._QUESTION_TEXT` has **no** entry for `clarify.attribute.dimension` → falls back to generic *“Pode detalhar um pouco mais?”*.
- CapabilityStrategy does **not** distinguish “user can answer this slot” vs “dimension is permanently unsupported in registry”.

### Evidence case (canonical)

```text
request_id: req_01M1PC597P9T01H7KBH2WC9YA3
raw: "Meu nome é Carlos."
proposal: Attribute + subject named Carlos + attribute_expression "name is Carlos"
IR: none
Knowledge mutate: none
outcome: needs_clarification / missing_attribute_dimension
```

---

## 3. Observed gaps

### GAP E1-A — Principal / Self

Cannot reliably map first-person / possessive self references to a durable person Entity owned by the authenticated principal.

Mis-routing risk already observed: self-name constructions treated as **named person subject** (`Carlos`) instead of **self + name value**.

### GAP E1-B — Everyday Attribute Expansion

Controlled dimension registry too small for Beta everyday speech (`name`, `brand`, `model`, …).

Secondary quality gap (E1.3): unsupported-but-clear properties become **CLARIFY**, which is epistemically misleading when more user text cannot enable commit.

### Non-gaps (do not “fix” in JAMES)

- Product API / adapter path works.
- Isolation / AuthUser as Engine identity works.
- Safe non-commit on unresolved Attribute works.

---

## 4. Relevant ADRs / freeze docs

| Doc | Relevance to E1 |
|-----|-----------------|
| ADR 0026 | Deferred principal-reference / implicit user as participant; **forbids fabricating Entity("eu")** without architecture |
| ADR 0071 | `Product User ID ≠ world-model Entity ID`; Engine user = AuthUser.id |
| ADR 0030 | Attribute definition; **manufacturer/owner → prefer Relation**, not Attribute text; TYPE ≠ Attribute |
| ADR 0031 | Typed `value_kind`; dimension identity = stable `dimension_key` (+ optional ontology FK); storage may predate CORE concept |
| ADR 0069 / ENGINE-V1-FREEZE | Engine v1 frozen (prompt v4, deepseek-chat, readiness/strategy) |
| ADR 0075 / PKE-V1 / PRODUCT-V1-FREEZE | Full stack freeze; reopen only on invariant violation evidence |
| PRODUCT-V1-UX-BOUNDARY | Public outcomes; frontend non-semantic |

**Reopen policy for E1:** treat Core/Engine/Product freezes as **defaults**. E1 may introduce **additive** Knowledge schema and controlled Engine extensions only with explicit ADR(s) under E1 numbering — not silent edits to frozen “v1 meaning”. Prefer additive registries and bindings over rewriting v1 contracts.

---

## 5. Self binding design

### Invariant (non-negotiable)

```text
AuthUser.id  ≠  Entity.id
```

Introduce an explicit binding:

```text
Auth Principal (user_id)
        ↓
PrincipalBinding (durable, per-user, 1:1 preferred for v1 of E1)
        ↓
World-model Entity (type: person, user-scoped)
```

### Conceptual API (names illustrative)

```text
ensure_principal_entity(user_id) -> EntityId
resolve_self_mention(mention, context) -> EntityResolution
```

Requirements:

1. Locate existing binding; reuse same Entity.
2. Create Entity only when policy allows (deterministic type `entity.person`).
3. Create binding deterministically and idempotently.
4. Never share Entity across users.
5. Preserve Knowledge `user_id` isolation on Entity and Attributes.
6. Do **not** store raw bearer tokens or Product passwords in Knowledge.

### Where binding lives (decision to confirm in E1.1.1)

| Option | Pros | Cons |
|--------|------|------|
| **A. Knowledge table** `principal_bindings(user_id → entity_id)` | World-model truth near Entities; Engine can resolve without Product store | Requires Knowledge migration (v10→v11); Core reopen discipline |
| **B. Product table** only | No Knowledge schema change | Engine/Knowledge path needs Product dependency (layering smell) |
| **C. Hybrid** Product mirror + Knowledge source of truth | Ops clarity | Dual-write risk |

**Plan recommendation (pending review):** **Option A** — Knowledge-owned binding, because self is a **semantic** identity, not a Product conversation concern. Product continues to pass only `AuthUser.id`.

### Bootstrap timing

Evaluate (choose in E1.1.1, do not implement all):

1. Lazy on first self-resolving utterance / first Knowledge write for user.
2. Eager on first authenticated Engine invocation.
3. Explicit Product hook after register/login (optional later).

Prefer **lazy idempotent ensure** to avoid empty Entities for users who never speak.

### Resolution of self

Extend contextual path already sketched by `MentionReferenceKind.CONTEXTUAL` + `EntityResolver._from_context`:

```text
"eu" | "me" | "meu/minha/…" (when referring to principal, not possessed object head)
        ↓
reference_kind = contextual (or dedicated self cue)
        ↓
PrincipalBinding
        ↓
EntityResolution(RESOLVED, entity_id=principal_entity)
```

Possessive constructions that attach to **another** entity (`meu carro`) must resolve:

```text
possessor = self (principal entity)
head = vehicle entity (create/resolve)
link = relation.owns (or equivalent already supported)
attributes = on vehicle entity — not on self
```

Do **not** invent `attribute.car`.

### Self vs named (Interpreter implication)

For:

```text
Meu nome é Carlos. / Eu me chamo Carlos.
```

Desired proposal shape:

```text
subject = self (contextual)
attribute_expression / value = Carlos
dimension candidate = name
```

Not:

```text
subject = named Carlos
```

Negative cases (must keep working / not collapse):

| Input | Must not do |
|-------|-------------|
| `Eu vi Carlos ontem.` | `self.name = Carlos` |
| `O nome do meu amigo é João.` | `self.name = João` |
| `Carlos disse que meu carro é vermelho.` | treat Carlos as self |

Implementation preference order (analyze in E1.1.3 / Interpreter implications):

1. **Deterministic post-proposal normalization** for high-precision self-name patterns (no new LLM authority).
2. Targeted prompt examples / v4→v4.1 or E1 prompt increment **only if** (1) insufficient — document as Engine extension ADR, not silent freeze break.
3. Avoid raw-string Product/JAMES hacks.

---

## 6. Principal lifecycle

```text
first need
   → ensure_principal_entity(user_id)
       → SELECT binding
       → if missing: CREATE person Entity (user-scoped) + INSERT binding (same UoW)
   → subsequent self refs reuse entity_id

user deletion / wipe (POST_E1 if needed)
   → binding + entity subject to existing user isolation / purge rules
```

Open: whether principal Entity `canonical_name` starts empty, mirrors display name, or waits for `name` Attribute (prefer **Attribute as source of spoken name**, Entity canonical_name updated carefully or left secondary).

---

## 7. Attribute extension design

### Preserve v1 principles

- LLM proposes; resolver decides.
- No automatic dimension creation from free LLM strings.
- Typed values (`text` | `number` | `year` | `date` | `concept`) per ADR 0031.
- Temporal supersession (`is_current`, `valid_from`/`valid_to`, `supersedes_id`) preserved.
- TYPE / Relation / State boundaries preserved.

### Registry strategy (conceptual CORE / EXTENDED)

Today there is **no** formal EXTENDED registry — only a Python alias map. E1.2 should introduce an explicit **Attribute Dimension Registry** (code-first is acceptable for E1; ontology CORE expansion optional).

```text
ATTRIBUTE_DIMENSION_REGISTRY
  tier: core_v1 | everyday_e1 | (future)
  key: name | brand | …
  value_kind: text | …
  aliases: [...]
  subject_type_constraints: optional (person | vehicle | …)
  privacy_class: normal | sensitive
  materializable: bool
  queryable: bool
```

LLM never writes registry rows.

### Candidate dimensions for Beta unlock (analyze before enable)

| Key | Priority for Beta | Notes / risks |
|-----|-------------------|---------------|
| `name` | **P0** | Person self; text; privacy sensitive |
| `brand` | **P0/P1** | Vehicle everyday; ADR 0030 prefers manufacturer as Relation — see open questions |
| `model` | **P1** | Decompose from “Honda Civic”; avoid single blob |
| `nickname` | P2 | Near-duplicate of name; may defer |
| `profession` / `occupation` | P2 | Near-synonyms; pick one or alias to one key |
| `manufacturer` | review | Likely **Relation**, not Attribute |
| `plate` | P2 | Privacy; format validation |
| `material` | P2 | Broad; weak type constraints |
| `type` | **defer / dangerous** | Collides with TYPE/classification (ADR 0030/0031) |

**Do not enable the full list by default.** Enable after redundancy, alias, domain, typing, privacy, and query review per key.

### Recommended E1.2 first enable set (proposal for review)

```text
P0: name
P1: brand, model   (vehicle-constrained)
Already v1: color, model_year, weight, height, area, capacity
Defer: nickname (alias→name?), profession/occupation, plate, material, type, manufacturer-as-attribute
```

### Brand / “Honda” ambiguity

```text
"Meu carro é um Honda."
```

Safe everyday resolution **only if** controlled evidence supports vehicle brand (lexicon / alias / constrained pattern), producing Attribute `brand=Honda` on a **vehicle** entity linked to self — **or** Relation form if ADR 0030 path is chosen.

If confidence insufficient → **UNSUPPORTED** or **CLARIFY(entity/brand sense)** — not optimistic commit.

```text
"Meu carro é um Honda Civic."
```

Prefer split `brand=Honda` + `model=Civic` when deterministic decomposition exists; else safe abstain rather than `brand="Honda Civic"` if that would poison queries.

### Identity vs property (must not collapse)

| Utterance | Subject | Knowledge shape |
|-----------|---------|-----------------|
| `Meu nome é Carlos.` | self (person) | Attribute `name` on principal Entity |
| `Meu carro é um Honda.` | vehicle (+ ownership) | Attribute/Relation on vehicle Entity; not `self.brand` |

---

## 8. Value typing

| Dimension | value_kind | Notes |
|-----------|------------|--------|
| name | `text` | Normalized display; not free dump of whole sentence |
| brand | `text` (E1) or later `concept` | Controlled vocabulary preferred |
| model | `text` | |
| color | `text` (existing) | |
| model_year | `year` | |
| weight/height/area/capacity | `number` + unit | existing |

Reject `key:string` / `value:any` bags.

---

## 9. Resolver changes (planned)

`attribute_resolution.py`:

- Read from Attribute Dimension Registry (not only hard-coded `_DIMENSION_QUERY_ALIASES`).
- Add `name` / `brand` / `model` resolvers with **high-precision** patterns.
- Keep “invented dimension → None”.
- Distinguish registry miss (unsupported) vs incomplete slot (clarify).

`EntityResolver`:

- Self/contextual → principal binding.
- Named person remains named path.
- No cross-user alias bleed.

`persistability` / `execution_readiness` / `capability_strategy`:

- When proposal clearly names a **known-unsupported** or **out-of-registry** dimension with complete value → prefer **SAFE_ABSTAIN / UNSUPPORTED** over CLARIFY.
- When dimension is **in registry** but value/slot missing → CLARIFY remains valid.
- When dimension is **in registry** and value present → EXECUTE path.

This is the core of **E1.3** and must be designed with E1.2 so Beta does not get endless “detalhe mais” loops.

---

## 10. Interpreter implications

- Prompt v4 frozen under Engine v1; E1 may need an **additive** interpretation policy:
  - Prefer deterministic repair for self-name / meu-carro patterns.
  - Optional E1 prompt delta only with ADR + regression proof.
- Never grant LLM authority to invent persistable dimensions.
- Preserve correction / multi-primitive / Event safety from v1.

---

## 11. Persistence implications

- Reuse `entity_attributes` — **no need** for a parallel KV store.
- Principal binding table (if Option A) → Knowledge migration **v10 → v11** (or next), with dual apply to tenant + `mom_base_*` only if this repo follows that ops model; for local PKE, version stamp + migration runner.
- Ownership: prefer existing Relation materialization (`relation.owns`) where already supported; gap-fill only if C04–C08 cannot be met.
- Supersession for color history (C09) should already be expressible; verify query path for “current” vs “previous”.

---

## 12. Query implications

Must support (after writes):

| Query | Needs |
|-------|--------|
| `Qual é o meu nome?` / `Como eu me chamo?` | self resolve + attribute `name` |
| `Qual é o meu carro?` | self → owns → vehicle; present brand/model |
| `Qual é a cor do meu carro?` | vehicle resolve + `color` current |
| Historical color | current filter + superseded chain / valid_to |

Query resolution must use same registry keys and self binding; no Product-side answer fabrication.

---

## 13. Temporal implications

- New dimensions obey same validity / `is_current` / supersession as v1 Attributes.
- `Pintei meu carro de preto` may be Event+Attribute or Attribute replace — follow existing change_semantics routing; do not special-case by weakening Event/Attribute boundary.
- `name` changes: supersede prior current name; do not delete history.

---

## 14. Clarification implications (E1.3)

| Situation | Outcome |
|-----------|---------|
| Missing answerable slot (which vehicle?) | CLARIFY + specific `question_key` |
| Dimension in registry, value missing | CLARIFY dimension/value |
| Clear utterance, dimension **not** materializable | UNSUPPORTED / SAFE_ABSTAIN — **not** fake CLARIFY |
| Ambiguous brand vs classification | CLARIFY only if user answer can disambiguate; else abstain |

Product presenter: add truthful copy for `clarify.attribute.dimension` **and** for unsupported everyday limitation — without exposing IR.

JAMES remains unaware of registry internals.

---

## 15. Product compatibility

```text
POST /api/v1/messages
response fields unchanged:
  status, type, text, operation, clarification, data, error, request_id, …
```

- No JAMES semantic shortcuts.
- No DTO breakage.
- Engine user identity remains server AuthUser.id.
- DEV_AUTH remains opt-in only.

---

## 16. Migration strategy

1. **Design ADR(s)** for E1 (principal binding; attribute registry; clarify vs unsupported).
2. If Knowledge table needed: migration script bumping `STORAGE_SCHEMA_VERSION`, idempotent, tested on empty + existing v10 DBs.
3. No rewrite of historical Attributes.
4. Registry is code/config in E1 (not user-editable).
5. Holdout corpora remain untouched unless explicitly extended with E1 suite (separate path).

---

## 17. Test matrix

### Canonical positive (C01–C09)

As specified in the E1 build brief (self name write/query/paraphrase; vehicle Honda / Honda Civic; color; cross-conversation; current color; historical if supported).

### Negatives (N01–N05)

Unknown dimension; invented dimension; self vs named; friend’s name; cross-user isolation.

### Additional planned

| ID | Case | Expect |
|----|------|--------|
| C10 | `Eu tenho um Honda.` | ownership + vehicle + brand if safe |
| N06 | `Meu nome é Carlos.` before name enabled | UNSUPPORTED not endless CLARIFY (once E1.3 lands; or interim documented) |
| N07 | Cross-user principal binding | no shared Entity |
| R01–Rn | Existing Attribute/State/Event/Relation/Product suites | pass |

---

## 18. Regression strategy

After each increment:

1. Targeted unit/integration for that increment.
2. Before E1.4 close: full `pytest tests/ -m "not live"` ≥ last frozen baseline (P-R ~5097; **E1.4 closed at 5137 passed / 8 live deselected**).
3. Product API contract tests unchanged in spirit.
4. No holdout burn for E1 exploration.
5. Optional small live smoke only after deterministic green.

---

## 19. Implementation increments (after plan approval)

```text
E1.1.1  Principal model + ADR draft
E1.1.2  Principal binding persistence + migration
E1.1.3  Contextual self resolution
E1.1.4  Self write/query (depends on name dimension or temporary fixture strategy)
        ↓
E1.2.1  Attribute dimension registry architecture
E1.2.2  Everyday dimension enablement (name → brand/model…)
E1.2.3  Value typing & constraints
E1.2.4  Write resolution
E1.2.5  Query resolution + ownership presentation
        ↓
E1.3.1  Clarification vs unsupported classification
E1.3.2  Presenter / question_key rendering
        ↓
E1.4    Full regression + E1 freeze note + Beta reopen checklist
```

**Ordering note:** E1.1.4 practically needs `name` (E1.2.2 P0) or a thin vertical slice that lands `name` with principal binding together. Prefer a **vertical thin slice** after E1.1.2:

```text
Slice S0: binding + name write/query + clarify/unsupported fix for name
Slice S1: vehicle ownership + brand/model
Slice S2: color history / query polish
```

Still gate each slice with tests before the next.

---

## 20. Risks

| Risk | Mitigation |
|------|------------|
| Collapsing AuthUser into Entity | Explicit binding table; tests N05/N07 |
| Brand as Attribute vs Relation conflict (ADR 0030) | Decide in ADR before C04; document chosen representation |
| `type` dimension reopening TYPE leak | Do not enable `type` in E1 |
| Prompt change regresses Interpreter | Prefer deterministic normalization; prompt delta only with suite |
| Fake CLARIFY loops in Beta | E1.3 classification mandatory before Beta reopen |
| Over-expanding dimension list | P0/P1 only; rest POST_E1 |
| Knowledge schema churn | Single migration; additive only |
| Optimistic persistence | Keep deny-by-default; registry allow-list only |
| “meu carro” as Attribute on self | Force Entity+ownership modeling |

---

## 21. Open questions (must answer before coding)

1. **Binding storage:** Knowledge `principal_bindings` (recommended) vs Product-only vs hybrid?
2. **Brand representation:** Attribute `brand` vs Relation `manufacturer`/`brand` concept — which is E1-canonical for “é um Honda”?
3. **Canonical name field:** Is spoken name **only** Attribute `name`, or also `entities.canonical_name`?
4. **Interpreter strategy:** Deterministic repair only vs prompt increment for E1?
5. **Schema version:** Confirm v10→v11 bump acceptable as E1 Core additive reopen under ADR?
6. **Profession vs occupation:** one key + aliases, or defer both?
7. **Nickname:** alias to `name` or separate?
8. **Eager vs lazy** principal Entity creation?
9. **Query “Qual é o meu carro?”** presentation: brand+model concatenation vs structured `data` only (API already has `data` — keep text truthful)?
10. **Historical “cor anterior”:** already query-supported or POST_E1 if missing?
11. **CapabilityStrategy change:** is reclassifying unsupported dimensions away from CLARIFY considered Engine v1 reopen or E1 additive policy ADR?
12. **Multi-vehicle:** if two cars exist, does “meu carro” CLARIFY which one? (likely yes — do not auto-pick unsafely)

---

## 22. Explicit non-goals (E1)

As in build brief: study/work journeys, behavioral inference, goals/tasks/reminders, Action Engine, family ontology, automatic arbitrary concept creation, general world ontology, JAMES semantic logic, Product DTO redesign, native clients, streaming, etc.

---

## 23. Epistemological / architectural principles

```text
When PKE cannot represent safely → do not persist.
Expand safe representation; do not become LLM→KV.
Natural language → proposal → controlled resolution → typed knowledge
  → validation → persistence → deterministic retrieval.
Clarification only when user information can realistically unblock execution.
```

---

## 24. Freeze / Beta reopen checklist (after implementation)

```text
[x] E1 ADRs accepted (0076–0079)
[x] C01–C09 / N01–N05 green (plus agreed extras)
[x] Full non-live regression green (5137 passed)
[x] Isolation proven
[x] Public API DTO unchanged
[x] Cross-conversation Knowledge proven
[x] JAMES unchanged semantically (presentation / DTO only)
[x] E1 freeze note published (docs/PKE-E1-FREEZE.md)
[ ] JAMES Beta may resume; new gaps classified (BUG/REGRESSION/PKE GAP/…)  ← operator
```

---

## 25. Recommended decision for reviewers

Authorize planning **complete**. Next human decision gate:

```text
APPROVE_PLAN_WITH_OPEN_QUESTIONS_RESOLVED
  → then start E1.1.1 (Principal model ADR) only
```

or

```text
REVISE_PLAN
  → comment on open questions §21
```

**Do not implement until open questions 1–2–4–5–11 are answered at minimum** (binding locus, brand shape, interpreter strategy, schema bump, clarify/unsupported policy).

---

## 26. Document control

| Item | Value |
|------|--------|
| Path | `docs/PKE-E1-EVERYDAY-KNOWLEDGE-PLAN.md` |
| Implements code? | **No** (plan only) |
| Changes JAMES? | **No** |
| Reopens PKE v1 freeze? | **Not yet** — E1 will require explicit additive ADRs if approved |

```text
WAITING_FOR_PLAN_REVIEW
```
