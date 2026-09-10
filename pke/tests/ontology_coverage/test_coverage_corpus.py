"""I11.11 — controlled ontology coverage expansion corpus (OC1–OC6 + PX + query)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application import FixedClock, IngestService, IngestStatus
from pke.interpretation import FakeInterpreter, IngestIR
from pke.interpretation.semantic.models import PrimitiveKind, ResolutionStatus
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import QueryResolutionStatus, proposal_to_query_ir
from pke.interpretation.semantic.resolver import resolve_concepts
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.semantic.sense import SemanticSense
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_uow
from tests.generalization_ingest.fixtures import benchmark_session, benchmark_user, fresh_db_path
from tests.integration.test_ingest import NOW
from tests.ontology_coverage import fixtures as oc
from tests.query_semantic import fixtures as qf
from tests.semantic_resolution.fixtures import px1_installation_service, px2_facilities_new


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _concepts(proposal):
    primitive, _ = route_primitive(proposal)
    return primitive, resolve_concepts(proposal, primitive)


@pytest.mark.parametrize(
    ("factory", "expected_action", "forbidden", "expected_sense"),
    [
        (oc.oc1_installed_ac, "action.install", {"action.replace", "action.maintain"}, SemanticSense.INSTALL),
        (oc.oc2_technician_installed_ac, "action.install", {"action.replace"}, SemanticSense.INSTALL),
        (oc.oc3_installed_program, "action.install", {"action.replace"}, SemanticSense.INSTALL),
        (oc.oc4_replaced_ac, "action.replace", {"action.install"}, SemanticSense.REPLACE_PHYSICAL),
        (oc.oc5_repaired_ac, "action.maintain", {"action.install", "action.replace"}, None),
    ],
)
def test_oc_positive_and_contrast(factory, expected_action, forbidden, expected_sense) -> None:
    proposal = factory()
    primitive, concepts = _concepts(proposal)
    assert primitive is PrimitiveKind.EVENT
    assert concepts.action == expected_action
    assert concepts.resolution_status is ResolutionStatus.RESOLVED
    assert concepts.ontology_gap is False
    for bad in forbidden:
        assert concepts.action != bad
    if expected_sense is not None:
        assert concepts.recognized_sense == expected_sense.value


def test_oc6_facilities_not_install() -> None:
    proposal = oc.oc6_facilities_new()
    primitive, concepts = _concepts(proposal)
    assert primitive is PrimitiveKind.ATTRIBUTE
    assert concepts.action is None
    assert concepts.action != "action.install"
    assert concepts.recognized_sense == SemanticSense.FACILITIES.value
    assert concepts.unresolved or concepts.ontology_gap


def test_px1_now_install() -> None:
    proposal = px1_installation_service()
    _, concepts = _concepts(proposal)
    assert concepts.action == "action.install"
    assert concepts.recognized_sense == SemanticSense.INSTALL.value


def test_px2_still_not_install() -> None:
    proposal = px2_facilities_new()
    _, concepts = _concepts(proposal)
    assert concepts.action != "action.install"
    assert concepts.recognized_sense == SemanticSense.FACILITIES.value


def test_false_canonicalization_zero_on_oc_matrix() -> None:
    rows = [
        (oc.oc1_installed_ac(), "action.install"),
        (oc.oc2_technician_installed_ac(), "action.install"),
        (oc.oc3_installed_program(), "action.install"),
        (oc.oc4_replaced_ac(), "action.replace"),
        (oc.oc5_repaired_ac(), "action.maintain"),
    ]
    false = 0
    for proposal, expected in rows:
        _, concepts = _concepts(proposal)
        if concepts.action != expected:
            false += 1
    _, concepts6 = _concepts(oc.oc6_facilities_new())
    if concepts6.action == "action.install":
        false += 1
    assert false == 0


def test_coverage_metrics_focused_corpus() -> None:
    """Focused sample metrics — not global percentages."""
    cases = [
        oc.oc1_installed_ac(),
        oc.oc2_technician_installed_ac(),
        oc.oc3_installed_program(),
        oc.oc4_replaced_ac(),
        oc.oc5_repaired_ac(),
        oc.oc6_facilities_new(),
    ]
    canonical = 0
    safe_abstention = 0
    ontology_gap = 0
    false_can = 0
    expected = {
        "Instalei o ar-condicionado.": "action.install",
        "O técnico instalou o ar-condicionado.": "action.install",
        "Instalei um programa.": "action.install",
        "Troquei o ar-condicionado.": "action.replace",
        "Consertei o ar-condicionado.": "action.maintain",
        "As instalações da empresa são novas.": None,
    }
    for proposal in cases:
        _, concepts = _concepts(proposal)
        want = expected[proposal.raw_input]
        if want is None:
            if concepts.action is None and (concepts.unresolved or concepts.ontology_gap):
                safe_abstention += 1
                if concepts.ontology_gap:
                    ontology_gap += 1
            elif concepts.action is not None:
                false_can += 1
        elif concepts.action == want:
            canonical += 1
        else:
            false_can += 1
    assert canonical == 5
    assert safe_abstention == 1
    assert ontology_gap >= 1
    assert false_can == 0


def test_query_symmetry_install(tmp_path: Path) -> None:
    write = oc.oc1_installed_ac()
    outcome = proposal_to_canonical_ir(write)
    assert outcome.ir is not None
    assert outcome.ir.event is not None
    assert outcome.ir.event.action is not None
    assert outcome.ir.event.action.key == "action.install"

    q = qf.query_install_ac()
    q_out = proposal_to_query_ir(q)
    assert q_out.status is QueryResolutionStatus.RESOLVED
    assert q_out.query_ir is not None
    assert q_out.query_ir.query.actions
    assert q_out.query_ir.query.actions[0].key == "action.install"

    db = fresh_db_path(tmp_path, "oc_qsym.db")
    user = benchmark_user()
    svc = IngestService(
        FakeInterpreter({write.raw_input: outcome.ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    result = svc.ingest(write.raw_input, user, benchmark_session())
    assert result.status is IngestStatus.COMMITTED
