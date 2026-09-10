# ADR 0047 — Correction Semantic Ingest & Target Resolution (I11.17.3)

## Status

Accepted — **CLOSED**. Schema remains **v10**. No migration. CORE = 65. TIME-01 CLOSED.

## Depends on

- ADR 0044 / 0045 / 0046 — Correction architecture, storage, effectiveness

## Semantic representation (ADDITIVE)

`SemanticProposal` gains:

```text
correction_semantics
correction_operation: retract | replace
correction_target_* (kind, entity, dimension, value, year, relation, state, action)
correction_target_assertion_id          # proposal-only; validated if controlled
correction_conversation_assertion_id    # app-bound conversation ref ≠ DB order
```

`WireSemanticProposal` / `IrCorrection` / `WireIrCorrection` extended with
`operation` + `target` (ADDITIVE / COMPATIBILITY).

Legacy fact-correction (`strategy` + `facts`) remains for compatibility.
`LAST_EVENT` is **not** CorrectionTargetResolver authority.

Replacement sibling fields on correction wire are **exclusive** (one primitive):
opportunistic Event co-emission must not preempt Attribute/Measurement materialization.

## Pipeline

```text
NL → SemanticProposal(correct)
  → Wire intent=correct + target + exclusive replacement sibling
  → CorrectionIngestOrchestrator
  → CorrectionTargetResolver → RESOLVED|AMBIGUOUS|UNRESOLVED
  → scrub replacement IR to intended primitive
  → ordinary materialization path
  → CorrectionService RETRACT|REPLACE (single UoW commit)
```

Forbidden:

```text
LLM → raw assertion_id trusted blindly
failed correction → ordinary assertion write
failed REPLACE → RETRACT
insertion order / created_at / LAST_EVENT as target authority
contextual pronoun as sole entity identity for target matching
```

## CorrectionTargetResolver

Shared resolver with primitive-specific candidate characterization.
Ambiguity: never pick highest score alone.
Eligible targets: EFFECTIVE only.
Conversation-bound / explicit ids still require ownership + effectiveness validation.

## Boundaries

| Scenario | Routed as Correction? |
|----------|----------------------|
| Negation only | NO |
| Contradiction without correction cue | NO |
| Temporal evolution | NO |
| State evolution | NO |
| Relation termination | NO |
| New Measurement | NO |
| Repeated Event | NO |
| Query | NO |
| Explicit correction_semantics + operation | YES |

## Outcomes

```text
CORRECTION_APPLIED
CORRECTION_TARGET_UNRESOLVED / AMBIGUOUS
CORRECTION_REPLACEMENT_UNRESOLVED / NON_MATERIALIZABLE
CORRECTION_REJECTED / UNSUPPORTED
```

Ambiguous/unresolved → no ledger, no replacement, no effectiveness change.

## Benchmark

Deterministic catalog + E2E in `tests/correction_ingest/` (≥80 cases; catalog size = 98).
Canonical suite (I11.17.3 close): **1328 passed**, 0 failed, 7 live deselected.

## Remaining debt

- Live provider prompt (no optimization in this increment)
- Audit query / include_retracted
- Deprecate legacy LAST_EVENT fact-correction path entirely
- Proposition-wide / multi-target correction (UNSUPPORTED by design)

## Recommendation

```text
I11.17.3_CLOSE_PROCEED_TO_CORRECTION_FINAL_REVALIDATION
```
