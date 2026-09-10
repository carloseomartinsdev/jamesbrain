"""Corpus contract for I12.8."""

from __future__ import annotations

from tests.event_interpreter_hardening.corpus import I128_CORPUS, mp_label


def test_corpus_size_in_range() -> None:
    assert 70 <= len(I128_CORPUS) <= 100


def test_mp_anchors_included() -> None:
    labels = {mp_label(c) for c in I128_CORPUS}
    for anchor in ("MP1", "MP2", "MP3", "MP4", "MP5"):
        assert anchor in labels


def test_mp1_included() -> None:
    mp1 = [c for c in I128_CORPUS if mp_label(c) == "MP1"]
    assert len(mp1) >= 1
    assert "95" in mp1[0].utterance.casefold()


def test_measurement_only_boundary_present() -> None:
    mp5 = [c for c in I128_CORPUS if mp_label(c) == "MP5"]
    assert mp5
    assert mp5[0].expected_primitive == "measurement"
