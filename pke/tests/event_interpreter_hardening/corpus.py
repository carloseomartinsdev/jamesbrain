"""I12.8 event interpretation hardening corpus (~70–100 cases). Development only."""

from __future__ import annotations

import json
from pathlib import Path

from tests.engine_v1_baseline.corpus import CORPUS, EngineCase

_ROOT = Path(__file__).resolve().parents[2]
_I126 = _ROOT / "docs" / "reports" / "i126_artifacts" / "baseline_deepseek_chat.jsonl"
_I127 = _ROOT / "docs" / "reports" / "i127_artifacts" / "checkpoint.jsonl"

MP_MARKERS: tuple[tuple[str, str], ...] = (
    ("MP1", "medi a temperatura e deu 95"),
    ("MP2", "olhei o tanque e ele estava com 20 litros"),
    ("MS18", "olhei o tanque e ele estava com 20 litros"),
    ("MP3", "pesei a caixa"),
    ("MP4", "consultei o saldo e tinha r$2500"),
    ("MP5", "o sensor mediu 38"),
)

MEASUREMENT_ONLY_NEEDLES = (
    "o sensor mediu 38",
    "termômetro marcou",
    "balança indicou",
    "a temperatura foi 38",
    "38 graus",
    "tinha r$2500",
    "20 litros no tanque",
    "pesava 10 kg",
    "bateria em 80%",
)


def mp_label(case: EngineCase) -> str | None:
    u = case.utterance.casefold()
    for label, prefix in MP_MARKERS:
        if u.startswith(prefix.casefold()) or prefix.casefold() in u:
            return label
    return None


def _is_mp(case: EngineCase) -> bool:
    return mp_label(case) is not None


def _omission_case_ids() -> set[str]:
    """Cases where I12.6/I12.7-R expected Event but raw proposal omitted it."""
    ids: set[str] = set()
    for path in (_I126, _I127):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("PROPOSAL_EVENT_PRESENT") and row.get("category") in {
                "multi_primitive",
                "event",
            }:
                cid = row.get("case_id")
                if cid:
                    ids.add(str(cid))
    # MP1 anchor always included
    for c in CORPUS:
        if mp_label(c) == "MP1":
            ids.add(c.id)
    return ids


def build_i128_corpus(*, target: int = 90) -> list[EngineCase]:
    by_id = {c.id: c for c in CORPUS}
    selected: dict[str, EngineCase] = {}

    for cid in _omission_case_ids():
        if cid in by_id:
            selected[cid] = by_id[cid]

    for c in CORPUS:
        if _is_mp(c):
            selected[c.id] = c

    # Event + Measurement family
    for c in CORPUS:
        if c.expected_primitive == "multi":
            selected[c.id] = c

    # Measurement-only boundaries
    for c in CORPUS:
        ul = c.utterance.casefold()
        if c.expected_primitive == "measurement" and any(n in ul for n in MEASUREMENT_ONLY_NEEDLES):
            selected[c.id] = c

    # Event-only resolved examples
    event_quota = 12
    event_have = sum(1 for c in selected.values() if c.expected_primitive == "event")
    for c in CORPUS:
        if event_have >= event_quota:
            break
        if c.expected_primitive == "event" and c.id not in selected:
            selected[c.id] = c
            event_have += 1

    # State / Relation / Query / Correction boundaries (no regression watch)
    quotas = {
        "state": 8,
        "relation": 8,
        "query": 6,
        "correction": 6,
        "attribute": 4,
        "temporal": 4,
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
    mandatory = set(_omission_case_ids()) | {c.id for c in CORPUS if _is_mp(c)}
    if len(cases) > target:
        keep = [c for c in cases if c.id in mandatory]
        rest = sorted((c for c in cases if c.id not in mandatory), key=lambda x: x.id)
        cases = keep + rest[: max(0, target - len(keep))]

    cases.sort(key=lambda c: (0 if c.id in mandatory else 1, c.id))
    return cases


I128_CORPUS = build_i128_corpus()
