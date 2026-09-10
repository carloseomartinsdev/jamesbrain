"""PX1–PX4 polysemy and negative cases."""

from __future__ import annotations

import pytest

from pke.interpretation.semantic.models import PrimitiveKind, ResolutionConfidence, ResolutionStatus
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.resolver import resolve_concepts
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.semantic.sense import SemanticSense
from pke.ontology import OntologyRegistry
from pke.interpretation.transport.catalog import ConceptCatalog
from tests.semantic_resolution.fixtures import (
    ambiguity_sao_luiz,
    px1_installation_service,
    px2_facilities_new,
    px3_replace_clutch,
    px4_exchange_idea,
)


@pytest.fixture(autouse=True)
def _load_catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def test_px1_installation_action_context() -> None:
    proposal = px1_installation_service()
    primitive, _ = route_primitive(proposal)
    concepts = resolve_concepts(proposal, primitive)
    assert primitive is PrimitiveKind.EVENT
    assert concepts.action == "action.install"
    assert concepts.action != "action.replace"
    assert concepts.recognized_sense == SemanticSense.INSTALL.value
    assert concepts.resolution_status is ResolutionStatus.RESOLVED
    assert concepts.ontology_gap is False


def test_px2_facilities_not_install_action() -> None:
    proposal = px2_facilities_new()
    primitive, _ = route_primitive(proposal)
    concepts = resolve_concepts(proposal, primitive)
    assert primitive is PrimitiveKind.ATTRIBUTE
    assert concepts.action is None
    assert concepts.action != "action.install"
    assert concepts.state_value is None
    assert concepts.state_value != "state.value.working"
    assert concepts.recognized_sense == SemanticSense.FACILITIES.value
    assert concepts.unresolved or concepts.ontology_gap


def test_px3_replace_clutch() -> None:
    proposal = px3_replace_clutch()
    concepts = resolve_concepts(proposal, route_primitive(proposal)[0])
    assert concepts.action == "action.replace"


def test_px4_exchange_idea_unresolved() -> None:
    proposal = px4_exchange_idea()
    primitive, _ = route_primitive(proposal)
    concepts = resolve_concepts(proposal, primitive)
    outcome = proposal_to_canonical_ir(proposal)
    assert concepts.unresolved or outcome.ir is None
    assert concepts.action != "action.replace"


def test_ambiguity_prefers_unresolved() -> None:
    proposal = ambiguity_sao_luiz()
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.result.concepts.confidence in {
        ResolutionConfidence.UNRESOLVED,
        ResolutionConfidence.AMBIGUOUS,
        ResolutionConfidence.CONTEXTUAL,
    }
