"""I11.14 — Pairwise boundary freeze documentation as executable checks."""

from __future__ import annotations

import pytest

from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from tests.semantic_audit.harness import CorpusCase, audit_case
from tests.semantic_audit.cases import (
    cp1_tank_capacity,
    cp2_tank_observed,
    cp3_corolla_silver,
    cp5_corolla_is_car,
    cp6_employment,
    cp8_manufacturer,
    cp9_corolla_broke,
    cp10_corolla_broken,
    cp25_door_open,
    cp26_joao_opened_door,
)


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _route(factory, expected: PrimitiveKind, *forbid: PrimitiveKind) -> None:
    case = CorpusCase("tmp", factory, expected, forbid)
    out = audit_case(case)
    assert out.routed is expected
    for f in forbid:
        assert out.routed is not f


def test_attribute_vs_state() -> None:
    _route(cp3_corolla_silver, PrimitiveKind.ATTRIBUTE, PrimitiveKind.STATE)
    _route(cp10_corolla_broken, PrimitiveKind.STATE, PrimitiveKind.ATTRIBUTE)
    _route(cp1_tank_capacity, PrimitiveKind.ATTRIBUTE, PrimitiveKind.STATE)
    _route(cp2_tank_observed, PrimitiveKind.MEASUREMENT, PrimitiveKind.ATTRIBUTE)


def test_attribute_vs_relation() -> None:
    _route(cp3_corolla_silver, PrimitiveKind.ATTRIBUTE, PrimitiveKind.RELATION)
    _route(cp8_manufacturer, PrimitiveKind.RELATION, PrimitiveKind.ATTRIBUTE)


def test_attribute_vs_type() -> None:
    _route(cp3_corolla_silver, PrimitiveKind.ATTRIBUTE, PrimitiveKind.TYPE)
    _route(cp5_corolla_is_car, PrimitiveKind.TYPE, PrimitiveKind.ATTRIBUTE)


def test_state_vs_event() -> None:
    _route(cp10_corolla_broken, PrimitiveKind.STATE, PrimitiveKind.EVENT)
    _route(cp9_corolla_broke, PrimitiveKind.EVENT, PrimitiveKind.STATE)
    _route(cp25_door_open, PrimitiveKind.STATE, PrimitiveKind.EVENT)
    _route(cp26_joao_opened_door, PrimitiveKind.EVENT, PrimitiveKind.STATE)


def test_state_vs_relation() -> None:
    _route(cp10_corolla_broken, PrimitiveKind.STATE, PrimitiveKind.RELATION)
    _route(cp6_employment, PrimitiveKind.RELATION, PrimitiveKind.STATE)


def test_event_vs_relation() -> None:
    _route(cp9_corolla_broke, PrimitiveKind.EVENT, PrimitiveKind.RELATION)
    _route(cp6_employment, PrimitiveKind.RELATION, PrimitiveKind.EVENT)


def test_event_vs_attribute() -> None:
    _route(cp9_corolla_broke, PrimitiveKind.EVENT, PrimitiveKind.ATTRIBUTE)
    _route(cp3_corolla_silver, PrimitiveKind.ATTRIBUTE, PrimitiveKind.EVENT)


def test_relation_vs_type() -> None:
    _route(cp8_manufacturer, PrimitiveKind.RELATION, PrimitiveKind.TYPE)
    _route(cp5_corolla_is_car, PrimitiveKind.TYPE, PrimitiveKind.RELATION)


def test_state_vs_type() -> None:
    _route(cp10_corolla_broken, PrimitiveKind.STATE, PrimitiveKind.TYPE)
    _route(cp5_corolla_is_car, PrimitiveKind.TYPE, PrimitiveKind.STATE)
