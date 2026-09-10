# ADR 0044 — Correction, Retraction & Evidence Lineage Design Freeze (I11.17)

## Status

Accepted — **design freeze only**. Schema remains **v9**. No Correction Engine implementation.

## Motivation

Frozen principle: *Corrections do not silently erase history.*

Current debt `CORRECTION_ENGINE_DEBT` and relation audit gaps (`nunca trabalhou` ≠ termination)
require an explicit epistemic layer for correction/retraction distinct from:

```text
temporal evolution · Relation termination · State/Attribute supersession
new Measurement · ordinary conflicting evidence · privacy deletion
```

Legacy `IrCorrection` + `CorrectionStrategy.LAST_EVENT` / session `last_event_id` is **not**
acceptable as future correction-target authority (insertion-order / conversational convenience).

## Layering

```text
Event / State / Relation / Attribute / Measurement
→ world-model knowledge assertions (persisted rows)

Correction / Retraction
→ meta-knowledge about assertions (epistemic operations)
```

```text
IS_CORRECTION_A_WORLD_MODEL_PRIMITIVE? NO
IS_CORRECTION_A_KNOWLEDGE_PRIMITIVE? NO
```

Correction is an epistemic operation + lineage record, not a sixth world primitive.

## Semantic boundaries (frozen)

| Phenomenon | Correction? |
|------------|-------------|
| “agora é preto” after color change over time | NO — temporal evolution |
| “não trabalha mais” | NO — Relation termination |
| State supersession via `supersedes_id` / `is_current` | NO — lifecycle bookkeeping |
| New Measurement at later time | NO — new observation |
| Competing evidence without correction language | NO — conflict / ambiguity |
| “corrigindo / na verdade / eu me enganei” with target | YES |
| Explicit “isso estava errado” (no replacement) | YES — retraction-only |
| “apague do sistema” | NO — privacy/admin deletion |

LLM may propose correction intent. Deterministic PKE validates target, effect, transaction.

## Retraction invariant

```text
RETRACT(P) ≠ ASSERT(¬P)
```

Retraction removes positive epistemic support of the targeted assertion.
It does not invent the opposite world proposition.

## Assertion identity

```text
ARE_EXISTING_PRIMITIVE_ROW_IDS_SUFFICIENT_AS_ASSERTION_IDENTITIES?
PARTIALLY → YES for typed references
```

Each persisted row (`events`, `states`, `relations`, `entity_attributes`, `measurements`,
and legacy `facts` where still present) already has a stable `id` + `user_id`.

```text
assertion row identity ≠ semantic proposition identity
```

Repeated identical evidence ⇒ distinct assertions. Targeted retraction of one does not
retract siblings.

Full generic Assertion/Evidence unification (**EVIDENCE-01**) is **not** required to start
Correction if typed KnowledgeReferences are used.

```text
CAN_CORRECTION_ENGINE_BE_IMPLEMENTED_SAFELY_WITHOUT_FULL_EVIDENCE01?
PARTIALLY → YES for bounded Correction Engine
```

EVIDENCE-01 remains deferred for multi-evidence graphs beyond typed ledger needs.

## KnowledgeReference (frozen conceptual)

```text
KnowledgeReference
├── primitive: event | state | relation | attribute | measurement | fact?
├── assertion_id: str   # row id in that primitive's table
└── user_id: str        # isolation — must match session user
```

```text
CAN_ALL_FIVE_PERSISTED_PRIMITIVES_BE_REFERENCED_SAFELY? YES
```

(via typed enum + id; integrity enforced in application layer — polymorphic SQL FK not required)

**Forbidden target heuristics:** `ORDER BY created_at DESC`, highest id, last inserted,
`CorrectionStrategy.LAST_EVENT` as epistemic authority.

Target resolution result:

```text
RESOLVED | AMBIGUOUS | UNRESOLVED
```

AMBIGUOUS / UNRESOLVED ⇒ **no mutation**.

## Correction record (conceptual)

```text
Correction
├── id
├── user_id                          # required, persisted
├── target: KnowledgeReference       # required
├── operation: RETRACT | REPLACE     # required
├── replacement: KnowledgeReference? # required iff REPLACE after materialize
├── replacement_frame?               # SemanticAssertionFrame / proposal — pre-materialize
├── source / raw_input_id            # correcting utterance provenance
├── confidence?
├── recorded_at                      # when correction was recorded ≠ fact time
├── status: COMMITTED | …            # ledger status
└── supersedes_correction_id?        # correction-of-correction lineage (acyclic)
```

`is_current` / `supersedes_id` on world primitives remain **lifecycle/bookkeeping**, not
correction status. Do **not** introduce `knowledge.is_current` for corrections.

Epistemic status vocabulary (future, ledger-derived — not row mutation):

```text
ACTIVE | RETRACTED | CORRECTED
```

## Effective evidence

```text
stored evidence = all persisted rows (auditable forever)
effective evidence = stored assertions not retracted by committed Correction
                    and not superseded-as-corrected by REPLACE lineage tip
```

| Situation | Effective? |
|-----------|------------|
| no correction | ACTIVE |
| RETRACT target | target not effective |
| REPLACE P→Q | P not effective; Q effective (if materialised) |
| correction-of-correction Q→R | follow lineage tip; history preserved |
| two assertions support P; one retracted | other remains support |

Ordinary queries use **effective** evidence.
Historical/audit may include retracted (`include_retracted` future flag — not implemented).

## Atomicity & non-materializable replacement

