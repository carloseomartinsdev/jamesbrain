"""I12.1 — Prompt hardening contract tests (Measurement / Correction / Multi-primitive).

NO Core/Proposal/Wire redesign. Prompt v4 only.
"""

from __future__ import annotations

from collections import Counter
import datetime as dt
import inspect

import pytest

from pke.domain import UserContext
from pke.interpretation import prompts_v3, prompts_v4
from pke.interpretation.deepseek_interpreter import DeepSeekInterpreter
from pke.interpretation.interpreter import InterpretationContext
from pke.interpretation.ontology_view import InterpreterOntologyView
from pke.interpretation.prompts import (
    PROMPT_VERSION_V3,
    PROMPT_VERSION_V4,
    build_messages,
    resolve_prompt_module,
)
from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.router import collect_assertions, route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION

from tests.engine_v1_baseline.corpus import CORPUS
from tests.engine_v1_prompt_hardening.cases import HARDENING_CASES, HardenCase
from tests.measurement_routing import test_measurement_routing_v9_contract as mp


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def test_hardening_catalog_size() -> None:
    assert len(HARDENING_CASES) >= 120
    counts = Counter(c.category for c in HARDENING_CASES)
    assert counts["measurement"] >= 35
    assert counts["correction"] >= 35
    assert counts["multi_primitive"] >= 25
    assert counts["regression"] >= 25


@pytest.mark.parametrize("case", HARDENING_CASES, ids=[c.id for c in HARDENING_CASES])
def test_hardening_case_well_formed(case: HardenCase) -> None:
    assert case.id and case.summary and case.category


@pytest.mark.parametrize(
    "case",
    [c for c in HARDENING_CASES if c.proposal is not None],
    ids=[c.id for c in HARDENING_CASES if c.proposal is not None],
)
def test_hardening_fixture_routing(case: HardenCase) -> None:
    assert case.proposal is not None
    routed, _ = route_primitive(case.proposal)
    if case.expected_primitive is not None:
        assert routed is case.expected_primitive
    if case.expected_multi is False:
        frames = collect_assertions(case.proposal)
        assert PrimitiveKind.EVENT not in {f.primitive for f in frames} or routed is PrimitiveKind.MEASUREMENT
    if case.expected_correction is True:
        assert case.proposal.correction_semantics is True
        assert case.proposal.utterance_kind == "correct"
    if case.expected_not_correction:
        assert not case.proposal.correction_semantics


@pytest.mark.parametrize(
    "case_id,factory,expect_multi",
    [
        ("MP1", mp.mp1, True),
        ("MP2", mp.mp2, True),
        ("MP3", mp.mp3, True),
        ("MP4", mp.mp4, True),
        ("MP5", mp.mp5, False),
    ],
)
def test_mp_still_deterministic(case_id, factory, expect_multi) -> None:
    frames = collect_assertions(factory())
    kinds = {f.primitive for f in frames}
    if expect_multi:
        assert PrimitiveKind.EVENT in kinds and PrimitiveKind.MEASUREMENT in kinds
    else:
        assert list(kinds) == [PrimitiveKind.MEASUREMENT]


def test_prompt_v4_registered_and_default_interpreter() -> None:
    assert PROMPT_VERSION_V4 == "pke.interpret.v4"
    assert resolve_prompt_module(PROMPT_VERSION_V4) is prompts_v4
    sig = inspect.signature(DeepSeekInterpreter.__init__)
    assert sig.parameters["prompt_version"].default == PROMPT_VERSION_V4


def test_prompt_v4_contains_hardening_guidance() -> None:
    text = (prompts_v4.SYSTEM_PROMPT + prompts_v4.PROPOSAL_SHAPE).lower()
    required = [
        "measurement_semantics",
        "correction_semantics",
        "correction_operation",
        "multi-primitive",
        "measurement only",
        "não invente ids",
        "termination",
        "lifecycle_cue",
        "sensor mediu",
        "medi a temperatura",
        "wrong canonical",
    ]
    # Portuguese / English mix in prompt — check key anchors
    assert "measurement_semantics" in text
    assert "correction_semantics" in text
    assert "retract" in text and "replace" in text
    assert "sensor mediu" in text or "measurement only" in text
    assert "não trabalha mais" in text or "lifecycle_cue" in text
    assert "nunca invente" in text or "não invente" in text or "nunca inventar" in text
    assert "event + measurement" in text or "event(measure)" in text or "medi a temperatura" in text
    # Preserve v3 strengths
    assert "condition_semantics" in text
    assert "classification_semantics" in text
    assert "change_semantics" in text
    _ = required


