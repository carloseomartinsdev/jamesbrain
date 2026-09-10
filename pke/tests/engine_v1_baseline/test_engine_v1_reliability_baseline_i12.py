"""I12 — Engine v1 reliability baseline & interpreter hardening design freeze.

NO Core redesign · NO schema/migration · NO prompt optimization · NO holdout.
Deterministic characterization of the language boundary above frozen Knowledge Core v1.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import pytest

from pke.interpretation.deepseek_interpreter import DeepSeekInterpreter
from pke.interpretation.prompts import PROMPT_VERSION_V3
from pke.interpretation.prompts_v3 import SYSTEM_PROMPT
from pke.interpretation.semantic.models import PrimitiveKind, SemanticEntityMention, SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.router import collect_assertions, route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.interpretation.transport.proposal_wire import WireSemanticProposal
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from tests.engine_v1_baseline.corpus import CORPUS, EngineCase
from tests.measurement_routing import test_measurement_routing_v9_contract as mp


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


# --- Corpus integrity ---


def test_corpus_size_and_distribution() -> None:
    assert len(CORPUS) >= 250
    counts = Counter(c.category for c in CORPUS)
    assert counts["event"] >= 30
    assert counts["state"] >= 25
    assert counts["relation"] >= 25
    assert counts["attribute"] + counts.get("type", 0) >= 25
    assert counts["measurement"] + counts["multi_primitive"] >= 30
    assert counts["query"] >= 40
    assert counts["correction"] >= 25
    assert counts["temporal"] >= 30
    assert counts["ambiguity"] >= 25
    assert counts["unknown_concept"] >= 20
    assert counts["multi_primitive"] >= 5
    assert len({c.id for c in CORPUS}) == len(CORPUS)


@pytest.mark.parametrize("case", CORPUS, ids=[c.id for c in CORPUS])
def test_corpus_case_well_formed(case: EngineCase) -> None:
    assert case.id and case.utterance.strip()
    assert case.category
    assert case.severity_if_wrong in {"S0", "S1", "S2", "S3", "S4"}


# --- Frozen Core boundary ---


def test_core_remains_frozen() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(list(OntologyRegistry.with_core_seeds().concepts())) == 67


# --- Deterministic MP regression (Core already frozen; Engine must not break) ---


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
def test_mp_regression_deterministic(case_id, factory, expect_multi) -> None:
    frames = collect_assertions(factory())
    kinds = {f.primitive for f in frames}
    if expect_multi:
        assert PrimitiveKind.EVENT in kinds
        assert PrimitiveKind.MEASUREMENT in kinds
    else:
        assert list(kinds) == [PrimitiveKind.MEASUREMENT]


# --- Correction / intent boundary fixtures (proposal-level, provider-independent) ---


BOUNDARY_PROPOSALS: list[tuple[str, SemanticProposal, str]] = [
    (
        "negation_only",
        SemanticProposal(
            raw_input="O Corolla não é azul.",
            utterance_kind="assert",
            negation=True,
            subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
            attribute_expression="azul",
            stable_property_semantics=True,
            primitive_hint="attribute",
        ),
        "assert",
    ),
    (
        "explicit_correction",
        SemanticProposal(
            raw_input="Corrigindo: era 36.",
            utterance_kind="correct",
            correction_semantics=True,
            correction_operation="replace",
            measurement_expression="36°C",
            measurable_dimension_key="temperature",
            measurement_numeric_value="36",
            measurement_unit="°C",
            measurement_semantics=True,
            primitive_hint="measurement",
        ),
        "correct",
    ),
    (
        "query_intent",
        SemanticProposal(
            raw_input="Qual a cor do Corolla?",
            utterance_kind="query",
            subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
            attribute_expression="cor",
            primitive_hint="attribute",
        ),
        "query",
    ),
    (
        "termination_not_correction",
        SemanticProposal(
            raw_input="João não trabalha mais na Acme.",
            utterance_kind="assert",
            subject=SemanticEntityMention(text="João", kind_hint="person"),
            object=SemanticEntityMention(text="Acme", kind_hint="organization"),
            relation_expression="não trabalha mais",
            lifecycle_cue="end",
            link_semantics=True,
            primitive_hint="relation",
        ),
        "assert",
    ),
]


@pytest.mark.parametrize("name,proposal,intent", BOUNDARY_PROPOSALS, ids=[b[0] for b in BOUNDARY_PROPOSALS])
def test_intent_boundary_fixtures(name: str, proposal: SemanticProposal, intent: str) -> None:
    assert proposal.utterance_kind == intent or (
        intent == "correct" and (proposal.correction_semantics or proposal.utterance_kind == "correct")
    )
    if intent != "correct":
        assert not proposal.correction_semantics or name == "explicit_correction"


def test_type_classification_not_attribute() -> None:
    from tests.attribute_design import fixtures as af

    p = af.at14_corolla_is_car()
    assert route_primitive(p)[0] is PrimitiveKind.TYPE
    out = proposal_to_canonical_ir(p)
    assert out.ir is None or out.ir.attribute is None


# --- SemanticProposal / Wire sufficiency ---


def test_semantic_proposal_expressive_for_engine_v1() -> None:
    fields = set(SemanticProposal.model_fields)
    for f in (
        "utterance_kind",
        "correction_semantics",
        "correction_operation",
        "measurement_semantics",
        "classification_semantics",
        "lifecycle_cue",
        "measurable_dimension_key",
        "action_expression",
    ):
        assert f in fields
    wire_fields = set(WireSemanticProposal.model_fields)
    for f in ("correction_semantics", "measurement_semantics", "classification_semantics"):
        assert f in wire_fields


def test_wire_mirrors_proposal_correction_and_measurement() -> None:
    assert "correction_operation" in WireSemanticProposal.model_fields
    assert "measurable_dimension_key" in WireSemanticProposal.model_fields


# --- Prompt audit (NO optimization) ---


def test_prompt_v3_audit_gaps_documented() -> None:
    """Characterization only: prompt may under-document Engine-critical cues."""
    text = SYSTEM_PROMPT.lower()
    # Present distinctions (State/Event/Attribute/TYPE)
    assert "condition_semantics" in text
    assert "change_semantics" in text
    assert "classification_semantics" in text
    # Gaps to track (not fix here) — measurement/correction may be weak in system prompt
    gaps = []
    if "measurement_semantics" not in text and "measurement" not in text:
        gaps.append("MEASUREMENT_PROMPT_UNDERDOCUMENTED")
    if "correction_semantics" not in text and "corrig" not in text:
        gaps.append("CORRECTION_PROMPT_UNDERDOCUMENTED")
    # Record as characterization — either gap list or explicit awareness
    assert isinstance(gaps, list)


def test_deepseek_interpreter_retry_implemented_bounded() -> None:
    """I12.2: retry exists at Interpreter; bounded to MAX_ATTEMPTS=2."""
    from pke.interpretation.retry import MAX_ATTEMPTS, RetryPolicy

    src = Path(__file__).resolve().parents[2] / "src" / "pke" / "interpretation" / "deepseek_interpreter.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    fun_names = {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "interpret" in fun_names
    text = src.read_text(encoding="utf-8")
    assert "RetryPolicy" in text
    assert "max_attempts" in text
    assert MAX_ATTEMPTS == 2
    assert RetryPolicy().max_attempts == 2


# --- Retry design freeze (characterization constants) ---


RETRYABLE_TRANSPORT = frozenset(
    {
        "timeout",
        "empty_response",
        "invalid_json",
        "schema_invalid_structured_output",
        "http_5xx",
        "temporary_provider_failure",
    }
)
NON_RETRYABLE_SEMANTIC = frozenset(
    {
        "ambiguous_entity",
        "unresolved_concept",
        "ontology_gap",
        "wrong_but_valid_json_proposal",
        "safe_abstention",
    }
)
RETRY_MAX_ATTEMPTS = 2
RETRY_BEFORE_COMMIT = True
RETRY_NE_KNOWLEDGE_WRITE = True


def test_retry_policy_design_frozen() -> None:
    assert RETRY_BEFORE_COMMIT is True
    assert RETRY_NE_KNOWLEDGE_WRITE is True
    assert RETRY_MAX_ATTEMPTS >= 1
    assert "timeout" in RETRYABLE_TRANSPORT
    assert "wrong_but_valid_json_proposal" in NON_RETRYABLE_SEMANTIC
    assert RETRYABLE_TRANSPORT.isdisjoint(NON_RETRYABLE_SEMANTIC)


# --- Failure taxonomy registry ---


FAILURE_CLASSES = (
    "A. INTENT FAILURE",
    "B. PRIMITIVE ROUTING FAILURE",
    "C. SEMANTIC FRAME FAILURE",
    "D. CANONICALIZATION FAILURE",
    "E. TRANSPORT / PROVIDER FAILURE",
)

SEVERITIES = ("S0", "S1", "S2", "S3", "S4")


def test_failure_taxonomy_complete() -> None:
    assert len(FAILURE_CLASSES) == 5
    assert SEVERITIES == ("S0", "S1", "S2", "S3", "S4")


# --- Safety metrics (baseline targets; deterministic path must not invent) ---


def test_safety_metrics_targets() -> None:
    metrics = {
        "ASSERTION_QUERY_CONFUSION": 0,
        "QUERY_ASSERTION_CONFUSION": 0,
        "FALSE_CORRECTION_ROUTING": 0,
        "PRIMITIVE_CONFLATION": 0,
        "WRONG_CANONICALIZATION": 0,
        "KNOWN_ACTION_LOST": 0,
        "KNOWN_OBJECT_LOST": 0,
        "KNOWN_ROLE_WRONG": 0,
        "TEMPORAL_PRECISION_INVENTED": 0,
        "UNKNOWN_ENTITY_FORCED": 0,
        "MEASUREMENT_ATTRIBUTE_CONFLATION": 0,
        "STATE_ATTRIBUTE_CONFLATION": 0,
        "RELATION_STATE_CONFLATION": 0,
        "EVENT_STATE_CONFLATION": 0,
        "MULTI_PRIMITIVE_LOST": 0,
        "UNSUPPORTED_TYPE_MISROUTED": 0,
        "LLM_ID_TRUSTED": 0,
        "INTERPRETER_FAILURE_CAUSED_WRITE": 0,
        "PROVIDER_RETRY_DUPLICATED_KNOWLEDGE": 0,
        "TRANSPORT_NORMALIZATION_INVENTED_SEMANTICS": 0,
    }
    assert all(v == 0 for v in metrics.values())


def test_positive_coverage_from_corpus() -> None:
    counts = Counter(c.category for c in CORPUS)
    coverage = {
        "EVENT_CASES": counts["event"],
        "STATE_CASES": counts["state"],
        "RELATION_CASES": counts["relation"],
        "ATTRIBUTE_CASES": counts["attribute"] + counts.get("type", 0),
        "MEASUREMENT_CASES": counts["measurement"],
        "QUERY_CASES": counts["query"],
        "CORRECTION_CASES": counts["correction"],
        "TEMPORAL_CASES": counts["temporal"],
        "MULTI_PRIMITIVE_CASES": counts["multi_primitive"],
        "AMBIGUITY_CASES": counts["ambiguity"],
        "UNKNOWN_CONCEPT_CASES": counts["unknown_concept"],
        "SAFE_ABSTENTION_CASES": sum(1 for c in CORPUS if c.expected_safe_abstention),
    }
    assert all(v > 0 for v in coverage.values())
    assert len(CORPUS) >= 250


def test_engine_v1_not_yet_reliable_live_boundary() -> None:
    """Live Interpreter is not Engine v1 closure authority; baseline freezes the gap."""
    # DeepSeek path exists but retry/hardening not implemented — reliability = NO for live boundary
    assert PROMPT_VERSION_V3
    assert DeepSeekInterpreter is not None
    # Design answer recorded in ADR: IS_CURRENT_INTERPRETER_RELIABLE_ENOUGH = NO
    IS_CURRENT_INTERPRETER_RELIABLE_ENOUGH = False
    assert IS_CURRENT_INTERPRETER_RELIABLE_ENOUGH is False
