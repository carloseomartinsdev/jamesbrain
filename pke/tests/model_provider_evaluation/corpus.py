"""I12.6 Stage A discriminative corpus (~80–120 cases). Development only."""

from __future__ import annotations

import json
from pathlib import Path

from tests.engine_v1_baseline.corpus import CORPUS, EngineCase

_ROOT = Path(__file__).resolve().parents[2]
_EXTRACT = _ROOT / "docs" / "reports" / "I12.3-R-CLOSURE-EXTRACT.json"

MP_UTTERANCE_MARKERS = (
    "medi a temperatura e deu 95",
    "olhei o tanque e ele estava com 20",
    "pesei a caixa: 10",
    "consultei o saldo e tinha r$2500",
    "o sensor mediu 38",
)


def _is_mp_anchor(case: EngineCase) -> bool:
    u = case.utterance.lower()
    return any(m in u for m in MP_UTTERANCE_MARKERS)


def _unsafe_ids() -> list[str]:
    if not _EXTRACT.is_file():
        return []
    data = json.loads(_EXTRACT.read_text(encoding="utf-8"))
    return sorted({u["case"] for u in data.get("unsafe_ledger", [])})


def build_stage_a_corpus(*, target: int = 100) -> list[EngineCase]:
    """Discriminative Stage A set: all I12.3 unsafe + MP anchors + stratified fill."""
    by_id = {c.id: c for c in CORPUS}
    selected: dict[str, EngineCase] = {}

    for uid in _unsafe_ids():
        if uid in by_id:
            selected[uid] = by_id[uid]

    for c in CORPUS:
        if _is_mp_anchor(c):
            selected[c.id] = c

    # Former Correction S4 pattern utterances (explicit)
    s4_needles = (
        "corrigi isso?",
        "na verdade ele é preto",
        "desculpa olhei errado",
        "isso estava errado",
        "não foi em 2024",
        "ao contrário: está fechada",
    )
    for c in CORPUS:
        ul = c.utterance.lower()
        if any(n in ul for n in s4_needles):
            selected[c.id] = c

    # Stratified fill by category
    quotas = {
        "event": 8,
        "state": 8,
        "relation": 8,
        "attribute": 6,
        "measurement": 8,
        "correction": 8,
        "query": 6,
        "temporal": 6,
        "multi_primitive": 12,
        "ambiguity": 4,
        "unknown_concept": 4,
        "conversational": 3,
        "negative": 4,
        "type": 2,
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

    cases = list(selected.values())
    # Trim if over target while keeping mandatory unsafe + mp
    mandatory = set(_unsafe_ids()) | {c.id for c in CORPUS if _is_mp_anchor(c)}
    if len(cases) > target:
        keep = [c for c in cases if c.id in mandatory]
        rest = [c for c in cases if c.id not in mandatory]
        # stable order by id
        rest.sort(key=lambda c: c.id)
        keep.sort(key=lambda c: c.id)
        cases = keep + rest[: max(0, target - len(keep))]

    cases.sort(key=lambda c: c.id)
    if len(cases) < 80:
        # pad with more from CORPUS
        for c in sorted(CORPUS, key=lambda x: x.id):
            if c.id not in {x.id for x in cases}:
                cases.append(c)
            if len(cases) >= 80:
                break
    return cases


STAGE_A_CORPUS: list[EngineCase] = build_stage_a_corpus()
