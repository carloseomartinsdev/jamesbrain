# ADR 0034 — Semantic Knowledge Model Closure & Cross-Primitive Audit (I11.14)

## Status

Accepted — audit closure. No schema/ontology expansion.

## Question

```text
DOES_THE_CURRENT_PKE_HAVE_A_COHERENT_CROSS_PRIMITIVE_KNOWLEDGE_MODEL?
PARTIALLY → YES for frozen boundaries; gaps remain in Measurement/Time/Type persistence/Correction
```

## Method

Deterministic SemanticProposal corpus:

- CP1–CP30 mandatory boundary cases
- OP1–OP25 open cross-domain cases
- QS1–QS5 query routing safety

Traced through Router → Resolver → Persistability → (optional) QueryIR.

## Local safety fix

Relation lifecycle cues (`lifecycle_cue` start/end) with link semantics but **without**
occurrence evidence (`change_semantics` / action / event expression) now route to
**RELATION**, not EVENT. Preserves Relation lifecycle vs Event occurrence.

## Frozen boundaries

| Boundary | Status |
|---|---|
| EVENT ↔ STATE | FROZEN |
| ATTRIBUTE ↔ STATE | FROZEN |
| ATTRIBUTE ↔ TYPE | FROZEN |
| ATTRIBUTE ↔ RELATION | FROZEN |
| RELATION lifecycle ↔ STATE | FROZEN |
| Descriptive vs observed quantity | FROZEN (observed → State/MEASUREMENT-01) |

## Remaining gaps (not closed)

- TYPE routing-only (acceptable; persistence deferred)
- Occupation/role (`João é médico`) — Attribute-shaped, non-materializable
- Brand vs manufacturer identity unresolved
- MEASUREMENT-01 (battery %, odometer, balances, mAh)
- TIME-01 (validity endpoints, partial calendars)
- CORRECTION_ENGINE_DEBT (`nunca trabalhou` ≠ termination)
- Monetary contractual amounts often Attribute-intent but non-canonical without money model

## Invariants confirmed

```text
State ≠ Event
Relation ≠ State
Attribute ≠ State / Relation / Type
Observed State ↛ Event
Relation assertion ↛ lifecycle Event (unless occurrence evidenced)
Entity-valued link prefers Relation
Query read-only (no mutation)
FALSE_CANONICALIZATION = 0 on audited corpus
```

## Schema / CORE

```text
schema = v8 (unchanged)
CORE = 65 (unchanged)
```
