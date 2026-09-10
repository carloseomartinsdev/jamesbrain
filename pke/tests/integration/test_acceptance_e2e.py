"""E2E offline da cadeia A → D1 → E → B → C → F e D2 isolado."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pke.application import (
    AskService,
    AskStatus,
    FixedClock,
    IngestService,
    IngestStatus,
    SessionContext,
)
from pke.domain import Money, UserContext
from pke.interpretation import FakeInterpreter
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.query.spec import FactVersionPolicy
from pke.resolution import PersonalContext
from tests.integration.test_ask import RAW_F, _query_ir
from tests.integration.test_ingest import RAW_A, RAW_B, RAW_C, RAW_D1, RAW_D2, RAW_E, ir_a, ir_b, ir_c, ir_d1, ir_d2, ir_d2_with_vehicle, ir_e

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "pke.db"


@pytest.fixture
def user() -> UserContext:
    return UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)


def _ingest(db_path: Path, ontology: OntologyRegistry, responses: dict[str, object]) -> IngestService:
    return IngestService(
        FakeInterpreter(responses),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db_path),
        FixedClock(NOW),
    )


def test_e2e_chain_a_d1_e_b_c_f(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = SessionContext(personal=PersonalContext(user_id="u1"))
    responses = {
        RAW_A: ir_a(),
        RAW_D1: ir_d1(),
        RAW_E: ir_e(),
        RAW_B: ir_b(),
        RAW_C: ir_c(),
        RAW_F: _query_ir(),
    }
    ingest = _ingest(db_path, ontology, responses)
    for raw in (RAW_A, RAW_D1, RAW_E, RAW_B, RAW_C):
        result = ingest.ingest(raw, user, session)
        assert result.status is IngestStatus.COMMITTED, raw

    ask = AskService(
        FakeInterpreter(responses),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db_path),
        FixedClock(NOW),
    )
    answered = ask.ask(RAW_F, user, session)
    assert answered.status is AskStatus.ANSWERED
    assert answered.query_result is not None
    assert answered.query_result.aggregate is not None
    assert answered.query_result.aggregate.value == Decimal("506.50")
    assert answered.query_result.aggregate.currency == "BRL"
    assert answered.resolved_spec is not None
    assert answered.resolved_spec.fact_version_policy is FactVersionPolicy.CURRENT

    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    amounts = []
    for fact_id in answered.query_result.aggregate.contributing_fact_ids:
        fact = next(item for item in graph.facts if item.id == fact_id)
        assert fact.superseded_at is None
        assert isinstance(fact.value, Money)
        amounts.append(fact.value.amount)
    assert sorted(amounts) == [Decimal("186.50"), Decimal("320")]
    for fact in graph.facts:
        if isinstance(fact.value, Money) and fact.value.amount == Decimal("180"):
            assert fact.id not in answered.query_result.aggregate.contributing_fact_ids


def test_e2e_d2_isolated_commits_temporally_incomplete(
    db_path: Path, ontology: OntologyRegistry, user: UserContext
) -> None:
    session = SessionContext(personal=PersonalContext(user_id="u1"))
    result = _ingest(db_path, ontology, {RAW_D2: ir_d2_with_vehicle()}).ingest(RAW_D2, user, session)
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization is not None
    assert not any(issue.code == "time.missing" for issue in result.issues)
    graph = open_sqlite_read_store(db_path).load_user_graph("u1")
    assert len(graph.events) == 1
    assert graph.events[0].temporal.kind.value == "partial"
