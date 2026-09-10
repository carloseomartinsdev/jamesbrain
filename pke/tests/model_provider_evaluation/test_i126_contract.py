"""Contract tests for I12.6 evaluation harness (no live calls)."""

from __future__ import annotations

from tests.model_provider_evaluation.candidates import all_candidates
from tests.model_provider_evaluation.corpus import STAGE_A_CORPUS, build_stage_a_corpus
from tests.model_provider_evaluation.freeze import default_freeze, frozen_thresholds


def test_thresholds_frozen_a_priori() -> None:
    t = frozen_thresholds()
    assert t.post_engine_s4 == 0
    assert t.post_engine_unsafe_variance_max == 0.01


def test_stage_a_corpus_size() -> None:
    cases = build_stage_a_corpus()
    assert 80 <= len(cases) <= 120
    assert len(STAGE_A_CORPUS) == len(cases)


def test_candidates_include_baseline() -> None:
    ids = [c.candidate_id for c in all_candidates()]
    assert "baseline_deepseek_chat" in ids
    assert ids[0] == "baseline_deepseek_chat"


def test_freeze_invariants() -> None:
    f = default_freeze()
    assert f.prompt_version.endswith("v4") or "v4" in f.prompt_version
    assert f.core_concept_count == 67
    assert f.effective_max_provider_calls == 2
