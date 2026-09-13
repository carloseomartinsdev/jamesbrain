"""I11.8 — partial canonicalization & persistability (PC1–PC6, PI1–PI4)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pke.application import FixedClock, IngestService, IngestStatus
from pke.interpretation import FakeInterpreter, IngestIR
from pke.interpretation.semantic.models import PrimitiveKind, ResolutionStatus
from pke.interpretation.semantic.persistability import PersistabilityStatus, assess_persistability
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.ontology import OntologyRegistry
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.persist import open_sqlite_uow
from tests.generalization_ingest.fixtures import benchmark_session, benchmark_user, fresh_db_path
from tests.semantic_resolution.fixtures import (
    ls1_installed_ac,
    ls3_installation_yesterday,
    pr2_fridge_broke,
    pr3_employment,
    px1_installation_service,
    sc3_open,
    sc4_replace_clutch,
    sc5_substitute_clutch,
)

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _ingest(proposal: SemanticProposal, db: Path) -> IngestStatus:
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    ir = outcome.ir
    assert isinstance(ir, IngestIR)
    user = benchmark_user()
    svc = IngestService(
        FakeInterpreter({proposal.raw_input: ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    result = svc.ingest(proposal.raw_input, user, benchmark_session())
    return result.status


def test_pc1_replace_clutch_canonical() -> None:
    proposal = sc4_replace_clutch()
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert outcome.ir.event is not None
    assert outcome.ir.event.action is not None
    assert outcome.ir.event.action.key == "action.replace"
    assessment = assess_persistability(outcome.result)
    assert assessment.wire_allowed
    assert assessment.status in {
        PersistabilityStatus.FULLY_RESOLVED,
        PersistabilityStatus.PARTIALLY_RESOLVED_PERSISTABLE,
    }


def test_pc2_substitute_clutch_same_semantics() -> None:
    outcome = proposal_to_canonical_ir(sc5_substitute_clutch())
    assert outcome.ir is not None
    assert outcome.ir.event is not None
    assert outcome.ir.event.action is not None
    assert outcome.ir.event.action.key == "action.replace"


def test_pc3_door_open_event_not_state() -> None:
    proposal = SemanticProposal(
        raw_input="A porta abriu.",
        subject=SemanticEntityMention(text="porta", kind_hint="thing"),
        event_expression="abriu",
        change_semantics=True,
        primitive_hint="event",
        temporal=SemanticTime(original_text="", occurrence_aspect="happened"),
    )
    result = resolve_proposal(proposal)
    assert result.primitive is PrimitiveKind.EVENT
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert outcome.ir.event is not None
    assert outcome.ir.state is None


def test_pc4_fridge_broke_event_occurrence() -> None:
    outcome = proposal_to_canonical_ir(pr2_fridge_broke())
    assert outcome.ir is not None
    assert outcome.ir.event is not None
    assert outcome.ir.state is None


def test_pc4_fridge_broke_persists(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "pc4")
    status = _ingest(pr2_fridge_broke(), db)
    assert status is IngestStatus.COMMITTED


def test_pc5_install_no_false_canonicalization() -> None:
    proposal = px1_installation_service()
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert outcome.ir.event is not None
    assert outcome.ir.event.action is not None
    assert outcome.ir.event.action.key == "action.install"
    concepts = outcome.result.concepts
    assert concepts.recognized_sense == "install"
    assert concepts.action == "action.install"
    assert concepts.action != "action.replace"
    assert concepts.ontology_gap is False


def test_pc6_installation_yesterday_no_replace() -> None:
    proposal = ls3_installation_yesterday()
    outcome = proposal_to_canonical_ir(proposal)
    concepts = outcome.result.concepts
    assert concepts.action == "action.install"
    assert concepts.action != "action.replace"
    if outcome.ir is not None and outcome.ir.event and outcome.ir.event.action:
        assert outcome.ir.event.action.key == "action.install"
        assert outcome.ir.event.action.key != "action.replace"


def test_pi1_relation_unresolved_not_materialized() -> None:
    """Complete link with no CORE alias becomes relation.learned.* (ADR learned relations).

    I11.8 originally expected ir is None for unmatched "trabalha". That contradicted
    the living unmatched-link contract (`test_unmatched_link_learns_extended_type`).
    Incomplete links still do not materialize — see PI3 and missing-endpoint paths.
    """
    proposal = SemanticProposal(
        raw_input="João — Acme",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="Acme", kind_hint="organization"),
        relation_expression="trabalha",
        link_semantics=True,
        primitive_hint="relation",
    )
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.learned.trabalha"


def test_pi2_state_invalid_value_not_materialized() -> None:
    proposal = SemanticProposal(
        raw_input="A porta está estranha.",
        subject=SemanticEntityMention(text="porta", kind_hint="thing"),
        state_expression="estranha_sem_conceito",
        condition_semantics=True,
        primitive_hint="state",
    )
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is None


def test_pi3_event_no_anchor_not_materialized() -> None:
    proposal = SemanticProposal(
        raw_input="Algo aconteceu.",
        change_semantics=False,
        primitive_hint="event",
        temporal=SemanticTime(original_text=""),
    )
    assessment = assess_persistability(resolve_proposal(proposal))
    assert not assessment.wire_allowed


def test_pi4_ambiguous_primitive_not_materialized() -> None:
    proposal = SemanticProposal(
        raw_input="Passei no São Luiz.",
        action_expression="passei",
        change_semantics=True,
        primitive_hint="unknown",
        temporal=SemanticTime(original_text="", occurrence_aspect="happened"),
    )
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.result.concepts.resolution_status in {
        ResolutionStatus.AMBIGUOUS,
        ResolutionStatus.UNRESOLVED,
        ResolutionStatus.BLOCKED,
    }
    assert outcome.ir is None


def test_pc1_pc2_ingest_committed(tmp_path: Path) -> None:
    for proposal in (sc4_replace_clutch(), sc5_substitute_clutch()):
        db = fresh_db_path(tmp_path, proposal.raw_input[:12])
        assert _ingest(proposal, db) is IngestStatus.COMMITTED


def test_state_open_canonical_ir_regression() -> None:
    outcome = proposal_to_canonical_ir(sc3_open())
    assert outcome.ir is not None
    assert outcome.ir.state is not None
    assert outcome.ir.state.value.key == "state.value.open"


def test_relation_employment_canonical_ir_regression() -> None:
    outcome = proposal_to_canonical_ir(pr3_employment())
    assert outcome.ir is not None
    assert outcome.ir.relation is not None


def test_install_ls1_persistable_with_action_install() -> None:
    outcome = proposal_to_canonical_ir(ls1_installed_ac())
    assert outcome.ir is not None
    assert outcome.ir.event is not None
    assert outcome.ir.event.action is not None
    assert outcome.ir.event.action.key == "action.install"
