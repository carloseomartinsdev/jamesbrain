"""Deterministic failure taxonomy tests."""

from __future__ import annotations

import json

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry

from tests.engine_v1_baseline.corpus import CORPUS
from tests.model_variance_strategy.analyze_historical import analyze_artifacts
from tests.model_variance_strategy.failure_taxonomy import (
    audit_proposal_inconsistencies,
    classify_run,
    trace_from_raw,
)


def _case(needle: str):
    for c in CORPUS:
        if needle in c.utterance.casefold():
            return c
    raise AssertionError(needle)


def setup_module() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def test_mp1_complete_proposal_traces_to_measurement_wire() -> None:
    p = SemanticProposal(
        raw_input="medi a temperatura e deu 95°C",
        utterance_kind="assert",
        subject=SemanticEntityMention(text="temperatura", kind_hint="thing"),
        action_expression="medi",
        event_expression="medi a temperatura",
        change_semantics=True,
        measurement_expression="95°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="95",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=SemanticTime(occurrence_aspect="happened"),
    )
    raw = json.dumps({"ir_kind": "semantic_proposal", "ir": p.model_dump()}, ensure_ascii=False)
    tr = trace_from_raw(raw)
    assert tr.proposal_valid
    assert tr.wire_built
    assert tr.outcome_ir


def test_mp1_missing_subject_concept_resolution() -> None:
    p = SemanticProposal(
        raw_input="medi a temperatura e deu 95°C",
        utterance_kind="assert",
        change_semantics=True,
        action_expression="medi",
        measurement_semantics=True,
        measurement_expression="95°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="95",
        measurement_unit="°C",
        temporal=SemanticTime(occurrence_aspect="happened"),
    )
    raw = json.dumps({"ir_kind": "semantic_proposal", "ir": p.model_dump()}, ensure_ascii=False)
    tr = trace_from_raw(raw)
    assert tr.proposal_valid
    assert not tr.wire_built
    assert tr.first_fault_stage == "S4_CONCEPT_RESOLUTION"


def test_internal_inconsistency_correction_without_intent() -> None:
    p = SemanticProposal(
        raw_input="x",
        utterance_kind="assert",
        correction_semantics=True,
        correction_operation="replace",
        measurement_semantics=True,
        measurement_expression="36°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="36",
        measurement_unit="°C",
        temporal=SemanticTime(occurrence_aspect="happened"),
    )
    issues = audit_proposal_inconsistencies(p)
    assert "correction_semantics_without_correct_intent" in issues


def test_historical_analysis_runs() -> None:
    result = analyze_artifacts()
    assert result["HISTORICAL_ROWS_ANALYZED"] > 0
    assert "MP1_FORENSIC" in result


def test_classify_mp1_missing_event() -> None:
    case = _case("medi a temperatura e deu 95")
    p = SemanticProposal(
        raw_input=case.utterance,
        utterance_kind="assert",
        measurement_semantics=True,
        measurement_expression="95°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="95",
        measurement_unit="°C",
        subject=SemanticEntityMention(text="temperatura"),
        primitive_hint="measurement",
        temporal=SemanticTime(occurrence_aspect="happened"),
    )
    raw = json.dumps({"ir_kind": "semantic_proposal", "ir": p.model_dump()}, ensure_ascii=False)
    cls = classify_run(case, raw_content=raw, ir_ok=True)
    assert cls.primary in {"SEMANTIC_OMISSION", "WRONG_SEMANTIC_DECISION", "CORRECT"}
    assert "event" not in cls.observed_primitive_set
