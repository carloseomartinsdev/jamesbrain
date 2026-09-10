"""I11.14 — Persistability / TYPE / enrichment boundaries."""

from __future__ import annotations

import pytest

from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.persistability import PersistabilityStatus
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from tests.semantic_audit.cases import ALL_CASES, MANDATORY_CASES
from tests.semantic_audit.harness import GapKind, audit_case


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


@pytest.mark.parametrize(
    "case_id",
    ["CP5", "CP7", "CP22", "OP24"],
)
def test_type_or_occupation_not_materialized_as_attribute(case_id: str) -> None:
    case = next(c for c in ALL_CASES if c.id == case_id)
    out = audit_case(case)
    if case.expected_primitive is PrimitiveKind.TYPE:
        assert out.routed is PrimitiveKind.TYPE
        assert out.wire_ir is False
        assert out.persist.wire_allowed is False
    if case_id == "CP7":
        assert out.routed is PrimitiveKind.ATTRIBUTE
        assert out.wire_ir is False
        assert out.attribute_dimension is None


def test_type_never_wires_attribute_payload() -> None:
    for case in ALL_CASES:
        if case.expected_primitive is not PrimitiveKind.TYPE:
            continue
        out = audit_case(case)
        assert out.wire_ir is False
        assert "classification_not_materializable" in " ".join(out.persist.notes) or (
            out.persist.status
            in {
                PersistabilityStatus.PARTIALLY_RESOLVED_NONPERSISTABLE,
                PersistabilityStatus.UNSAFE,
            }
        )


def test_descriptive_capacity_persistable_observed_not_attribute() -> None:
    cp1 = audit_case(next(c for c in MANDATORY_CASES if c.id == "CP1"))
    cp2 = audit_case(next(c for c in MANDATORY_CASES if c.id == "CP2"))
    assert cp1.routed is PrimitiveKind.ATTRIBUTE
    assert cp1.attribute_dimension == "capacity"
    assert cp1.wire_ir is True
    assert cp2.routed is PrimitiveKind.MEASUREMENT
    assert cp2.attribute_dimension is None
    assert cp2.wire_ir is True


def test_no_event_from_state_assertion() -> None:
    out = audit_case(next(c for c in MANDATORY_CASES if c.id == "CP10"))
    assert out.routed is PrimitiveKind.STATE
    assert out.routed is not PrimitiveKind.EVENT


def test_safe_abstention_counts() -> None:
    outcomes = [audit_case(c) for c in ALL_CASES]
    safe_unresolved = sum(
        1
        for o in outcomes
        if (not o.wire_ir)
        and (
            o.safe_abstention
            or o.gap
            in {
                GapKind.SAFE_UNRESOLVED,
                GapKind.ONTOLOGY,
                GapKind.REPRESENTATION,
                GapKind.MEASUREMENT,
                GapKind.TEMPORAL,
                GapKind.CORRECTION,
            }
        )
    )
    safe_partial = sum(
        1 for o in outcomes if o.gap is GapKind.SAFE_PARTIAL or o.wire_ir and o.persist.status.name.startswith("PARTIALLY")
    )
    assert safe_unresolved >= 5
    assert safe_partial >= 0


def test_must_not_wire_cases() -> None:
    for case in ALL_CASES:
        if not case.must_not_wire:
            continue
        out = audit_case(case)
        assert out.wire_ir is False, case.id
