"""Claim-aware write outcome — committed means a semantic claim was materialized."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.clock import FixedClock
from pke.application.ingest import IngestService
from pke.application.results import (
    ClaimTally,
    IngestResult,
    IngestStatus,
    ingest_status_from_tally,
)
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticClaimKind,
    SemanticClaimOrigin,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.product.api.v1.dtos import ApiOperationOutcome
from pke.product.conversation.presenter import _present_ingest
from pke.resolution.context import PersonalContext
from pke.persist import open_sqlite_uow
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = "u-claim-status") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-claim-status") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _named(text: str) -> SemanticEntityMention:
    return SemanticEntityMention(
        text=text, kind_hint="thing", reference_kind="named", confidence=1.0
    )


def _ingest(proposal: SemanticProposal, db: Path):
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    svc = IngestService(
        FakeInterpreter({proposal.raw_input: outcome.ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    return svc.ingest(proposal.raw_input, _user(), _session()), outcome


def test_all_claims_committed_returns_committed() -> None:
    tally = ClaimTally(received=2, valid=2, committed=2, deferred=0, rejected=0)
    assert ingest_status_from_tally(tally, interpreter_claims=True) is IngestStatus.COMMITTED


def test_some_claims_committed_returns_partial() -> None:
    tally = ClaimTally(received=3, valid=2, committed=2, deferred=1, rejected=0)
    assert ingest_status_from_tally(tally, interpreter_claims=True) is IngestStatus.PARTIAL


def test_assumed_rejected_with_materialized_facts_is_committed() -> None:
    tally = ClaimTally(received=3, valid=2, committed=1, deferred=0, rejected=1)
    assert ingest_status_from_tally(tally, interpreter_claims=True) is IngestStatus.COMMITTED


def test_zero_committed_deferred_does_not_return_committed() -> None:
    tally = ClaimTally(received=1, valid=0, committed=0, deferred=1, rejected=0)
    status = ingest_status_from_tally(tally, interpreter_claims=True)
    assert status is IngestStatus.DEFERRED
    assert status is not IngestStatus.COMMITTED


def test_zero_committed_unsupported_does_not_return_committed() -> None:
    tally = ClaimTally(received=1, valid=0, committed=0, deferred=0, rejected=1)
    status = ingest_status_from_tally(tally, interpreter_claims=True)
    assert status is IngestStatus.UNSUPPORTED
    assert status is not IngestStatus.COMMITTED


def test_legacy_path_without_interpreter_claims_stays_committed() -> None:
    tally = ClaimTally(received=0, valid=0, committed=0, deferred=0, rejected=0)
    assert ingest_status_from_tally(tally, interpreter_claims=False) is IngestStatus.COMMITTED


def test_entity_reuse_alone_does_not_count_as_claim_commit(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "claim-reuse.db")
    luna = _named("Luna")
    seed = SemanticProposal(
        raw_input="seed luna",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=luna,
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=luna,
                predicate="profession",
                value_text="mascot",
                origin=SemanticClaimOrigin.EXPLICIT,
                confidence=1.0,
            )
        ],
        confidence=1.0,
    )
    first, _ = _ingest(seed, db)
    assert first.status is IngestStatus.COMMITTED
    deferred = SemanticProposal(
        raw_input="derived only",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=luna,
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=luna,
                predicate="fur color",
                value_text="branco",
                origin=SemanticClaimOrigin.DERIVED,
                confidence=1.0,
            )
        ],
        confidence=1.0,
    )
    second, _ = _ingest(deferred, db)
    assert second.claims.received == 1
    assert second.claims.committed == 0
    assert second.claims.deferred == 1
    assert len(second.bound_entity_ids) >= 1
    assert second.status is not IngestStatus.COMMITTED
    assert second.status is IngestStatus.DEFERRED


def test_presenter_receives_truthful_write_status() -> None:
    result = IngestResult(
        status=IngestStatus.DEFERRED,
        raw_text="x",
        claims=ClaimTally(received=1, valid=0, committed=0, deferred=1, rejected=0),
    )
    response = _present_ingest(
        result,
        conversation_id="c1",
        client_request_id=None,
        request_id=None,
        entity_label=lambda *_a: None,
        user_id="u",
        debug=None,
    )
    assert response.data is not None
    assert response.data["status"] == "deferred"
    assert response.data["claims"]["committed"] == 0
    assert response.operation is not None
    assert response.operation.outcome is ApiOperationOutcome.DEFERRED
    assert response.operation.outcome is not ApiOperationOutcome.COMMITTED
    assert "Entendi." != response.text
    assert "guardar" in response.text
