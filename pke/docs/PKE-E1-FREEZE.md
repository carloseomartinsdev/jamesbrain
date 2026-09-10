# PKE E1 Freeze — Everyday Knowledge Foundation

**Status:** `PKE_E1 = FROZEN`  
**Freeze decision:** E1.4 — Full Revalidation & Freeze  
**Date:** 2026-09-04  
**ADR:** `docs/decisions/0079-e1-everyday-knowledge-foundation-freeze.md`

---

## Versions

| Item | Value |
|------|-------|
| E1 build | **FROZEN** (E1.1 + E1.2 + E1.3) |
| Knowledge storage schema | **v11** (`principal_bindings`) |
| Everyday Attribute registry | `name`, `brand`, `model` (+ pre-E1 core dims) |
| Capability outcomes | `AUTO_EXECUTE` / `CLARIFY` / `UNSUPPORTED` / `SAFE_ABSTAIN` |
| Product public API | `/api/v1/` schema **1.4** (DTO unchanged by E1) |
| Engine | v1 FROZEN (prompt **v4**) |
| Corrective patches | **P1** Live Provider Query Completeness — ADR `0080` |

---

## Freeze meaning

```text
E1_FREEZE DOES NOT MEAN ALL EVERYDAY LANGUAGE WORKS.
E1_FREEZE DOES NOT MEAN NEW ATTRIBUTES OR RELATIONS MAY BE ADDED CASUALLY.
E1_FREEZE MEANS PRINCIPAL/SELF, CONTROLLED EVERYDAY ATTRIBUTES,
AND CLARIFICATION QUALITY ARE STABLE AND SAFE.
```

---

## Contracts frozen in E1

```text
AuthUser != Entity
PrincipalBinding is lazy
PrincipalBinding is idempotent
unknown semantic dimension → no unsafe IR → no commit
LLM cannot register dimensions
conversation != knowledge
Portal/Product do not own semantic rules
```

### Boundary reminders

Attribute is **not** a generic fallback for State / Relation / Type / Event.

Vehicle ownership shape:

```text
Principal → relation.owns → Vehicle
  ├── brand
  ├── model
  └── color (existing State/Attribute path)
```

Never flatten as `principal.car_*`.

---

## Regression baseline (E1.4)

| Gate | Result |
|------|--------|
| Focused E1 suites (`e1_principal`, `e1_everyday`, `e1_clarification`) | PASS |
| Frozen-contract / clarification coverage | PASS |
| Migration runner includes `v10_to_v11` | PASS |
| Product API smoke (`tests/api`, `tests/product_v1_freeze`) | PASS |
| Full `pytest tests/ -m "not live"` | **5137 passed**, 8 live deselected |
| JAMES Portal live smoke | Operator checklist on Beta resume (same Product DTO) |

---

## Beta reopen

```text
E1 FREEZE
    ↓
JAMES Beta resumes
    ↓
real-world testing
    ↓
collect gaps
    ↓
classify evidence
    ↓
decide next build
```

Do not auto-start E2.
