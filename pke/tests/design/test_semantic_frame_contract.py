"""Contratos experimentais I11.2 — isolados de produção."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pke.design.behavioral import (
    BehavioralPattern,
    ClarificationPolicy,
    ConceptMappingType,
    ContextualHypothesis,
    HypothesisStatus,
    InformationValueProfile,
)
from pke.design.scenarios import (
    scenario_a_oil_change,
    scenario_b_bought_oranges,
    scenario_c_cardiologist_forgotten,
    scenario_e_behavioral_grocery,
    scenario_g_broken_fridge,
    select_mileage_question,
)
from pke.design.semantic_frame import (
    Occurrence,
    SemanticFrame,
    SemanticInformationLoss,
    SlotStatus,
)
from pke.design.temporal_knowledge import (
    RelationToNow,
    TemporalAspect,
    TemporalKnowledge,
    TemporalUnknownReason,
)


def test_valid_incomplete_knowledge_principle() -> None:
    occ = scenario_a_oil_change()
    assert occ.is_valid_incomplete
    assert "quantity" in occ.enrichment.high_value_missing
    assert "quantity" in occ.enrichment.unknown_dimensions


def test_temporal_past_without_absolute_date() -> None:
    occ = scenario_b_bought_oranges()
    assert occ.temporal.relation_to_now is RelationToNow.PAST
    assert occ.temporal.aspect is TemporalAspect.COMPLETED
    assert not occ.temporal.has_absolute_calendar_time


def test_forgotten_differs_from_not_provided() -> None:
    forgotten = scenario_c_cardiologist_forgotten().temporal
    not_provided = TemporalKnowledge(
        relation_to_now=RelationToNow.PAST,
        aspect=TemporalAspect.COMPLETED,
        unknown_reason=TemporalUnknownReason.NOT_PROVIDED,
    )
    assert forgotten.is_distinct_from(not_provided)
    assert forgotten.unknown_reason is TemporalUnknownReason.FORGOTTEN


def test_state_without_invented_event() -> None:
    occ = scenario_g_broken_fridge()
    assert occ.frame.state_transition.status is SlotStatus.KNOWN
    assert occ.frame.event_type.status is SlotStatus.NOT_APPLICABLE
    assert occ.frame.action.status is SlotStatus.NOT_APPLICABLE


def test_behavioral_pattern_not_fact() -> None:
    occ, pattern, hypothesis = scenario_e_behavioral_grocery()
    assert occ.frame.place.status is not SlotStatus.KNOWN
    assert hypothesis.status is HypothesisStatus.PROPOSED
    assert "place" not in occ.frame.place.concept_keys
    assert pattern.support == 18


def test_clarification_prefers_mileage_over_vehicle() -> None:
    assert select_mileage_question() == "mileage"


def test_destructive_generalization_enum() -> None:
    assert SemanticInformationLoss.DESTRUCTIVE.value == "destructive"


def test_concept_mapping_types_distinct() -> None:
    assert ConceptMappingType.CANONICAL_ALIAS != ConceptMappingType.TYPE_LEXEME
    assert ConceptMappingType.INSTANCE_MENTION != ConceptMappingType.ROLE_CUE


def test_semantic_model_json_exists_and_valid() -> None:
    path = Path(__file__).resolve().parents[2] / "docs" / "design" / "I11.2-SEMANTIC-MODEL.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "semantic_dimensions" in data
    assert "temporal_dimensions" in data
    assert "implementation_candidates" in data
    assert len(data["implementation_candidates"]) >= 7


def test_clarification_policy_non_blocking() -> None:
    policy = ClarificationPolicy()
    assert policy.block_on_useful_missing is False
    assert policy.max_questions_per_turn == 1


def test_occurrence_coverage_map() -> None:
    occ = scenario_a_oil_change()
    cov = occ.frame.coverage_map()
    assert cov["ACTION"] == "known"
    assert cov["VALUE"] == "missing"


def test_design_not_imported_in_production_paths() -> None:
    """Garantia leve: application não importa pke.design."""
    app_root = Path(__file__).resolve().parents[2] / "src" / "pke" / "application"
    for path in app_root.rglob("*.py"):
        assert "pke.design" not in path.read_text(encoding="utf-8")
