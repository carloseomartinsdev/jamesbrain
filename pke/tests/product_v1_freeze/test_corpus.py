"""Product v1 freeze corpus size + case registry checks."""

from __future__ import annotations

from tests.product_v1_freeze.anchors import PRODUCT_FREEZE_ANCHORS
from tests.product_v1_freeze.corpus import PRODUCT_V1_FREEZE_CORPUS


def test_freeze_corpus_size() -> None:
    assert len(PRODUCT_V1_FREEZE_CORPUS) >= 300
    assert len({c.case_id for c in PRODUCT_V1_FREEZE_CORPUS}) == len(PRODUCT_V1_FREEZE_CORPUS)


def test_anchors_p01_p50() -> None:
    anchors = [c for c in PRODUCT_V1_FREEZE_CORPUS if c.is_anchor]
    assert len(anchors) == 50
    assert [a.anchor_id for a in PRODUCT_FREEZE_ANCHORS] == [f"P{i:02d}" for i in range(1, 51)]
    assert [c.case_id for c in anchors] == [f"P{i:02d}" for i in range(1, 51)]


def test_corpus_families_present() -> None:
    families = {c.family for c in PRODUCT_V1_FREEZE_CORPUS}
    for required in (
        "anchor",
        "auth_matrix",
        "ownership_matrix",
        "idempotency_matrix",
        "dto_isolation",
        "web_boundary",
        "schema_guard",
        "recovery_matrix",
    ):
        assert required in families
