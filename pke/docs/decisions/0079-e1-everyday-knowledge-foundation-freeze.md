# ADR 0079 — E1 Everyday Knowledge Foundation Freeze (E1.4)

## Status

**ACCEPTED — `PKE_E1 = FROZEN` (Everyday Knowledge Foundation)**

Closes E1.1 (ADR 0076), E1.2 (ADR 0077), E1.3 (ADR 0078) after full revalidation.
Does not authorize E2 or any new domain semantics.

## Context

E1 delivered PrincipalBinding, controlled everyday Attribute dimensions
(`name`, `brand`, `model` + ownership routing), and CapabilityStrategy quality
(`CLARIFY` / `UNSUPPORTED` / `SAFE_ABSTAIN` / `AUTO_EXECUTE`).

E1.4 is revalidation-only: identify regressions, fix only E1-introduced contract
breaks or outdated tests, then freeze.

## Decision

Freeze Everyday Knowledge Foundation within the declared E1 capability boundary.

```text
E1.1 COMPLETE
E1.2 COMPLETE
E1.3 COMPLETE
E1.4 COMPLETE

PKE E1
EVERYDAY KNOWLEDGE FOUNDATION
FROZEN
```

### Freeze meaning

```text
E1_FREEZE DOES NOT MEAN FULL EVERYDAY ONTOLOGY.
E1_FREEZE DOES NOT MEAN FAMILY / WORK / PREFERENCE / WORLD SEMANTICS.
E1_FREEZE MEANS THE DECLARED E1 CONTRACTS ARE STABLE, SAFE,
AND REGRESSION-GREEN AGAINST FROZEN Product/Engine boundaries.
```

### Still frozen (unchanged by E1 freeze)

| Layer | Status |
|-------|--------|
| Product API v1 public DTO | FROZEN (schema 1.4) |
| Engine v1 interpreter surface | FROZEN (prompt v4) |
| Knowledge schema | **v11** (PrincipalBinding; additive from v10) |
| CORE concept count | unchanged by E1 Attribute *registry* (code-config dimensions) |
| Portal / Product semantic ownership | none — presentation / DTO only |

### Known deferred gaps (record only — not E1 scope)

- Event formulation `Pintei meu carro de preto.` may remain outside current
  capability; classify honestly as gap — do not expand E1 to force-pass.
- Dimensions outside controlled registry → UNSUPPORTED / SAFE_ABSTAIN (never
  LLM-registered dimensions).
- Family, journeys, work/problem, preferences, world ontology → post-E1 / Beta evidence.

## Consequences

- JAMES Beta may resume everyday tests against this freeze.
- New Beta failures → classify (BUG / REGRESSION / PKE GAP) → triage next build.
- Do **not** start E2 automatically.
- Reopen E1 only on invariant violation evidence.

## Evidence

See `docs/reports/E1.4-FULL-REVALIDATION-AND-FREEZE.md` and `docs/PKE-E1-FREEZE.md`.
