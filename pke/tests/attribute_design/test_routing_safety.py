"""I11.12.1 — Attribute routing safety (AS1–AS8) + type contrasts + collapse metrics."""

from __future__ import annotations

import pytest

from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.persistability import assess_persistability
from pke.interpretation.semantic.resolver import resolve_concepts
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from tests.attribute_design import as_fixtures as afx


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


@pytest.mark.parametrize(
    ("factory", "expected", "forbid_attribute"),
    [
        (afx.as1_corolla_silver, PrimitiveKind.ATTRIBUTE, False),
        (afx.as2_corolla_is_car, PrimitiveKind.TYPE, True),
        (afx.as3_corolla_broken, PrimitiveKind.STATE, True),
        (afx.as4_corolla_broke, PrimitiveKind.EVENT, True),
        (afx.as5_corolla_belongs_joao, PrimitiveKind.RELATION, True),
        (afx.as6_house_area, PrimitiveKind.ATTRIBUTE, False),
        (afx.as7_tank_20_liters, PrimitiveKind.MEASUREMENT, True),
        (afx.as8_tank_capacity, PrimitiveKind.ATTRIBUTE, False),
    ],
    ids=["AS1", "AS2", "AS3", "AS4", "AS5", "AS6", "AS7", "AS8"],
)
def test_as_matrix(factory, expected, forbid_attribute) -> None:
    proposal = factory()
    primitive, _ = route_primitive(proposal)
    assert primitive is expected
    if forbid_attribute:
        assert primitive is not PrimitiveKind.ATTRIBUTE
    if expected is PrimitiveKind.TYPE:
        concepts = resolve_concepts(proposal, primitive)
        assert concepts.primitive is PrimitiveKind.TYPE
        assert concepts.attribute is None
        assert concepts.recognized_sense == "classification"
        outcome = proposal_to_canonical_ir(proposal)
        assert outcome.ir is None
        assessment = assess_persistability(outcome.result)
        assert assessment.wire_allowed is False


def test_type_contrasts() -> None:
    # Rex → classification
    p, _ = route_primitive(afx.tc_rex_dog())
    assert p is PrimitiveKind.TYPE
    assert p is not PrimitiveKind.ATTRIBUTE

    # Ana médica → descriptive Attribute-shaped today (occupation); not TYPE
    p, _ = route_primitive(afx.tc_ana_doctor())
    assert p is PrimitiveKind.ATTRIBUTE
    assert proposal_to_canonical_ir(afx.tc_ana_doctor()).ir is None  # still non-materializable

    # PDF → document classification
    p, _ = route_primitive(afx.tc_file_pdf())
    assert p is PrimitiveKind.TYPE

    # Electrolux → Relation (brand/manufacturer)
    p, _ = route_primitive(afx.tc_fridge_electrolux())
    assert p is PrimitiveKind.RELATION
    assert p is not PrimitiveKind.ATTRIBUTE


def test_false_collapse_metrics_zero() -> None:
    rows = [
        (afx.as1_corolla_silver, PrimitiveKind.ATTRIBUTE),
        (afx.as2_corolla_is_car, PrimitiveKind.TYPE),
        (afx.as3_corolla_broken, PrimitiveKind.STATE),
        (afx.as4_corolla_broke, PrimitiveKind.EVENT),
        (afx.as5_corolla_belongs_joao, PrimitiveKind.RELATION),
        (afx.as6_house_area, PrimitiveKind.ATTRIBUTE),
        (afx.as7_tank_20_liters, PrimitiveKind.MEASUREMENT),
        (afx.as8_tank_capacity, PrimitiveKind.ATTRIBUTE),
        (afx.tc_rex_dog, PrimitiveKind.TYPE),
        (afx.tc_file_pdf, PrimitiveKind.TYPE),
        (afx.tc_fridge_electrolux, PrimitiveKind.RELATION),
    ]
    type_to_attr = 0
    state_to_attr = 0
    rel_to_attr = 0
    event_to_attr = 0
    attr_to_other = 0
    for factory, expected in rows:
        actual, _ = route_primitive(factory())
        if expected is PrimitiveKind.TYPE and actual is PrimitiveKind.ATTRIBUTE:
            type_to_attr += 1
        if expected is PrimitiveKind.STATE and actual is PrimitiveKind.ATTRIBUTE:
            state_to_attr += 1
        if expected is PrimitiveKind.RELATION and actual is PrimitiveKind.ATTRIBUTE:
            rel_to_attr += 1
        if expected is PrimitiveKind.EVENT and actual is PrimitiveKind.ATTRIBUTE:
            event_to_attr += 1
        if expected is PrimitiveKind.ATTRIBUTE and actual is not PrimitiveKind.ATTRIBUTE:
            attr_to_other += 1
    assert type_to_attr == 0
    assert state_to_attr == 0
    assert rel_to_attr == 0
    assert event_to_attr == 0
    assert attr_to_other == 0


def test_schema_and_core_unchanged() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67
