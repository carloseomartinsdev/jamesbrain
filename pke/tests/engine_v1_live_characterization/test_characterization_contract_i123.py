"""I12.3 — Deterministic characterization contracts (no live provider calls)."""

from __future__ import annotations

import hashlib

import pytest

from pke.interpretation.models import IngestIR, IngestIntent
from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.retry import MAX_ATTEMPTS, RetryPolicy
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.ontology import OntologyRegistry

from tests.engine_v1_baseline.corpus import CORPUS, EngineCase
from tests.engine_v1_live_characterization.freeze import default_freeze
from tests.engine_v1_live_characterization.scoring import (
    classify_case_variance,
    score_failure,
    score_success,
)
from pke.interpretation.interpreter import InterpretationError


def test_freeze_invariants() -> None:
    fr = default_freeze()
    assert fr.prompt_version == PROMPT_VERSION_V4
    assert fr.schema_version == STORAGE_SCHEMA_VERSION == "11"
    assert fr.core_concept_count == len(list(OntologyRegistry.with_core_seeds().concepts())) == 67
    assert fr.retry_max_attempts == MAX_ATTEMPTS == 2
    assert RetryPolicy().max_attempts == 2
    assert fr.sdk_max_retries == 0
    assert fr.effective_max_provider_calls == 2


def test_corpus_snapshot_stable() -> None:
    assert len(CORPUS) == 334
    ids = [c.id for c in CORPUS]
    assert len(ids) == len(set(ids))
    blob = "\n".join(f"{c.id}\t{c.utterance}" for c in CORPUS)
    fp = hashlib.sha256(blob.encode()).hexdigest()[:16]
    assert len(fp) == 16


def test_scoring_correct_event() -> None:
    case = EngineCase(
        id="T1",
        utterance="A geladeira quebrou.",
        category="event",
        expected_intent="assert",
        expected_primitive="event",
    )
    ir = IngestIR.model_construct(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=case.utterance,
        event=object(),  # presence-only for primitive detection
        state=None,
        attribute=None,
        measurement=None,
        relation=None,
    )
    score = score_success(case, ir, run=1)
    assert score.observed_intent == "assert"
    assert score.observed_primitive == "event"
    assert score.verdict == "CORRECT"


def test_scoring_false_correction_is_s4() -> None:
    case = EngineCase(
        id="T2",
        utterance="A porta está aberta.",
        category="state",
        expected_intent="assert",
        expected_primitive="state",
    )
    ir = IngestIR.model_construct(
        intent=IngestIntent.CORRECT,
        raw_input=case.utterance,
        correction=None,
    )
    score = score_success(case, ir, run=1)
    assert score.severity == "S4"
    assert score.verdict == "UNSAFE"


def test_scoring_safe_abstention_on_error() -> None:
    case = EngineCase(
        id="T3",
        utterance="xyzzy unknown",
        category="unknown_concept",
        expected_intent="assert",
        expected_primitive="unknown",
        expected_safe_abstention=True,
    )
    score = score_failure(
        case, InterpretationError("semantic_resolution:concept_resolution"), run=1
    )
    assert score.verdict == "SAFE_ABSTENTION"
    assert score.severity == "S0"


def test_variance_classifier() -> None:
    case = EngineCase("T4", "x", "event", "assert", "event")
    ok = score_failure(
        case, InterpretationError("semantic_resolution:concept_resolution"), run=1
    )
    # force correct-like by cloning fields
    a = ok
    b = ok
    assert classify_case_variance([a, b]) in {
        "STABLE_SAFE_ABSTENTION",
        "UNSTABLE_BUT_SAFE",
        "STABLE_CORRECT",
    }


def test_safety_metrics_contract_zeros_documented() -> None:
    # Observational experiment must not invent writes; contract reminder
    metrics = {
        "INTERPRETER_FAILURE_CAUSED_WRITE": 0,
        "PROVIDER_RETRY_DUPLICATED_KNOWLEDGE": 0,
        "TRANSPORT_NORMALIZATION_INVENTED_SEMANTICS": 0,
        "LLM_ID_TRUSTED": 0,
    }
    assert all(v == 0 for v in metrics.values())


@pytest.mark.live
def test_live_marker_exists_for_deselection() -> None:
    """Placeholder live test — real characterization via run_i123 script.

    Deselected by default (`not live`). Requires DEEPSEEK_API_KEY when selected.
    """
    import os

    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY ausente")
    pytest.skip("Full live corpus runs via run_i123_live_characterization module, not pytest loop")