```text
MUST_RETRACTION_AND_REPLACEMENT_BE_ATOMIC? YES when operation=REPLACE
```

Phases (future):

1. interpret correction  
2. resolve target → RESOLVED or abort  
3. resolve replacement (if any)  
4. validate  
5. materialize replacement (if REPLACE)  
6. persist Correction lineage  
7. single transaction commit  

**Policy — non-materializable / unresolved replacement:**

```text
NO_RETRACTION_UNTIL_REPLACEMENT_MATERIALIZES
```

**Exception:** explicit **retraction-only** (`operation=RETRACT`, no replacement) may commit
independently when target is RESOLVED.

Failed DB / invalid replacement ⇒ no partial correction.

## Persistence architecture (chosen)

```text
GENERIC_CORRECTION_LEDGER_WITH_TYPED_REFERENCES
```

Compare:

| Option | Verdict |
|--------|---------|
| A Existing primitive lineage only | Insufficient (Measurement has no supersedes; conflates lifecycle) |
| B Generic correction ledger + typed refs | **Chosen** — append-only, cross-primitive, auditable |
| C Full Assertion/Evidence layer | Deferred EVIDENCE-01; not blocking bounded Correction |
| D Per-primitive correction tables | Duplicates logic; higher migration cost |
| E Decompose first | Not required — boundaries are distinguishable |

```text
WOULD_CORRECTION_IMPLEMENTATION_REQUIRE_SCHEMA_V10?
YES
```

(new `knowledge_corrections` ledger; no destructive backfill of history)

Legacy v9 rows: treated as **not retracted by any known correction record** — not as a
fabricated “uncorrected” ontology flag. No fake backfill.

## Canonical effectiveness authority

```text
AssertionEffectivenessResolver (future)
  ← Correction ledger
  ← shared by Event/Measurement/Relation/State/Attribute resolvers
```

Repositories remain retrieval-only. Resolvers consume effectiveness; do not each reimplement
correction SQL truth.

Query impact (future):

| Primitive | Impact |
|-----------|--------|
| Event | RESOLVER_EFFECTIVENESS / FILTER_RETRACTED |
| Measurement | RESOLVER_EFFECTIVENESS |
| Relation | RESOLVER_EFFECTIVENESS (≠ terminate path) |
| State | RESOLVER_EFFECTIVENESS (≠ is_current) |
| Attribute | RESOLVER_EFFECTIVENESS (≠ supersedes bookkeeping) |

## Wire / proposal impact

| Layer | Impact |
|-------|--------|
| SemanticProposal | ADDITIVE (`utterance_kind=correct` already exists; target/replacement fields) |
| WireSemanticEnvelope | ADDITIVE |
| WireIngestIR / IngestIR | ADDITIVE (retire LAST_EVENT as authority; typed KnowledgeReference) |
| ResolutionResult | ADDITIVE |
| KnowledgeCandidate | ADDITIVE / COMPATIBILITY_ADAPTER |

Preference: **ADDITIVE**, not breaking for ordinary assert ingest.

## Interaction with existing supersedes / termination

- `State.supersedes_id` / `Attribute.supersedes_id` / `Relation.supersedes_id`: lineage/bookkeeping only  
- `RelationAssertionMode.TERMINATE` / termination fields: lifecycle only  
- Measurement: no supersession columns by design — correction ledger covers it  
- Fact amount correction via LAST_EVENT: **legacy debt** — must be replaced by explicit target resolution before Correction Engine close

## Transactionality

Target retraction + replacement materialization + correction row: all-or-nothing for REPLACE.

## Future implementation sequence (not started)

1. Schema v10 correction ledger + KnowledgeReference validation  
2. Target resolver (RESOLVED/AMBIGUOUS/UNRESOLVED) — no insertion-order  
3. Correction transaction in ingest branch  
4. AssertionEffectivenessResolver  
5. Wire/proposal additive fields; deprecate LAST_EVENT strategy  
6. Benchmark C1–C18 + safety metrics  

## Safety metrics (future = 0)

```text
CORRECTION_TARGET_SELECTED_BY_INSERTION_ORDER
CORRECTION_TARGET_AMBIGUITY_IGNORED
CORRECTION_DESTROYED_ORIGINAL_EVIDENCE
CORRECTION_RETRACTION_ASSERTED_OPPOSITE
CORRECTION_CONFLATED_WITH_TEMPORAL_EVOLUTION
CORRECTION_CONFLATED_WITH_RELATION_TERMINATION
CORRECTION_CONFLATED_WITH_STATE_SUPERSESSION
CORRECTION_CONFLATED_WITH_NEW_MEASUREMENT
CORRECTION_RETRACTED_UNTARGETED_DUPLICATE_EVIDENCE
CORRECTION_CROSSED_USER_BOUNDARY
CORRECTION_REPLACEMENT_PARTIALLY_COMMITTED
CORRECTION_LINEAGE_CYCLE
CREATED_AT_USED_AS_CORRECTION_TARGET_AUTHORITY
RECORDED_AT_USED_AS_FACT_TIME
```

## Recommendation

```text
I11.17_CLOSE_PROCEED_TO_CORRECTION_IMPLEMENTATION_FREEZE
```

Next: implementation freeze / schema v10 design for ledger (separate increment), not EVIDENCE-01 first.

## Debt update

```text
TIME-01                  CLOSED
CORRECTION_ENGINE_DEBT   DESIGN_FROZEN (implementation OPEN)
EVIDENCE-01              DEFERRED (not blocking bounded Correction)
```
