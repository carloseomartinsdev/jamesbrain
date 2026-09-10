from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal
from tests.engine_v1_baseline.corpus import EngineCase
from tests.event_interpreter_hardening.corpus import mp_label
from tests.model_capability_reevaluation.corpus import I1211_CORPUS
from tests.model_capability_reevaluation.freeze import default_freeze, frozen_thresholds
from tests.model_capability_reevaluation.scoring import invented_required_information, useful_capture


def test_corpus_size() -> None:
    assert 100 <= len(I1211_CORPUS) <= 140


def test_mp_anchors_present() -> None:
    labels = {mp_label(c) for c in I1211_CORPUS}
    for a in ("MP1", "MP2", "MP3", "MP4", "MP5"):
        assert a in labels


def test_thresholds_frozen_a_priori() -> None:
    t = frozen_thresholds()
    assert t.useful_capture_delta_min == 0.10
    assert t.execution_ready_delta_min == 0.10
    assert t.mp1_useful_capture_material == 0.70
    assert t.post_s4 == 0
    assert t.missing_information_invented == 0


def test_prompt_identical_across_candidates() -> None:
    fr = default_freeze()
    assert fr.prompt_version == PROMPT_VERSION_V4
    assert fr.semantic_proposal == "unchanged"


def test_abstention_is_not_useful_capture() -> None:
    case = EngineCase(
        id="NEG",
        utterance="asdf qwerty",
        category="unknown_concept",
        expected_intent="none",
        expected_primitive="unknown",
        expected_safe_abstention=True,
    )
    assert useful_capture(case, ir=None, outcome=None, error="proposal_semantics:unactionable") is False


def test_invented_subject_not_in_utterance() -> None:
    case = EngineCase(
        id="X",
        utterance="Medi a temperatura e deu 95°C.",
        category="multi_primitive",
        expected_intent="assert",
        expected_primitive="multi",
    )
    proposal = SemanticProposal(
        raw_input=case.utterance,
        subject=SemanticEntityMention(text="reator nuclear"),
    )
    assert "invented_subject" in invented_required_information(case, proposal)


def test_first_person_pronoun_is_not_invention() -> None:
    case = EngineCase(
        id="X",
        utterance="Medi a temperatura e deu 95°C.",
        category="multi_primitive",
        expected_intent="assert",
        expected_primitive="multi",
    )
    proposal = SemanticProposal(
        raw_input=case.utterance,
        subject=SemanticEntityMention(text="eu"),
    )
    assert invented_required_information(case, proposal) == []
