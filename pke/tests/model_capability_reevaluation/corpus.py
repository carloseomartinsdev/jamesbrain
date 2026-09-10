"""I12.11 development corpus (~100–140). Frozen before live calls."""

from __future__ import annotations

from tests.engine_v1_baseline.corpus import CORPUS, EngineCase
from tests.event_interpreter_hardening.corpus import mp_label


def build_i1211_corpus(*, target: int = 120) -> list[EngineCase]:
    selected: dict[str, EngineCase] = {}
    for c in CORPUS:
        if mp_label(c):
            selected[c.id] = c
    for c in CORPUS:
        if c.expected_primitive == "multi":
            selected[c.id] = c

    quotas = {
        "event": 14,
        "state": 14,
        "relation": 14,
        "measurement": 12,
        "correction": 10,
        "query": 8,
        "attribute": 8,
        "multi_primitive": 10,
        "ambiguity": 4,
        "unknown_concept": 4,
        "temporal": 6,
        "negative": 4,
    }
    by_cat: dict[str, list[EngineCase]] = {}
    for c in CORPUS:
        by_cat.setdefault(c.category, []).append(c)
    for cat, quota in quotas.items():
        have = sum(1 for c in selected.values() if c.category == cat)
        need = max(0, quota - have)
        for c in by_cat.get(cat, []):
            if need <= 0:
                break
            if c.id not in selected:
                selected[c.id] = c
                need -= 1

    mandatory = {c.id for c in CORPUS if mp_label(c)}
    cases = list(selected.values())
    if len(cases) > target:
        keep = [c for c in cases if c.id in mandatory]
        rest = sorted((c for c in cases if c.id not in mandatory), key=lambda x: x.id)
        cases = keep + rest[: max(0, target - len(keep))]
    cases.sort(key=lambda c: (0 if c.id in mandatory else 1, c.id))
    return cases


I1211_CORPUS = build_i1211_corpus()
