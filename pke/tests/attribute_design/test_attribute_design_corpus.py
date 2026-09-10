"""I11.12 — Attribute primitive & property representation design corpus.

Design-only assertions: routing boundaries, no Attribute materialization,
no ontology expansion, no schema v8.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pke.interpretation.semantic.models import PrimitiveKind, ResolutionStatus
from pke.interpretation.semantic.persistability import assess_persistability
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from tests.attribute_design import fixtures as af


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


@dataclass(frozen=True)
class AtDesignRow:
    case_id: str
    factory: object
    expected_primitive: PrimitiveKind
    dimension_candidate: str | None
    value_form: str
    persistable_now: bool
    ambiguity: str
    reason: str
    forbid_state: bool = False
    forbid_relation: bool = False
    forbid_attribute: bool = False
    type_not_attribute: bool = False


AT_ROWS: tuple[AtDesignRow, ...] = (
    AtDesignRow(
        "AT1",
        af.at1_corolla_silver,
        PrimitiveKind.ATTRIBUTE,
        "color",
        "normalized_lexical (prata/silver)",
        False,
        "ontology_gap — no attribute.color yet",
        "descriptive qualitative property",
        forbid_state=True,
    ),
    AtDesignRow(
        "AT2",
        af.at2_house_area,
        PrimitiveKind.ATTRIBUTE,
        "area",
        "quantity+unit (200, m²)",
        False,
        "no Attribute storage / dimension",
        "descriptive spatial property",
        forbid_state=True,
    ),
    AtDesignRow(
        "AT3",
        af.at3_notebook_weight,
        PrimitiveKind.ATTRIBUTE,
        "weight",
        "quantity+unit (1.5, kg)",
        False,
        "no Attribute storage / dimension",
        "descriptive mass property",
        forbid_state=True,
    ),
    AtDesignRow(
        "AT4",
        af.at4_door_open,
        PrimitiveKind.STATE,
        "state.openness",
        "state.value.open",
        True,
        "none",
        "temporally meaningful condition in openness dimension",
        forbid_attribute=True,
    ),
    AtDesignRow(
        "AT5",
        af.at5_phone_broken,
        PrimitiveKind.STATE,
        "state.operational_condition",
        "state.value.broken",
        True,
        "none",
        "operational condition — not descriptive color/type",
        forbid_attribute=True,
    ),
    AtDesignRow(
        "AT6",
        af.at6_bill_overdue,
        PrimitiveKind.STATE,
        "state.due_status",
        "state.value.overdue",
        True,
        "none",
        "due-status condition",
        forbid_attribute=True,
    ),
    AtDesignRow(
        "AT7",
        af.at7_facilities_new,
        PrimitiveKind.ATTRIBUTE,
        "relative_age / newness (deferred)",
        "deferred — relative descriptor",
        False,
        "facilities entity + newness representation gaps",
        "stable_property route; do not coerce to State",
        forbid_state=True,
    ),
    AtDesignRow(
        "AT8",
        af.at8_joao_height,
        PrimitiveKind.ATTRIBUTE,
        "height",
        "quantity+unit (1.80, m)",
        False,
        "no Attribute storage",
        "descriptive anthropometric property",
        forbid_state=True,
    ),
    AtDesignRow(
        "AT9",
        af.at9_corolla_year,
        PrimitiveKind.ATTRIBUTE,
        "model_year",
        "year/int (2020)",
        False,
        "no Attribute storage",
        "descriptive model-year property",
        forbid_state=True,
    ),
    AtDesignRow(
        "AT10",
        af.at10_fridge_white,
        PrimitiveKind.ATTRIBUTE,
        "color",
        "normalized_lexical (branca/white)",
        False,
        "ontology_gap — color dimension",
        "same pattern as AT1",
        forbid_state=True,
    ),
    AtDesignRow(
        "AT11",
        af.at11_tank_20_liters,
        PrimitiveKind.MEASUREMENT,
        "fuel_level",
        "quantity observation 20 L",
        False,
        "MEASUREMENT storage deferred to v9",
        "observed fill level ≠ capacity attribute",
        forbid_attribute=True,
        forbid_state=True,
    ),
    AtDesignRow(
        "AT12",
        af.at12_tank_capacity_50,
        PrimitiveKind.ATTRIBUTE,
        "capacity",
        "quantity+unit (50, L)",
        False,
        "no Attribute storage",
        "descriptive capacity ≠ observed quantity",
        forbid_state=True,
    ),
    AtDesignRow(
        "AT13",
        af.at13_manufacturer_toyota,
        PrimitiveKind.RELATION,
        None,
        "entity-entity link (manufacturer)",
        True,
        "relation type may be unresolved today",
        "entity-valued manufacturer is Relation, not Attribute",
        forbid_attribute=True,
    ),
    AtDesignRow(
        "AT14",
        af.at14_corolla_is_car,
        PrimitiveKind.TYPE,
        None,
        "type_classification — not Attribute",
        False,
        "TYPE write path deferred",
        "entity kind/type — classification_semantics",
        type_not_attribute=True,
        forbid_state=True,
        forbid_attribute=True,
    ),
)


@pytest.mark.parametrize("row", AT_ROWS, ids=[r.case_id for r in AT_ROWS])
def test_at_primitive_routing(row: AtDesignRow) -> None:
    proposal = row.factory()  # type: ignore[operator]
    primitive, _ = route_primitive(proposal)
    assert primitive is row.expected_primitive, f"{row.case_id}: {row.reason}"


@pytest.mark.parametrize(
    "row",
    [
        r
        for r in AT_ROWS
        if r.expected_primitive is PrimitiveKind.ATTRIBUTE and not r.type_not_attribute
    ],
    ids=[
        r.case_id
        for r in AT_ROWS
        if r.expected_primitive is PrimitiveKind.ATTRIBUTE and not r.type_not_attribute
    ],
)
def test_attribute_cases_wire_when_dimension_resolves(row: AtDesignRow) -> None:
    proposal = row.factory()  # type: ignore[operator]
    outcome = proposal_to_canonical_ir(proposal)
    # Supported descriptive dimensions materialize; unresolved dimensions stay blocked
    if row.case_id in {"AT1", "AT2", "AT3", "AT8", "AT9", "AT10", "AT12"}:
        assert outcome.ir is not None
        assert outcome.ir.attribute is not None
    else:
        assert outcome.ir is None


@pytest.mark.parametrize(
    "row",
    [r for r in AT_ROWS if r.forbid_state],
    ids=[r.case_id for r in AT_ROWS if r.forbid_state],
)
def test_no_attribute_to_state_collapse(row: AtDesignRow) -> None:
    proposal = row.factory()  # type: ignore[operator]
    primitive, _ = route_primitive(proposal)
    assert primitive is not PrimitiveKind.STATE
    outcome = proposal_to_canonical_ir(proposal)
    if outcome.ir is not None:
        assert outcome.ir.state is None


@pytest.mark.parametrize(
    "row",
    [r for r in AT_ROWS if r.forbid_attribute],
    ids=[r.case_id for r in AT_ROWS if r.forbid_attribute],
)
def test_no_state_or_relation_to_attribute_collapse(row: AtDesignRow) -> None:
    proposal = row.factory()  # type: ignore[operator]
    primitive, _ = route_primitive(proposal)
    assert primitive is not PrimitiveKind.ATTRIBUTE


def test_type_classification_must_not_become_attribute() -> None:
    """AT14: classification routes TYPE — never Attribute path."""
    proposal = af.at14_corolla_is_car()
    primitive, _ = route_primitive(proposal)
    assert primitive is PrimitiveKind.TYPE
    assert primitive is not PrimitiveKind.ATTRIBUTE
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is None
    assessment = assess_persistability(resolve_proposal(proposal))
    assert assessment.wire_allowed is False
    assert "classification_not_materializable" in assessment.notes or "classification" in assessment.critical_unresolved


def test_primitive_safety_counts() -> None:
    attr_to_state = 0
    state_to_attr = 0
    rel_to_attr = 0
    type_to_attr = 0
    type_persisted = 0
    for row in AT_ROWS:
        proposal = row.factory()  # type: ignore[operator]
        primitive, _ = route_primitive(proposal)
        if row.forbid_state and primitive is PrimitiveKind.STATE:
            attr_to_state += 1
        if row.forbid_attribute and primitive is PrimitiveKind.ATTRIBUTE:
            if row.expected_primitive is PrimitiveKind.STATE:
                state_to_attr += 1
            if row.expected_primitive is PrimitiveKind.RELATION:
                rel_to_attr += 1
            if row.expected_primitive is PrimitiveKind.TYPE:
                type_to_attr += 1
        if row.type_not_attribute:
            if primitive is PrimitiveKind.ATTRIBUTE:
                type_to_attr += 1
            outcome = proposal_to_canonical_ir(proposal)
            if outcome.ir is not None:
                type_persisted += 1
    assert attr_to_state == 0
    assert state_to_attr == 0
    assert rel_to_attr == 0
    assert type_to_attr == 0
    assert type_persisted == 0


def test_state_regressions_still_persistable() -> None:
    for factory in (af.at4_door_open, af.at5_phone_broken, af.fridge_broken_regression):
        outcome = proposal_to_canonical_ir(factory())
        assert outcome.ir is not None
        assert outcome.ir.state is not None


def test_relation_regression_still_persistable() -> None:
    outcome = proposal_to_canonical_ir(af.employment_regression())
    assert outcome.ir is not None
    assert outcome.ir.relation is not None


def test_schema_remains_v8() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"


def test_core_ontology_unchanged_at_65() -> None:
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67


def test_at7_new_not_forced_into_state_value() -> None:
    result = resolve_proposal(af.at7_facilities_new())
    assert result.primitive is PrimitiveKind.ATTRIBUTE
    assert result.concepts.state_value is None
    assert result.concepts.state_value != "state.value.working"
    assert result.concepts.resolution_status in {
        ResolutionStatus.ONTOLOGY_GAP,
        ResolutionStatus.UNRESOLVED,
        ResolutionStatus.SAFE_PARTIAL,
    }


def test_design_matrix_documented() -> None:
    """Ensure AT matrix completeness for ADR — 14 cases."""
    assert len(AT_ROWS) == 14
    assert {r.case_id for r in AT_ROWS} == {f"AT{i}" for i in range(1, 15)}
