# ADR 0055 — Interpreter Correction Acceptance Guard (I12.4)

## Status

Accepted — **I12.4 Correction Acceptance Guard closed** (deterministic suite green).

```text
ENGINE V1 SAFETY HARDENING
INTERPRETER ACCEPTANCE GUARDRAILS
FALSE CORRECTION PRE-COMMIT GATE
```

No Knowledge Core change. No schema/migration. No CORE expansion.
No SemanticProposal / Wire change. No prompt / model / provider change.
Holdout untouched.

## Context

I12.3 live characterization (N=3, 334 cases) observed:

```text
S4 = 9
all 9 = FALSE_CORRECTION_ROUTING
UNSAFE_VARIANCE ≈ 10.8%
```

Correction mutations are epistemically dangerous. Provider retry (I12.2) does not
fix wrong-but-schema-valid Correction proposals. Prompt v4 (I12.1) reduces but
does not eliminate false Correction routing.

## Decision

### Philosophy

```text
LLM proposes.
PKE validates.
PKE decides whether proposal is admissible.
Storage persists only accepted knowledge.
```

The guard is an **acceptance validator**, not a second semantic interpreter.

### Placement

```text
User text + bounded conversational context
  → Interpreter (+ provider retry, structural only)
  → valid SemanticProposal
  → Correction Acceptance Guard
  → ACCEPT | REJECT | CLARIFICATION_REQUIRED
  → accepted proposal only
  → semantic pipeline / Correction ingest
  → CorrectionTargetResolver
  → CorrectionService / materialization / commit
```

Implemented at:

1. `proposal_to_canonical_ir` — after structural proposal resolution flags Correction;
   reject/clarify yields `failure_stage=ACCEPTANCE_GUARD:…` (no canonical IR).
2. `CorrectionIngestOrchestrator.ingest` — second gate before `CorrectionTargetResolver`
   (defense in depth if IR arrives via another path).

Rejection **must not** trigger provider retry (`acceptance_guard:` →
`SEMANTIC_NON_RETRYABLE`).

### Authority boundary

Guard answers: `IS_CORRECTION_INTENT_ADMISSIBLE?`

`CorrectionTargetResolver` still answers: `WHICH_PERSISTED_ASSERTION_IS_THE_TARGET?`

Guard must never:

- rewrite primitive (Correction → State/Relation/Event/Measurement)
- invent replacement / entity / time / canonical concept
- select KnowledgeReference / row ID / latest-by-insertion-order
- search Knowledge Store to invent corrective intent
- auto-reinterpret after REJECT

`REJECT` means: the Interpreter's proposed Correction is not admissible —
not that the utterance has no semantics.

### Evidence model (deterministic)

Ordered rules, no LLM, no embeddings:

- Strong meta cues: corrigindo, retificando, me enganei, falei errado, desconsidere,
  quis dizer, não era X era Y, …
- Perceptual cues (li/olhei errado): require prior utterance **or** self-contained
  numeric/contrast replacement; otherwise `CLARIFICATION_REQUIRED`
- Contextual short forms with prior: `Não, foi…` / `Foi em…` (comma-required for `Não,`)
- Competing lifecycle cues without strong correction → REJECT
  (termination `não…mais`, evolution `agora`, repetition `de novo`, new observation)
- Bare `não`, isolated `na verdade` without prior, queries → REJECT / insufficient
- Ambiguous weak + pronoun with prior → CLARIFICATION_REQUIRED

Conservative when unsure: prefer REJECT or CLARIFY over unsafe mutation.

### Captured S4 replay

Nine I12.3 S4 runs replayed deterministically (utterance only; no provider):

| Case | Utterance | Guard |
|------|-----------|-------|
| QY30 | corrigi isso? | REJECT (query) |
| CR06 | na verdade ele é preto | REJECT (weak, no prior) |
| CR16 | desculpa olhei errado; está fechada | CLARIFY (perceptual, no prior) |
| CR21 | isso estava errado | REJECT (weak, no prior) |
| NG06 | não foi em 2024 | REJECT (negation ≠ replace) |
| NG10 | ao contrário: está fechada | REJECT (weak, no prior) |

`CAPTURED_S4_BLOCK_RATE = 100%` (none ACCEPT → none reach CorrectionTargetResolver).

CR16 remains a **true correction** when prior context is supplied (hard positive).

### Metrics targets

```text
FALSE_CORRECTION_ACCEPTED = 0   (deterministic safety corpus)
CORRECTION_ACCEPTANCE_PRECISION = 100%
clear TRUE correction recall >= 90%
CAPTURED_S4_BLOCK_RATE = 100%
```

Recall threshold rationale: clear positives are labeled `clear_positive`; genuinely
ambiguous cases use clarification and are excluded from the clear-positive denominator.

### Freeze confirmation

```text
prompt = v4 unchanged
provider/model unchanged
SemanticProposal unchanged
Wire unchanged
RetryPolicy taxonomy extended only for acceptance_guard: prefix (non-retryable)
Knowledge Core v1 = FROZEN
schema = v10
CORE = 65
migration = none
holdout untouched
```

### Remaining Engine debt

```text
INTERPRETER-RETRY-01 = CLOSED
INTERPRETER-STATE-01 = OPEN
INTERPRETER-RELATION-01 = OPEN
INTERPRETER-EVENT-01 = OPEN
ONTOLOGY-COVERAGE-01 = PRODUCT_QUALITY
SEMANTIC-QUERY-01 = PRODUCT_QUALITY
LIVE-INTERPRETER-RELIABILITY-01 = PARTIALLY_MITIGATED
  (S4 Correction safety mitigated; S3 / multi-primitive remain)
```

## Consequences

- Unsupported Correction proposals cannot mutate knowledge via the Correction path.
- LLM may still propose false Corrections; guard makes unsafe acceptance = 0 for this class.
- Reinterpretation of rejected Corrections into other primitives is **out of scope** (future).
- Highest remaining Engine v1 blocker after this guard: **MULTI_PRIMITIVE_ROUTING**
  (I12.3: multi_primitive family worst unsafe; MS18 evidence).

## Recommendation

```text
I12.4_CLOSE_PROCEED_TO_MULTI_PRIMITIVE_ROUTING_HARDENING
```
