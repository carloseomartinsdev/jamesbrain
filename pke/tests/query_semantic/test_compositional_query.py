"""I11.9 — compositional semantic query resolution & retrieval."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application import (
    AskService,
    AskStatus,
    FixedClock,
    IngestService,
    IngestStatus,
    SessionContext,
)
from pke.interpretation import FakeInterpreter, IngestIR, QueryIR
from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import (
    QueryResolutionStatus,
    proposal_to_query_ir,
)
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.query.results import TemporalCompleteness
from pke.query.spec import AggregateKind
from tests.generalization_ingest.fixtures import benchmark_session, benchmark_user, fresh_db_path
from tests.integration.test_ask import _ask, _ingest
from pke.domain import UserContext
from tests.integration.test_ask import _session as ingest_session
from tests.integration.test_ingest import NOW, _service
from tests.query_semantic import fixtures as qf

pytestmark = pytest.mark.usefixtures("_catalog")


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _to_ir(proposal: SemanticProposal) -> IngestIR | QueryIR:
    if proposal.utterance_kind == "query":
        outcome = proposal_to_query_ir(proposal)
        assert outcome.query_ir is not None, outcome.notes
        return outcome.query_ir
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, outcome.failure_stage
    assert isinstance(outcome.ir, IngestIR)
    return outcome.ir


def _semantic_service(db: Path, mapping: dict[str, SemanticProposal]):
    responses = {raw: _to_ir(prop) for raw, prop in mapping.items()}
    ontology = OntologyRegistry.with_core_seeds()
    return IngestService(
        FakeInterpreter(responses),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )


def _semantic_ask(db: Path, mapping: dict[str, SemanticProposal]) -> AskService:
    responses = {raw: _to_ir(prop) for raw, prop in mapping.items()}
    ontology = OntologyRegistry.with_core_seeds()
    store = open_sqlite_read_store(db)
    return AskService(
        FakeInterpreter(responses),  # type: ignore[arg-type]
        ontology,
        store,
        FixedClock(NOW),
    )


def _resolve_event(proposal: SemanticProposal):
    return proposal_to_query_ir(proposal)


def _user() -> UserContext:
    return UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)


def _run_query(db: Path, ingest_map: dict[str, SemanticProposal], query: SemanticProposal):
    user = _user()
    session = ingest_session()
    svc = _semantic_service(db, ingest_map)
    for raw in ingest_map:
        assert svc.ingest(raw, user, session).status is IngestStatus.COMMITTED
    ask = _semantic_ask(db, {query.raw_input: query})
    return ask.ask(query.raw_input, user, session)


# --- resolution unit matrix ---


def test_q1_action_object_without_event_type() -> None:
    outcome = _resolve_event(qf.query_replace_clutch())
    assert outcome.status is QueryResolutionStatus.RESOLVED
    assert outcome.query_ir is not None
    q = outcome.query_ir.query
    assert q.actions and q.actions[0].key == "action.replace"
    assert q.event_types == [] or q.event_types[0].key in {
        "event.maintenance",
        "event.vehicle_maintenance",
    }


def test_q4_query_no_event_type_filter() -> None:
    outcome = _resolve_event(qf.query_replace_clutch_no_event_type())
    assert outcome.status is QueryResolutionStatus.RESOLVED
    assert outcome.query_ir is not None
    assert outcome.query_ir.query.actions
    assert outcome.query_ir.query.actions[0].key == "action.replace"


def test_q10_install_resolves_action() -> None:
    outcome = _resolve_event(qf.query_install_ac())
    assert outcome.status is QueryResolutionStatus.RESOLVED
    assert outcome.query_ir is not None
    assert outcome.query_ir.query.actions
    assert outcome.query_ir.query.actions[0].key == "action.install"


def test_q11_exchange_idea_not_replace() -> None:
    outcome = _resolve_event(qf.query_exchange_idea())
    assert outcome.status in {
        QueryResolutionStatus.SAFE_UNRESOLVED,
        QueryResolutionStatus.INSUFFICIENT,
    }
    assert outcome.query_ir is None


def test_q12_ambiguous_pass_abstains() -> None:
    outcome = _resolve_event(qf.query_ambiguous_pass())
    assert outcome.status is QueryResolutionStatus.SAFE_AMBIGUOUS
    assert outcome.query_ir is None


def test_q8_state_query_routes_state() -> None:
    outcome = _resolve_event(qf.query_door_open())
    assert outcome.status is QueryResolutionStatus.RESOLVED
    assert outcome.query_ir is not None
    assert outcome.query_ir.query.intent == "state"
    assert outcome.query_ir.query.state_values


def test_q9_relation_query_routes_relation() -> None:
    outcome = _resolve_event(qf.query_employment())
    assert outcome.status is QueryResolutionStatus.RESOLVED
    assert outcome.query_ir is not None
    assert outcome.query_ir.query.intent == "relation"
    assert outcome.query_ir.query.relation_types


def test_q7_temporal_maps_august_range() -> None:
    outcome = _resolve_event(qf.query_clutch_august())
    assert outcome.status is QueryResolutionStatus.RESOLVED
    assert outcome.query_ir is not None
    assert outcome.query_ir.query.time is not None
    assert outcome.query_ir.query.time.date_from is not None
    assert outcome.query_ir.query.aggregate == "count"


# --- E2E retrieval matrix ---


def test_e2e_q1_match(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "q1.db")
    result = _run_query(
        db,
        {qf.ingest_replace_clutch().raw_input: qf.ingest_replace_clutch()},
        qf.query_replace_clutch(),
    )
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.matched_count >= 1


def test_e2e_q2_no_match(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "q2.db")
    result = _run_query(
        db,
        {qf.ingest_replace_oil_corolla().raw_input: qf.ingest_replace_oil_corolla()},
        qf.query_replace_clutch_corolla(),
    )
    assert result.status is AskStatus.NO_RESULTS


def test_e2e_q3_entity_context(tmp_path: Path) -> None:
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime

    db = fresh_db_path(tmp_path, "q3.db")
    ingest = qf.ingest_replace_clutch_corolla()
    other = SemanticProposal(
        raw_input="Troquei a embreagem do Civic.",
        object=SemanticEntityMention(text="embreagem", kind_hint="vehicle"),
        entities_mentioned=[SemanticEntityMention(text="Civic", kind_hint="vehicle")],
        action_expression="troquei a embreagem",
        change_semantics=True,
        event_expression="troquei a embreagem do Civic",
        primitive_hint="event",
        temporal=SemanticTime(original_text="", occurrence_aspect="happened"),
    )
    user = _user()
    session = ingest_session()
    svc = _semantic_service(
        db,
        {
            ingest.raw_input: ingest,
            other.raw_input: other,
        },
    )
    assert svc.ingest(ingest.raw_input, user, session).status is IngestStatus.COMMITTED
    assert svc.ingest(other.raw_input, user, session).status is IngestStatus.COMMITTED
    result = _semantic_ask(db, {qf.query_replace_clutch_corolla().raw_input: qf.query_replace_clutch_corolla()}).ask(
        qf.query_replace_clutch_corolla().raw_input,
        user,
        session,
    )
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.matched_count == 1


def test_e2e_positive_corolla(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e2e_pos.db")
    ingest = qf.ingest_replace_clutch_corolla()
    result = _run_query(db, {ingest.raw_input: ingest}, qf.query_replace_clutch_corolla())
    assert result.status is AskStatus.ANSWERED


def test_e2e_negative_corolla(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e2e_neg.db")
    ingest = qf.ingest_replace_oil_corolla()
    result = _run_query(db, {ingest.raw_input: ingest}, qf.query_replace_clutch_corolla())
    assert result.status is AskStatus.NO_RESULTS


def test_e2e_q7_temporal_unknown(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "q7.db")
    ingest = qf.ingest_replace_clutch()
    result = _run_query(db, {ingest.raw_input: ingest}, qf.query_clutch_august())
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.resolved_spec is not None
    assert result.resolved_spec.aggregate is AggregateKind.COUNT
    assert result.query_result.aggregate is not None
    assert result.query_result.aggregate.value == 0
    assert result.query_result.temporal_membership_unknown is True
    assert result.query_result.temporal_completeness is TemporalCompleteness.PARTIAL


def test_e2e_q8_state_regression(tmp_path: Path) -> None:
    from pke.domain import ConceptRef, OccurrenceStatus, RelationToReference
    from pke.interpretation import EntityMention, IngestIntent, IngestIR, IrState, IrTime

    db = fresh_db_path(tmp_path, "q8.db")
    raw = "A porta está aberta?"
    user = _user()
    session = ingest_session()
    ingest_raw = "A porta está aberta."
    door = EntityMention(
        text="porta",
        type_hint=ConceptRef(key="entity.home"),
        role=ConceptRef(key="role.subject"),
    )
    ingest_ir = IngestIR(
        intent=IngestIntent.RECORD_STATE,
        raw_input=ingest_raw,
        entities_mentioned=[door],
        state=IrState(
            value=ConceptRef(key="state.value.open"),
            dimension=ConceptRef(key="state.openness"),
            time=IrTime(
                original_text="",
                occurrence_status=OccurrenceStatus.ONGOING,
                relation_to_reference=RelationToReference.DURING,
                tense_evidence="present",
            ),
        ),
    )
    svc = _service(db, OntologyRegistry.with_core_seeds(), {ingest_raw: ingest_ir})
    assert svc.ingest(ingest_raw, user, session).status is IngestStatus.COMMITTED
    result = _semantic_ask(db, {raw: qf.query_door_open()}).ask(raw, user, session)
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.current_state_value is not None


def test_e2e_q9_relation_regression(tmp_path: Path) -> None:
    from pke.domain import ConceptRef, OccurrenceStatus, RelationToReference
    from pke.interpretation import (
        EntityMention,
        IngestIntent,
        IngestIR,
        IrRelation,
        IrTime,
        RelationAssertionMode,
    )

    db = fresh_db_path(tmp_path, "q9.db")
    raw = "João trabalha na Acme?"
    user = _user()
    session = ingest_session()
    ingest_raw = "João trabalha na Acme."
    joao = EntityMention(
        text="João",
        type_hint=ConceptRef(key="entity.person"),
        role=ConceptRef(key="role.subject"),
    )
    acme = EntityMention(
        text="Acme",
        type_hint=ConceptRef(key="entity.organization"),
        role=ConceptRef(key="role.object"),
    )
    ingest_ir = IngestIR(
        intent=IngestIntent.RECORD_RELATION,
        raw_input=ingest_raw,
        relation=IrRelation(
            type=ConceptRef(key="relation.employed_by"),
            subject=joao,
            object=acme,
            mode=RelationAssertionMode.ASSERT,
            time=IrTime(
                original_text="",
                occurrence_status=OccurrenceStatus.ONGOING,
                relation_to_reference=RelationToReference.DURING,
                tense_evidence="present",
            ),
        ),
    )
    svc = _service(db, OntologyRegistry.with_core_seeds(), {ingest_raw: ingest_ir})
    assert svc.ingest(ingest_raw, user, session).status is IngestStatus.COMMITTED
    result = _semantic_ask(db, {raw: qf.query_employment()}).ask(raw, user, session)
    assert result.status is AskStatus.ANSWERED
    assert result.query_result is not None
    assert result.query_result.relation_answer is not None


def test_q5_maintenance_and_action(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "q5.db")
    ingest = qf.ingest_event_with_type()
    outcome = _resolve_event(qf.query_maintenance_replace_clutch())
    assert outcome.status is QueryResolutionStatus.RESOLVED
    result = _run_query(db, {ingest.raw_input: ingest}, qf.query_maintenance_replace_clutch())
    assert result.status is AskStatus.ANSWERED


def test_q6_partial_past_no_date(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "q6.db")
    result = _run_query(
        db,
        {qf.ingest_replace_clutch().raw_input: qf.ingest_replace_clutch()},
        qf.query_replace_clutch(),
    )
    assert result.status is AskStatus.ANSWERED


def test_false_positive_matrix(tmp_path: Path) -> None:
    """Specific query must not match sibling maintenance event (oil vs clutch)."""
    db = fresh_db_path(tmp_path, "safety.db")
    oil = qf.ingest_replace_oil_corolla()
    result = _run_query(db, {oil.raw_input: oil}, qf.query_replace_clutch())
    assert result.status is AskStatus.NO_RESULTS
