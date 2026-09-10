"""I11.14 — Query symmetry probes (no new query capabilities)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application import AskService, AskStatus, FixedClock, IngestService, IngestStatus
from pke.interpretation import FakeInterpreter, IngestIR, QueryIR
from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from tests.attribute_query import fixtures as aqf
from tests.generalization_ingest.fixtures import benchmark_session
from tests.integration.test_ask import _session as ingest_session
from tests.integration.test_ingest import NOW
from tests.semantic_audit.cases import QUERY_SAFETY_CASES, cp3_corolla_silver, cp6_employment, cp10_corolla_broken
from tests.semantic_resolution.fixtures import pr3_employment
from pke.domain.value_objects import UserContext


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _to_ir(proposal: SemanticProposal) -> IngestIR | QueryIR:
    if proposal.utterance_kind == "query":
        outcome = proposal_to_query_ir(proposal)
        assert outcome.query_ir is not None, (outcome.status, outcome.notes, outcome.primitive)
        return outcome.query_ir
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert isinstance(outcome.ir, IngestIR)
    return outcome.ir


def test_query_safety_routing() -> None:
    for case in QUERY_SAFETY_CASES:
        proposal = case.factory()  # type: ignore[operator]
        routed, _ = route_primitive(proposal)
        assert routed is case.expected_primitive


def test_attribute_write_read_symmetry(tmp_path: Path) -> None:
    write = aqf.aq1_write()
    query = aqf.aq1_query()
    user = UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)
    session = ingest_session()
    db = tmp_path / "sym.db"
    ontology = OntologyRegistry.with_core_seeds()
    svc = IngestService(
        FakeInterpreter({write.raw_input: _to_ir(write)}),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    assert svc.ingest(write.raw_input, user, session).status is IngestStatus.COMMITTED
    ask = AskService(
        FakeInterpreter({query.raw_input: _to_ir(query)}),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    result = ask.ask(query.raw_input, user, session)
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.attribute_status == "known_single"


def test_query_paths_are_read_only(tmp_path: Path) -> None:
    """Ask must not create Attribute/State rows."""
    write = cp3_corolla_silver()
    query = aqf.aq1_query()
    user = UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)
    session = ingest_session()
    db = tmp_path / "ro.db"
    ontology = OntologyRegistry.with_core_seeds()
    svc = IngestService(
        FakeInterpreter({write.raw_input: _to_ir(write)}),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    assert svc.ingest(write.raw_input, user, session).status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        before = sum(len(uow.attributes.for_entity(user.user_id, e.id)) for e in uow.entities.all_for_user(user.user_id))
    ask = AskService(
        FakeInterpreter({query.raw_input: _to_ir(query)}),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    ask.ask(query.raw_input, user, session)
    with open_sqlite_uow(db) as uow:
        after = sum(len(uow.attributes.for_entity(user.user_id, e.id)) for e in uow.entities.all_for_user(user.user_id))
    assert before == after


def test_state_and_relation_query_intents_distinct() -> None:
    state_q = cp10_corolla_broken().model_copy(update={"utterance_kind": "query"})
    rel_q = pr3_employment().model_copy(update={"raw_input": "João trabalha na Acme?", "utterance_kind": "query"})
    assert route_primitive(state_q)[0] is PrimitiveKind.STATE
    assert route_primitive(rel_q)[0] is PrimitiveKind.RELATION
