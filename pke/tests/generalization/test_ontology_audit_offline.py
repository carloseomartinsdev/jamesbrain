"""Testes offline da auditoria ontológica I11.1."""

from __future__ import annotations

from pathlib import Path

from pke.ontology.registry import OntologyRegistry

from tests.generalization.cases import DEVELOPMENT_CASES
from tests.generalization.ontology_audit import (
    CoverageClass,
    benchmark_demand_coverage,
    compute_coverage_metrics,
    inventory_core,
    run_audit,
)
from tests.generalization.semantic_demand import CASE_SEMANTIC_DEMAND


def test_all_development_cases_have_demand() -> None:
    for case in DEVELOPMENT_CASES:
        assert case.case_id in CASE_SEMANTIC_DEMAND, case.case_id


def test_core_inventory_counts() -> None:
    inv = inventory_core(OntologyRegistry.with_core_seeds())
    assert inv["total"] == 67
    assert inv["by_kind"]["entity"] == 10
    assert inv["by_kind"]["event"] == 8
    assert inv["by_kind"]["action"] == 7
    assert inv["by_kind"].get("state_dimension", 0) == 8
    assert inv["by_kind"].get("state_value", 0) == 10


def test_action_replace_is_direct() -> None:
    cov = benchmark_demand_coverage(OntologyRegistry.with_core_seeds())
    replace = next(c for c in cov if c.need_id == "need.action.replace")
    assert replace.classification is CoverageClass.DIRECT


def test_install_is_direct() -> None:
    cov = benchmark_demand_coverage(OntologyRegistry.with_core_seeds())
    install = next(c for c in cov if c.need_id == "need.action.install")
    assert install.classification is CoverageClass.DIRECT


def test_coverage_metrics_bounds() -> None:
    cov = benchmark_demand_coverage(OntologyRegistry.with_core_seeds())
    m = compute_coverage_metrics(cov)
    assert 0 <= m["overall_concept_coverage"] <= 1
    assert m["representation_gaps"] >= 1


def test_run_audit_from_baseline_json() -> None:
    path = Path(__file__).resolve().parents[2] / "docs" / "reports" / "I11-GENERALIZATION-BASELINE.json"
    if not path.is_file():
        return
    audit = run_audit(path)
    assert audit["metrics"]["overall_concept_coverage"] > 0
    assert audit["inventory"]["total"] > 0
