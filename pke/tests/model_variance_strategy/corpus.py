"""I12.9 discriminative corpus (~50–80 cases). Development only."""

from __future__ import annotations

from tests.engine_v1_baseline.corpus import CORPUS, EngineCase
from tests.event_interpreter_hardening.corpus import mp_label

MP_UTTERANCE = "medi a temperatura e deu 95°C"


def build_i129_corpus(*, target: int = 65) -> list[EngineCase]:
    by_id = {c.id: c for c in CORPUS}
    selected: dict[str, EngineCase] = {}

    # MP anchors (mandatory)
    for c in CORPUS:
        if mp_label(c):
            selected[c.id] = c

    # Event + Measurement family
    for c in CORPUS:
        if c.expected_primitive == "multi":
            selected[c.id] = c

    # Single primitives — stratified
    quotas = {
        "event": 10,
        "state": 10,
        "relation": 10,
        "measurement": 8,
        "correction": 6,
        "query": 5,
        "ambiguity": 3,
        "unknown_concept": 3,
    }
    by_cat: dict[str, list[EngineCase]] = {}
    for c in CORPUS:
        by_cat.setdefault(c.category, []).append(c)

    for cat, quota in quotas.items():
        prim = cat if cat not in {"ambiguity", "unknown_concept"} else None
        have = sum(
            1
            for c in selected.values()
            if c.category == cat or (prim and c.expected_primitive == prim)
        )
        need = max(0, quota - have)
        pool = by_cat.get(cat, [])
        for c in pool:
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


I129_CORPUS = build_i129_corpus()

DUAL_SAMPLE_CASES = [c for c in I129_CORPUS if mp_label(c) or c.expected_primitive in {"multi", "event", "state", "relation"}][:12]
