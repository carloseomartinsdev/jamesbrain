# E1 Patch P1 — Live Provider Query Completeness

**Status:** COMPLETE  
**Base:** PKE E1 FROZEN + corrective patch P1  
**Date:** 2026-09-04

## Cause

```text
Live LLM incomplete semantic_query
→ missing semantic_signals
→ InterpretationError
→ Product unsupported (kind=none)
```

Knowledge write of `name` was fine; Ask path never reached.

## Fix

| Layer | Change |
|-------|--------|
| Repair | High-precision self-name query whitelist; before sufficiency gate |
| Prompt | v4/v5 self-name ATTRIBUTE query examples |
| Presenter | Neutral interpretation_error copy (no “registrar”) |
| Tests | Captured fixtures + EngineGateway + Product API cross-conversation |

## Regression

```text
tests/e1_patch_p1/     17 passed
pytest -m "not live"   5154 passed, 8 live deselected
```

## Gate checklist

- [x] Positives → `knowledge_query` + name recall (Product path fixture)
- [x] Negatives → no false self-name repair
- [x] Focused + full `pytest tests/ -m "not live"` PASS
- [x] No new semantics
