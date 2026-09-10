# ADR 0048 — Correction Engine Final Closure (I11.17-R)

## Status

**Accepted — CORRECTION_ENGINE_DEBT CLOSED.**

Final cross-layer revalidation. No new features. Schema remains **v10**. CORE = **65**.
TIME-01 remains **CLOSED**. Evidence-01 remains **DEFERRED**. Holdout untouched.

## Depends on

- ADR 0044 — Correction semantics / lineage design
- ADR 0045 — Ledger v10 storage contract
- ADR 0046 — Ledger implementation + effectiveness
- ADR 0047 — Semantic ingest + target resolution

## Final authority map

| Concern | Canonical authority |
|---------|---------------------|
| semantic correction intent | SemanticProposal / semantic pipeline |
| target resolution | CorrectionTargetResolver |
| assertion identity | KnowledgeReference |
| reference integrity | KnowledgeReferenceResolver |
| correction transaction | CorrectionService (+ ingest UoW) |
| correction persistence | CorrectionRepository / `knowledge_corrections` |
| assertion effectiveness | AssertionEffectivenessResolver |
| Event / Measurement / Relation / State / Attribute truth | primitive epistemic resolvers |
| Storage | persistence only |

No duplicated truth authority. Correction is **meta-knowledge**, not `PrimitiveKind.CORRECTION`.

## Effectiveness invariant

```text
An assertion is EFFECTIVE iff
no committed Correction targets its KnowledgeReference.
```

## RETRACT / REPLACE

- **RETRACT(P):** P stored + ineffective. Not DELETE. Not ASSERT NOT P.
- **REPLACE(P,Q):** P ineffective, Q effective, Correction stored; atomic UoW.
- Non-materializable / unresolved replacement → no mutation; no REPLACE→RETRACT.
- Failed correction → no ordinary assertion fallback.

## Target resolution

```text
RESOLVED | AMBIGUOUS | UNRESOLVED
```

Ambiguous/unresolved → no ledger / replacement / effectiveness change.
No insertion-order / `created_at` / `LAST_EVENT` authority.
LLM invented assertion IDs are not trusted without controlled membership.

## Multi-primitive regression

I11.17.3 exclusive replacement isolation must **not** break ordinary Event+Measurement
(MP1–MP4) or Measurement-only (MP5). Verified in final benchmark.

## Unsupported (bounded)

- Proposition-wide / multi-target correction
- Audit query surface (data preserved for future)
- Evidence-01 generic assertion registry
- Live-provider prompt optimization

## Final benchmark

`tests/correction_final/` — ≥120 deterministic cases including adversarial A1–A40.

## Closure decision

```text
CORRECTION_ENGINE_CLOSE
CORRECTION_ENGINE_DEBT: OPEN → CLOSED
```

Do **not** close Evidence-01, Measurement-analytics, TYPE persistence, adaptive aliases,
or other unrelated debts.

## Remaining non-Correction debts

- Evidence-01 (deferred)
- Legacy LAST_EVENT fact-correction path deprecation (compatibility remnant; not authority)
- Live provider evaluation (deselected by default)
- Holdout (untouched)
