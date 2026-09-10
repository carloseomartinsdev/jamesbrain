"""I11.9-R — closure verification (temporal UNKNOWN matrix + discrimination).

AskStatus contract under test:
- ANSWERED means query execution completed, not proposition false.
- COUNT=0 with temporal_membership_unknown is NOT a complete negative.
- NO_RESULTS applies only when temporal completeness is COMPLETE and no indeterminate contributors.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pke.application import AskService, AskStatus, FixedClock, IngestService, IngestStatus
from pke.domain import ConceptRef, EventStatus, UserContext
from pke.interpretation import (
    EntityMention,
    FakeInterpreter,
    IngestIntent,
    IngestIR,
    IrEvent,
    IrQueryTime,
    IrTime,
    QueryIR,
    QuerySpec,
)
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.query.results import TemporalCompleteness
from pke.query.spec import AggregateKind
from pke.resolution import PersonalContext
from pke.application import SessionContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW, _corolla, _service
from tests.query_semantic import fixtures as qf
from tests.query_semantic.test_compositional_query import (
    _run_query,
    _semantic_ask,
    _semantic_service,
    _user,
)
from tests.integration.test_ask import _session as ingest_session

FORTALEZA = ZoneInfo("America/Fortaleza")
AUGUST_QUERY_TIME = IrQueryTime(
    original_text="agosto",
    date_from=dt.date(2026, 8, 1),
    date_to=dt.date(2026, 9, 1),
)

pytestmark = pytest.mark.usefixtures("_catalog")


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _august_count_ir(raw: str, *, corolla: bool = False) -> QueryIR:
    entities = [_corolla()] if corolla else []
    return QueryIR(
        raw_input=raw,
        query=QuerySpec(
            intent="aggregate",
            entities=entities,
            entity_association="subject" if corolla else None,
            actions=[ConceptRef(key="action.replace")],
            aggregate="count",
            time=AUGUST_QUERY_TIME,
        ),
    )


def _replace_clutch_ir(raw: str, *, month: int, year: int = 2026) -> IngestIR:
    day = 15
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=raw,
        domains=[ConceptRef(key="domain.vehicle")],
        entities_mentioned=[_corolla()],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.replace"),
            status=EventStatus.COMPLETED,
            time=IrTime(
                original_text="agosto" if month == 8 else "setembro",
                date=dt.date(year, month, day),
            ),
            facts=[],
        ),
    )


def _partial_past_ir() -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input="Troquei a embreagem.",
        domains=[ConceptRef(key="domain.vehicle")],
        event=IrEvent(
            type=ConceptRef(key="event.maintenance"),
            action=ConceptRef(key="action.replace"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text=""),
            facts=[],
        ),
    )


def _ask_count(db: Path, ingest_ir: IngestIR, ingest_raw: str, query_ir: QueryIR) -> tuple:
    user = UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)
    session = SessionContext(personal=PersonalContext(user_id="u1"))
    ontology = OntologyRegistry.with_core_seeds()
    svc = IngestService(
        FakeInterpreter({ingest_raw: ingest_ir}),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    assert svc.ingest(ingest_raw, user, session).status is IngestStatus.COMMITTED
    ask = AskService(
        FakeInterpreter({query_ir.raw_input: query_ir}),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    return ask.ask(query_ir.raw_input, user, session)


# --- U1–U4 temporal UNKNOWN matrix ---


def test_u1_partial_past_august_query_is_unknown_not_complete_negative(tmp_path: Path) -> None:
    """Known past event, calendar unknown — August range → temporal UNKNOWN."""
    db = fresh_db_path(tmp_path, "u1.db")
    result = _run_query(
        db,
        {qf.ingest_replace_clutch().raw_input: qf.ingest_replace_clutch()},
        qf.query_clutch_august(),
    )
    qr = result.query_result
    assert qr is not None
    assert qr.temporal_membership_unknown is True
    assert qr.temporal_completeness is TemporalCompleteness.PARTIAL
    assert qr.aggregate is not None
    assert qr.aggregate.value == 0


def test_u2_unknown_must_not_collapse_to_no_results_or_false(tmp_path: Path) -> None:
    """UNKNOWN case must not become NO_RESULTS (false) nor COMPLETE negative."""
    db = fresh_db_path(tmp_path, "u2.db")
    result = _run_query(
        db,
        {qf.ingest_replace_clutch().raw_input: qf.ingest_replace_clutch()},
        qf.query_clutch_august(),
    )
    assert result.status is AskStatus.ANSWERED
    assert result.status is not AskStatus.NO_RESULTS
    qr = result.query_result
    assert qr is not None
    assert qr.temporal_membership_unknown is True
    assert qr.temporal_completeness is not TemporalCompleteness.COMPLETE


def test_u3_known_september_august_query_is_no_match(tmp_path: Path) -> None:
    """Event explicitly in September — August query → complete NO_MATCH."""
    db = fresh_db_path(tmp_path, "u3.db")
    raw_ingest = "Troquei a embreagem do Corolla em setembro."
    raw_query = "Troquei a embreagem do Corolla em agosto?"
    result = _ask_count(
        db,
        _replace_clutch_ir(raw_ingest, month=9),
        raw_ingest,
        _august_count_ir(raw_query, corolla=True),
    )
    qr = result.query_result
    assert qr is not None
    assert qr.aggregate is not None
    assert qr.aggregate.value == 0
    assert qr.temporal_membership_unknown is False
    assert qr.temporal_completeness is TemporalCompleteness.COMPLETE
    assert result.status is AskStatus.NO_RESULTS


def test_u4_known_august_august_query_is_match(tmp_path: Path) -> None:
    """Event explicitly in August — August query → MATCH."""
    db = fresh_db_path(tmp_path, "u4.db")
    raw_ingest = "Troquei a embreagem do Corolla em agosto."
    raw_query = "Troquei a embreagem do Corolla em agosto?"
    result = _ask_count(
        db,
        _replace_clutch_ir(raw_ingest, month=8),
        raw_ingest,
        _august_count_ir(raw_query, corolla=True),
    )
    qr = result.query_result
    assert qr is not None
    assert qr.aggregate is not None
    assert qr.aggregate.value == 1
    assert qr.temporal_membership_unknown is False
    assert result.status is AskStatus.ANSWERED


def test_is_zero_count_not_complete_negative_when_temporal_unknown() -> None:
    """Formal: count=0 + temporal_membership_unknown → NOT a complete negative."""
    from pke.application.ask import _is_empty
    from pke.query.results import AggregateResult, QueryPlan, QueryResult
    from pke.query.spec import AggregateKind, FactVersionPolicy, HierarchyMode, ResolvedQuerySpec, SortKey

    spec = ResolvedQuerySpec(user_id="u1", aggregate=AggregateKind.COUNT)
    result = QueryResult(
        matched_count=0,
        plan=QueryPlan(
            sets=["events"],
            filters={},
            expanded_event_type_ids=[],
            expanded_action_ids=[],
            version_policy=FactVersionPolicy.CURRENT,
            aggregation=AggregateKind.COUNT,
            ordering=SortKey.EVENT_TIME_DESC,
            hierarchy=HierarchyMode.EXACT,
        ),
        aggregate=AggregateResult(kind=AggregateKind.COUNT, value=0),
        temporal_completeness=TemporalCompleteness.PARTIAL,
        temporal_membership_unknown=True,
    )
    assert _is_empty(spec, result) is False


# --- Discrimination A/B/C ---


def test_discrimination_a_oil_not_clutch(tmp_path: Path) -> None:
    """Same vehicle, different object/action → NO_MATCH."""
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime

    db = fresh_db_path(tmp_path, "d_a.db")
    ingest = qf.ingest_replace_oil_corolla()
    query = SemanticProposal(
        raw_input="Troquei o óleo do Corolla?",
        utterance_kind="query",
        object=SemanticEntityMention(text="óleo"),
        entities_mentioned=[SemanticEntityMention(text="Corolla", kind_hint="vehicle")],
        action_expression="troquei o óleo",
        event_expression="troquei o óleo do Corolla",
        temporal=SemanticTime(original_text="", occurrence_aspect="happened"),
        primitive_hint="event",
    )
    user = _user()
    session = ingest_session()
    svc = _semantic_service(db, {ingest.raw_input: ingest})
    assert svc.ingest(ingest.raw_input, user, session).status is IngestStatus.COMMITTED
    result = _semantic_ask(db, {query.raw_input: query}).ask(query.raw_input, user, session)
    assert result.status is AskStatus.NO_RESULTS


def test_discrimination_b_civic_not_corolla(tmp_path: Path) -> None:
    """Same object, different vehicle context → NO_MATCH (only Corolla persisted)."""
    from pke.interpretation.semantic.models import SemanticEntityMention

    db = fresh_db_path(tmp_path, "d_b.db")
    ingest = qf.ingest_replace_clutch_corolla()
    query = qf.query_replace_clutch_corolla()
    query = query.model_copy(
        update={
            "raw_input": "Troquei a embreagem do Civic?",
            "entities_mentioned": [SemanticEntityMention(text="Civic", kind_hint="vehicle")],
            "event_expression": "troquei a embreagem do Civic",
        }
    )
    user = _user()
    session = ingest_session()
    svc = _semantic_service(db, {ingest.raw_input: ingest})
    assert svc.ingest(ingest.raw_input, user, session).status is IngestStatus.COMMITTED
    result = _semantic_ask(db, {query.raw_input: query}).ask(query.raw_input, user, session)
    assert result.status is AskStatus.NO_RESULTS


def test_discrimination_c_corolla_clutch_match(tmp_path: Path) -> None:
    """Same object + same vehicle → MATCH."""
    db = fresh_db_path(tmp_path, "d_c.db")
    ingest = qf.ingest_replace_clutch_corolla()
    query = qf.query_replace_clutch_corolla()
    query = query.model_copy(update={"raw_input": "Troquei a embreagem do Corolla?"})
    user = _user()
    session = ingest_session()
    svc = _semantic_service(db, {ingest.raw_input: ingest})
    assert svc.ingest(ingest.raw_input, user, session).status is IngestStatus.COMMITTED
    result = _semantic_ask(db, {query.raw_input: query}).ask(query.raw_input, user, session)
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.matched_count >= 1