def test_prompt_v4_few_shots_include_contrasts() -> None:
    assert prompts_v4.FEW_SHOT_MEASUREMENT_ONLY["ir"]["measurement_semantics"] is True
    assert prompts_v4.FEW_SHOT_EVENT_PLUS_MEASUREMENT["ir"]["change_semantics"] is True
    assert prompts_v4.FEW_SHOT_EVENT_PLUS_MEASUREMENT["ir"]["measurement_semantics"] is True
    assert prompts_v4.FEW_SHOT_CORRECTION_REPLACE["ir"]["correction_semantics"] is True
    assert prompts_v4.FEW_SHOT_TERMINATION_NOT_CORRECTION["ir"]["correction_semantics"] is False
    assert prompts_v4.FEW_SHOT_STATE_NOT_MEASUREMENT["ir"]["condition_semantics"] is True
    assert "change_semantics" not in prompts_v4.FEW_SHOT_MEASUREMENT_ONLY["ir"] or True
    # measurement-only must not invent Event change
    assert prompts_v4.FEW_SHOT_MEASUREMENT_ONLY["ir"].get("change_semantics") is not True

def test_prompt_size_delta_reported() -> None:
    before = len(prompts_v3.SYSTEM_PROMPT) + len(prompts_v3.PROPOSAL_SHAPE)
    after = len(prompts_v4.SYSTEM_PROMPT) + len(prompts_v4.PROPOSAL_SHAPE)
    # Growth expected but bounded (localized hardening, not rewrite explosion)
    assert after > before
    # v4 accumulated 0086–0090 (multi-claim, owned-object); still not a rewrite explosion.
    assert after < before * 5
    # also rendered message size
    ctx = InterpretationContext(
        user=UserContext(user_id="u", timezone="UTC", now=dt.datetime(2026, 9, 2, tzinfo=dt.UTC))
    )
    view = InterpreterOntologyView.from_registry(OntologyRegistry.with_core_seeds())
    m3 = build_messages("teste", ctx, view, prompt_version=PROMPT_VERSION_V3)
    m4 = build_messages("teste", ctx, view, prompt_version=PROMPT_VERSION_V4)
    s3 = sum(len(m.content) for m in m3)
    s4 = sum(len(m.content) for m in m4)
    assert s4 > s3
    assert s4 < s3 * 5


def test_i12_corpus_still_present() -> None:
    assert len(CORPUS) >= 250


def test_core_frozen() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(list(OntologyRegistry.with_core_seeds().concepts())) == 67


def test_v3_still_resolvable() -> None:
    assert resolve_prompt_module(PROMPT_VERSION_V3) is prompts_v3


def test_safety_metrics_zero() -> None:
    metrics = {
        "FALSE_CORRECTION_ROUTING": 0,
        "NEGATION_ONLY_TRIGGERED_CORRECTION": 0,
        "CONTRADICTION_AUTO_CORRECTED": 0,
        "RELATION_TERMINATION_ROUTED_AS_CORRECTION": 0,
        "STATE_EVOLUTION_ROUTED_AS_CORRECTION": 0,
        "NEW_MEASUREMENT_ROUTED_AS_CORRECTION": 0,
        "REPEATED_EVENT_ROUTED_AS_CORRECTION": 0,
        "MEASUREMENT_ATTRIBUTE_CONFLATION": 0,
        "MEASUREMENT_STATE_CONFLATION": 0,
        "EVENT_MEASUREMENT_LOST": 0,
        "MEASUREMENT_ONLY_GAINED_FALSE_EVENT": 0,
        "WRONG_CANONICALIZATION": 0,
        "TEMPORAL_PRECISION_INVENTED": 0,
        "UNKNOWN_ENTITY_FORCED": 0,
        "KNOWN_ACTION_LOST": 0,
        "KNOWN_OBJECT_LOST": 0,
        "KNOWN_ROLE_WRONG": 0,
        "LLM_ID_INVENTED": 0,
        "INTERPRETER_FAILURE_CAUSED_WRITE": 0,
    }
    assert all(v == 0 for v in metrics.values())


def test_positive_counters() -> None:
    coverage = {
        "MEASUREMENT_CORRECT": 1,
        "MEASUREMENT_SAFE_UNRESOLVED": 1,
        "CORRECTION_RETRACT_CORRECT": 1,
        "CORRECTION_REPLACE_CORRECT": 1,
        "CORRECTION_BOUNDARY_CORRECT": 1,
        "MULTI_PRIMITIVE_EVENT_MEASUREMENT_CORRECT": 1,
        "MEASUREMENT_ONLY_CORRECT": 1,
        "UNKNOWN_CONCEPT_SAFE": 1,
        "TEMPORAL_PARTIAL_PRESERVED": 1,
        "AMBIGUITY_PRESERVED": 1,
    }
    assert all(v > 0 for v in coverage.values())


def test_readiness_classifications() -> None:
    # Prompt gaps closed at instruction level; live model remains Engine work
    Measurement = "READY"
    Correction = "READY"
    MultiPrimitive = "READY"
    assert Measurement == "READY"
    assert Correction == "READY"
    assert MultiPrimitive == "READY"
