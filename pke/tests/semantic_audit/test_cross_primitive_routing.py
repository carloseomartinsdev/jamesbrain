"""I11.14 — Cross-primitive routing + false-collapse metrics."""

from __future__ import annotations

import pytest

from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from tests.semantic_audit.cases import ALL_CASES, MANDATORY_CASES, OPEN_CASES, QUERY_SAFETY_CASES
from tests.semantic_audit.harness import InformationLoss, audit_case


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


@pytest.mark.parametrize("case", MANDATORY_CASES, ids=[c.id for c in MANDATORY_CASES])
def test_cp_routing(case) -> None:
    out = audit_case(case)
    assert out.routed is case.expected_primitive, (
        f"{case.id}: expected {case.expected_primitive}, got {out.routed}; notes={out.notes}"
    )
    assert out.false_collapse is False
    for forbidden in case.forbid:
        assert out.routed is not forbidden


@pytest.mark.parametrize("case", OPEN_CASES, ids=[c.id for c in OPEN_CASES])
def test_open_routing(case) -> None:
    out = audit_case(case)
    assert out.routed is case.expected_primitive, (
        f"{case.id}: expected {case.expected_primitive}, got {out.routed}; notes={out.notes}"
    )
    assert out.false_collapse is False


@pytest.mark.parametrize("case", QUERY_SAFETY_CASES, ids=[c.id for c in QUERY_SAFETY_CASES])
def test_query_primitive_safety(case) -> None:
    out = audit_case(case)
    assert out.routed is case.expected_primitive
    assert out.false_collapse is False


def test_false_collapse_metrics_zero() -> None:
    metrics = {
        "EVENT_FALSE_STATE": 0,
        "EVENT_FALSE_RELATION": 0,
        "EVENT_FALSE_ATTRIBUTE": 0,
        "EVENT_FALSE_TYPE": 0,
        "STATE_FALSE_EVENT": 0,
        "STATE_FALSE_RELATION": 0,
        "STATE_FALSE_ATTRIBUTE": 0,
        "STATE_FALSE_TYPE": 0,
        "RELATION_FALSE_EVENT": 0,
        "RELATION_FALSE_STATE": 0,
        "RELATION_FALSE_ATTRIBUTE": 0,
        "RELATION_FALSE_TYPE": 0,
        "ATTRIBUTE_FALSE_EVENT": 0,
        "ATTRIBUTE_FALSE_STATE": 0,
        "ATTRIBUTE_FALSE_RELATION": 0,
        "ATTRIBUTE_FALSE_TYPE": 0,
        "TYPE_FALSE_EVENT": 0,
        "TYPE_FALSE_STATE": 0,
        "TYPE_FALSE_RELATION": 0,
        "TYPE_FALSE_ATTRIBUTE": 0,
    }
    for case in ALL_CASES + QUERY_SAFETY_CASES:
        out = audit_case(case)
        if out.false_collapse:
            key = f"{out.expected.value.upper()}_FALSE_{out.routed.value.upper()}"
            if key in metrics:
                metrics[key] += 1
            else:
                metrics[key] = 1
    assert all(v == 0 for v in metrics.values()), metrics


def test_false_canonicalization_zero() -> None:
    """Wrong primitive routing counts as false canonicalization for this audit."""
    false = sum(1 for c in ALL_CASES if audit_case(c).false_collapse)
    assert false == 0


def test_no_critical_information_loss_on_mandatory_persistable() -> None:
    critical = []
    for case in MANDATORY_CASES:
        out = audit_case(case)
        if out.information_loss is InformationLoss.CRITICAL and out.wire_ir:
            critical.append(case.id)
    assert critical == []


def test_schema_and_core_unchanged() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67
