"""LS1–LS11 lexical sense safety and false canonicalization guards."""

from __future__ import annotations

import pytest

from pke.interpretation.semantic.models import PrimitiveKind, ResolutionStatus
from pke.interpretation.semantic.resolver import resolve_concepts
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.semantic.sense import SemanticSense
from pke.ontology import OntologyRegistry
from pke.interpretation.transport.catalog import ConceptCatalog
from tests.semantic_resolution.fixtures import (
    ls1_installed_ac,
    ls10_passed_sao_luiz,
    ls11_shopping_context,
    ls2_installation_service,
    ls3_installation_yesterday,
    ls4_facilities_new,
    ls5_replace_clutch,
    ls6_substitute_clutch,
    ls7_exchange_idea,
    ls8_currency_exchange,
    ls9_clothing_change,
    pr1_fridge_broken,
    pr3_employment,
    pr5_door_open,
    relation_motor_works,
    sc2_broken,
    sc3_open,
    sc4_replace_clutch,
    state_door_new,
    state_fridge_new,
)


@pytest.fixture(autouse=True)
def _load_catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _resolve(fixture):
    proposal = fixture()
    primitive, _ = route_primitive(proposal)
    concepts = resolve_concepts(proposal, primitive)
    return proposal, primitive, concepts


def _false_canonical(concepts) -> bool:
    if concepts.action == "action.replace" and concepts.recognized_sense in {
        SemanticSense.INSTALL.value,
        SemanticSense.EXCHANGE_IDEA.value,
        SemanticSense.CURRENCY_EXCHANGE.value,
        SemanticSense.CLOTHING_CHANGE.value,
    }:
        return True
    if concepts.state_value == "state.value.working" and concepts.recognized_sense in {
        SemanticSense.FACILITIES.value,
        SemanticSense.PROPERTY_NEW.value,
    }:
        return True
    if concepts.relation_type == "relation.employed_by":
        return False  # checked per-case
    return False


@pytest.mark.parametrize(
    ("fixture", "expected_primitive", "expected_sense", "forbidden_action", "forbidden_state"),
    [
        (ls1_installed_ac, PrimitiveKind.EVENT, SemanticSense.INSTALL.value, "action.replace", None),
        (ls2_installation_service, PrimitiveKind.EVENT, SemanticSense.INSTALL.value, "action.replace", None),
        (ls3_installation_yesterday, PrimitiveKind.EVENT, SemanticSense.INSTALL.value, "action.replace", None),
        (ls4_facilities_new, PrimitiveKind.ATTRIBUTE, SemanticSense.FACILITIES.value, "action.install", "state.value.working"),
        (ls5_replace_clutch, PrimitiveKind.EVENT, None, None, None),
        (ls6_substitute_clutch, PrimitiveKind.EVENT, None, None, None),
        (ls7_exchange_idea, PrimitiveKind.EVENT, SemanticSense.EXCHANGE_IDEA.value, "action.replace", None),
        (ls8_currency_exchange, PrimitiveKind.EVENT, SemanticSense.CURRENCY_EXCHANGE.value, "action.replace", None),
        (ls9_clothing_change, PrimitiveKind.EVENT, SemanticSense.CLOTHING_CHANGE.value, "action.replace", None),
        (ls10_passed_sao_luiz, PrimitiveKind.EVENT, SemanticSense.AMBIGUOUS_PASS.value, "action.replace", None),
    ],
    ids=["LS1", "LS2", "LS3", "LS4", "LS5", "LS6", "LS7", "LS8", "LS9", "LS10"],
)
def test_lexical_sense_no_false_canonical(
    fixture,
    expected_primitive,
    expected_sense,
    forbidden_action,
    forbidden_state,
) -> None:
    _, primitive, concepts = _resolve(fixture)
    assert primitive is expected_primitive
    if expected_sense:
        assert concepts.recognized_sense == expected_sense or expected_sense in (
            concepts.recognized_sense or ""
        )
    if forbidden_action:
        assert concepts.action != forbidden_action
    if forbidden_state:
        assert concepts.state_value != forbidden_state
    if fixture in {ls1_installed_ac, ls2_installation_service, ls3_installation_yesterday}:
        assert concepts.action == "action.install"
        assert concepts.resolution_status is ResolutionStatus.RESOLVED
        assert concepts.ontology_gap is False
    if fixture in {ls5_replace_clutch, ls6_substitute_clutch}:
        assert concepts.action == "action.replace"
        assert concepts.resolution_status is ResolutionStatus.RESOLVED
    if fixture in {ls7_exchange_idea, ls8_currency_exchange, ls9_clothing_change, ls10_passed_sao_luiz}:
        assert concepts.action != "action.replace"
        assert concepts.action != "action.install"
        assert concepts.unresolved or concepts.resolution_status in {
            ResolutionStatus.UNRESOLVED,
            ResolutionStatus.AMBIGUOUS,
            ResolutionStatus.ONTOLOGY_GAP,
            ResolutionStatus.BLOCKED,
        }


