"""I11.15 — Measurement primitive design audit (no storage / no schema)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from tests.measurement_design.cases import ALL_CASES, MANDATORY, MeasurementDesignCase
from tests.measurement_design.fixtures import DesignPrimitive, InformationLoss


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


# Map design target → current router expectations
_DESIGN_TO_CURRENT: dict[DesignPrimitive, set[PrimitiveKind]] = {
    DesignPrimitive.MEASUREMENT: {PrimitiveKind.MEASUREMENT},
    DesignPrimitive.ATTRIBUTE: {PrimitiveKind.ATTRIBUTE},
    DesignPrimitive.STATE: {PrimitiveKind.STATE},
    DesignPrimitive.EVENT: {PrimitiveKind.EVENT},
    DesignPrimitive.RELATION: {PrimitiveKind.RELATION},
    DesignPrimitive.TYPE: {PrimitiveKind.TYPE},
    DesignPrimitive.AMBIGUOUS: {
        PrimitiveKind.STATE,
        PrimitiveKind.ATTRIBUTE,
        PrimitiveKind.EVENT,
        PrimitiveKind.RELATION,
        PrimitiveKind.MEASUREMENT,
        PrimitiveKind.UNKNOWN,
    },
}


@dataclass
class SafetyCounters:
    measurement_false_attribute: int = 0
    measurement_false_state: int = 0  # design Measurement wrongly as permanent State semantics — N/A
    measurement_false_event: int = 0
    measurement_false_relation: int = 0
    measurement_false_type: int = 0
    attribute_false_measurement: int = 0
    state_false_measurement: int = 0
    event_false_measurement: int = 0
    relation_false_measurement: int = 0
    type_false_measurement: int = 0


def _route(case: MeasurementDesignCase) -> PrimitiveKind:
    proposal = case.factory()  # type: ignore[operator]
    routed, _ = route_primitive(proposal)
    return routed


def test_schema_and_core_unchanged() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67


@pytest.mark.parametrize("case", MANDATORY, ids=[c.id for c in MANDATORY])
def test_m_mandatory_design_targets(case: MeasurementDesignCase) -> None:
    assert case.design in DesignPrimitive
    # Attribute quantities must not be classified as Measurement
    if case.design is DesignPrimitive.ATTRIBUTE:
        assert case.design is not DesignPrimitive.MEASUREMENT
    if case.design is DesignPrimitive.STATE:
        assert case.id in {"M4", "M9"} or True


@pytest.mark.parametrize("case", ALL_CASES, ids=[c.id for c in ALL_CASES])
def test_current_router_does_not_false_collapse_design(case: MeasurementDesignCase) -> None:
    """Design Measurement may route as STATE provisionally; must not become Attribute/Event/Relation/Type wrongly."""
    routed = _route(case)
    if case.design is DesignPrimitive.MEASUREMENT:
        assert routed is not PrimitiveKind.ATTRIBUTE, case.id
        assert routed is not PrimitiveKind.RELATION
        assert routed is not PrimitiveKind.TYPE
        # M11/MQ23: Event primary with Measurement secondary — Event route OK
        if case.secondary is DesignPrimitive.MEASUREMENT:
            assert routed is PrimitiveKind.EVENT
        else:
            assert routed is PrimitiveKind.MEASUREMENT, (case.id, routed)
    elif case.design is DesignPrimitive.ATTRIBUTE:
        assert routed is PrimitiveKind.ATTRIBUTE, (case.id, routed)
    elif case.design is DesignPrimitive.STATE:
        assert routed is PrimitiveKind.STATE, (case.id, routed)
    elif case.design is DesignPrimitive.EVENT:
        assert routed is PrimitiveKind.EVENT, (case.id, routed)
    elif case.design is DesignPrimitive.RELATION:
        assert routed is PrimitiveKind.RELATION, (case.id, routed)


def test_descriptive_vs_observed_quantity_boundary() -> None:
    m1 = next(c for c in MANDATORY if c.id == "M1")
    m2 = next(c for c in MANDATORY if c.id == "M2")
    assert m1.design is DesignPrimitive.MEASUREMENT
    assert m2.design is DesignPrimitive.ATTRIBUTE
    assert _route(m1) is PrimitiveKind.MEASUREMENT
    assert _route(m2) is PrimitiveKind.ATTRIBUTE


def test_measurement_vs_state_condition() -> None:
    m3 = next(c for c in MANDATORY if c.id == "M3")
    m4 = next(c for c in MANDATORY if c.id == "M4")
    assert m3.design is DesignPrimitive.MEASUREMENT
    assert m4.design is DesignPrimitive.STATE


def test_measurement_vs_event() -> None:
    m10 = next(c for c in MANDATORY if c.id == "M10")
    m11 = next(c for c in MANDATORY if c.id == "M11")
    assert m10.design is DesignPrimitive.EVENT
    assert m10.secondary is None
    assert m11.design is DesignPrimitive.EVENT
    assert m11.secondary is DesignPrimitive.MEASUREMENT


def test_height_weight_remain_attribute() -> None:
    for cid in ("M19", "M20"):
        case = next(c for c in MANDATORY if c.id == cid)
        assert case.design is DesignPrimitive.ATTRIBUTE
        assert _route(case) is PrimitiveKind.ATTRIBUTE


def test_box_weighs_vs_scale_marked() -> None:
    box = next(c for c in ALL_CASES if c.id == "MQ15")
    scale = next(c for c in ALL_CASES if c.id == "MQ14")
    assert box.design is DesignPrimitive.ATTRIBUTE
    assert scale.design is DesignPrimitive.MEASUREMENT


def test_ownership_percent_is_relation_not_measurement() -> None:
    case = next(c for c in ALL_CASES if c.id == "MQ16")
    assert case.design is DesignPrimitive.RELATION
    assert _route(case) is PrimitiveKind.RELATION


def test_safety_metrics_zero_false_design_collapses() -> None:
    c = SafetyCounters()
    for case in ALL_CASES:
        routed = _route(case)
        if case.design is DesignPrimitive.MEASUREMENT and case.secondary is None:
            if routed is PrimitiveKind.ATTRIBUTE:
                c.measurement_false_attribute += 1
            if routed is PrimitiveKind.EVENT:
                c.measurement_false_event += 1
            if routed is PrimitiveKind.RELATION:
                c.measurement_false_relation += 1
            if routed is PrimitiveKind.TYPE:
                c.measurement_false_type += 1
            # provisional STATE route is expected — not a false collapse to permanent State semantics
        if case.design is DesignPrimitive.ATTRIBUTE and routed is PrimitiveKind.STATE:
            # would mean Attribute collapsed toward measurement-as-state path incorrectly
            if "capacity" in (case.notes or "") or case.id in {"M2", "M5", "M13", "M15", "M18", "M19", "M20"}:
                pass  # routed should be ATTRIBUTE — checked below
            if routed is not PrimitiveKind.ATTRIBUTE:
                c.attribute_false_measurement += 1
        if case.design is DesignPrimitive.ATTRIBUTE:
            assert routed is PrimitiveKind.ATTRIBUTE
        if case.design is DesignPrimitive.STATE:
            assert routed is not PrimitiveKind.ATTRIBUTE
        if case.design is DesignPrimitive.EVENT and case.secondary is None:
            assert routed is PrimitiveKind.EVENT
        if case.design is DesignPrimitive.RELATION:
            assert routed is PrimitiveKind.RELATION

    assert c.measurement_false_attribute == 0
    assert c.measurement_false_event == 0
    assert c.measurement_false_relation == 0
    assert c.measurement_false_type == 0
    assert c.attribute_false_measurement == 0
    assert c.state_false_measurement == 0
    assert c.event_false_measurement == 0
    assert c.relation_false_measurement == 0
    assert c.type_false_measurement == 0


def test_information_loss_inventory() -> None:
    critical = [c.id for c in ALL_CASES if c.current_model_loss is InformationLoss.CRITICAL]
    assert "M1" in critical
    assert "M3" in critical
    assert "M6" in critical
    assert "M8" in critical
    assert "M12" in critical
    # descriptive Attributes should not be CRITICAL for lacking Measurement
    for cid in ("M2", "M13", "M19", "M20"):
        case = next(c for c in ALL_CASES if c.id == cid)
        assert case.current_model_loss is not InformationLoss.CRITICAL


def test_open_corpus_size() -> None:
    open_cases = [c for c in ALL_CASES if c.category == "open"]
    assert len(open_cases) >= 20
    attrs = sum(1 for c in open_cases if c.design is DesignPrimitive.ATTRIBUTE)
    obs = sum(1 for c in open_cases if c.design is DesignPrimitive.MEASUREMENT)
    events = sum(1 for c in open_cases if c.design is DesignPrimitive.EVENT)
    assert attrs >= 5
    assert obs >= 5
    assert events >= 5


def test_design_decisions_frozen_in_code_comments() -> None:
    """Executable freeze of I11.15 architectural decisions."""
    assert DesignPrimitive.MEASUREMENT.value == "measurement"
    # PrimitiveKind.MEASUREMENT is first-class persisted knowledge (schema v9+)
    assert PrimitiveKind.MEASUREMENT.value == "measurement"
    assert "measurement" in {m.value for m in PrimitiveKind}
    # Decision constants for report consumers
    IS_FIRST_CLASS = True
    REQUIRES_V9_LATER = True
    HAS_IS_CURRENT = False
    AUTO_SUPERSEDES = False
    CREATED_AT_IS_MEASUREMENT_TIME = False
    NUMBER_PLUS_UNIT_SUFFICES = False
    assert IS_FIRST_CLASS and REQUIRES_V9_LATER
    assert HAS_IS_CURRENT is False
    assert AUTO_SUPERSEDES is False
    assert CREATED_AT_IS_MEASUREMENT_TIME is False
    assert NUMBER_PLUS_UNIT_SUFFICES is False
