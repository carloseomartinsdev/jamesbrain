"""Testes determinísticos do harness ingest-path (offline, sem LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.ontology import OntologyRegistry

from tests.generalization_ingest.cases import DETERMINISTIC_TEMPORAL_IDS, QUERY_CASES, TEMPORAL_CASES
from tests.generalization_ingest.evaluator import IngestPathEvaluator


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    return tmp_path / "ingest-bench"


@pytest.mark.parametrize("case_id", sorted(DETERMINISTIC_TEMPORAL_IDS))
def test_deterministic_temporal(case_id: str, ontology: OntologyRegistry, work_dir: Path) -> None:
    case = next(c for c in TEMPORAL_CASES if c.case_id == case_id)
    outcome = IngestPathEvaluator(ontology, work_dir).run_deterministic_temporal(case)
    assert outcome.knowledge_success, outcome.temporal_fails


@pytest.mark.parametrize("case", QUERY_CASES, ids=lambda c: c.case_id)
def test_deterministic_query(case, ontology: OntologyRegistry, work_dir: Path) -> None:
    outcome = IngestPathEvaluator(ontology, work_dir).run_query_case(case)
    assert outcome.query_success, outcome.query_fails