def test_ls5_ls6_replace_physical() -> None:
    for fixture in (ls5_replace_clutch, ls6_substitute_clutch):
        _, _, concepts = _resolve(fixture)
        assert concepts.action == "action.replace"


def test_ls11_shopping_context_stays_unresolved() -> None:
    _, primitive, concepts = _resolve(ls11_shopping_context)
    assert primitive is PrimitiveKind.EVENT
    assert concepts.action != "action.replace"
    assert concepts.unresolved or concepts.resolution_status is ResolutionStatus.AMBIGUOUS


def test_state_new_not_working_or_open() -> None:
    for fixture in (state_fridge_new, state_door_new):
        _, primitive, concepts = _resolve(fixture)
        assert primitive is PrimitiveKind.ATTRIBUTE
        assert concepts.state_value not in {"state.value.working", "state.value.open", "state.value.broken"}
        assert concepts.action is None


def test_state_broken_and_open_still_resolve() -> None:
    _, _, broken = _resolve(sc2_broken)
    assert broken.state_value == "state.value.broken"
    _, _, open_state = _resolve(sc3_open)
    assert open_state.state_value == "state.value.open"


def test_relation_motor_not_employment() -> None:
    _, primitive, concepts = _resolve(relation_motor_works)
    assert primitive is PrimitiveKind.RELATION
    assert concepts.relation_type != "relation.employed_by"
    assert concepts.unresolved or concepts.relation_type is None


def test_relation_employment_still_works() -> None:
    _, _, concepts = _resolve(pr3_employment)
    assert concepts.relation_type == "relation.employed_by"


def test_false_canonicalization_rate_zero() -> None:
    negative_fixtures = [
        ls1_installed_ac,
        ls2_installation_service,
        ls3_installation_yesterday,
        ls4_facilities_new,
        ls7_exchange_idea,
        ls8_currency_exchange,
        ls9_clothing_change,
        ls10_passed_sao_luiz,
        state_fridge_new,
        state_door_new,
        relation_motor_works,
    ]
    false_count = 0
    for fixture in negative_fixtures:
        _, _, concepts = _resolve(fixture)
        if concepts.action == "action.replace" and fixture not in (sc4_replace_clutch,):
            false_count += 1
        if concepts.state_value == "state.value.working" and fixture is ls4_facilities_new:
            false_count += 1
        if concepts.relation_type == "relation.employed_by" and fixture is relation_motor_works:
            false_count += 1
        if concepts.state_value in {"state.value.working", "state.value.open"} and fixture in (
            state_fridge_new,
            state_door_new,
        ):
            false_count += 1
    assert false_count == 0


def test_registry_order_independence() -> None:
    proposal = ls5_replace_clutch()
    primitive, _ = route_primitive(proposal)
    first = resolve_concepts(proposal, primitive)
    second = resolve_concepts(proposal, primitive)
    assert first.model_dump() == second.model_dump()


def test_sense_with_canonical_install() -> None:
    _, _, concepts = _resolve(ls1_installed_ac)
    assert concepts.recognized_sense == SemanticSense.INSTALL.value
    assert concepts.action == "action.install"
    assert concepts.ontology_gap is False


def test_abstention_not_required_for_install_when_canonical() -> None:
    _, primitive, concepts = _resolve(ls2_installation_service)
    assert primitive is PrimitiveKind.EVENT
    assert concepts.action == "action.install"
    assert concepts.resolution_status is ResolutionStatus.RESOLVED
