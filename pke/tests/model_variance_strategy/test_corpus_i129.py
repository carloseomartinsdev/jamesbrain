from tests.model_variance_strategy.corpus import I129_CORPUS, DUAL_SAMPLE_CASES
from tests.event_interpreter_hardening.corpus import mp_label


def test_corpus_size() -> None:
    assert 50 <= len(I129_CORPUS) <= 80


def test_mp_anchors() -> None:
    labels = {mp_label(c) for c in I129_CORPUS}
    for a in ("MP1", "MP2", "MP3", "MP4", "MP5"):
        assert a in labels


def test_dual_sample_subset() -> None:
    assert 8 <= len(DUAL_SAMPLE_CASES) <= 15
