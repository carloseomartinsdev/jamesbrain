"""SC1–SC6 semantic concept resolution."""

from __future__ import annotations

import pytest

from pke.interpretation.semantic.models import ResolutionConfidence
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.resolver import resolve_concepts
from pke.interpretation.semantic.router import route_primitive
from pke.ontology import OntologyRegistry
from pke.interpretation.transport.catalog import ConceptCatalog
from tests.semantic_resolution.fixtures import (
    sc1_employment,
    sc2_broken,
    sc3_open,
    sc4_replace_clutch,
    sc5_substitute_clutch,
    sc6_overdue,
)


@pytest.fixture(autouse=True)
def _load_catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


@pytest.mark.parametrize(
    ("fixture", "relation", "dimension", "value", "action"),
    [
        (sc1_employment, "relation.employed_by", None, None, None),
        (sc2_broken, None, "state.operational_condition", "state.value.broken", None),
        (sc3_open, None, "state.openness", "state.value.open", None),
        (sc4_replace_clutch, None, None, None, "action.replace"),
        (sc5_substitute_clutch, None, None, None, "action.replace"),
        (sc6_overdue, None, "state.due_status", "state.value.overdue", None),
    ],
    ids=["SC1", "SC2", "SC3", "SC4", "SC5", "SC6"],
)
def test_concept_resolution(fixture, relation, dimension, value, action) -> None:
    proposal = fixture()
    primitive, _ = route_primitive(proposal)
    concepts = resolve_concepts(proposal, primitive)
    assert concepts.unresolved is False
    assert concepts.confidence in {ResolutionConfidence.EXACT, ResolutionConfidence.CONTEXTUAL}
    if relation:
        assert concepts.relation_type == relation
    if dimension:
        assert concepts.state_dimension == dimension
    if value:
        assert concepts.state_value == value
    if action:
        assert concepts.action == action


def test_sc6_not_unpaid() -> None:
    proposal = sc6_overdue()
    primitive, _ = route_primitive(proposal)
    concepts = resolve_concepts(proposal, primitive)
    assert concepts.state_value != "state.value.unpaid"


def test_pipeline_produces_canonical_ir() -> None:
    outcome = proposal_to_canonical_ir(sc1_employment())
    assert outcome.ir is not None
    assert outcome.ir.intent.value == "record_relation"
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.employed_by"
