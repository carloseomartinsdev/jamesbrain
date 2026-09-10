"""I12.13 bounded clarification recovery — deterministic suite."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from pathlib import Path

import pytest

from pke.application.clarification_recovery import (
    ClarificationRecoveryService,
    RecoveryStatus,
)
from pke.application.ingest import IngestService
from pke.application.pending_operation import (
    MAX_CLARIFICATION_ROUNDS_PER_PENDING_OPERATION,
    PendingOperationStatus,
    PendingSemanticOperation,
)
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.capability_strategy import ClarificationRequest
from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.sqlite.engine import create_sqlite_engine, init_database, session_factory
from pke.persist.sqlite.uow import SqliteUnitOfWork
from pke.resolution import PersonalContext
from tests.clarification_recovery.corpus import I1213_CORPUS, mp1_pending
from tests.structured_proposal_reliability.corpus import mp1_missing_subject


class FixedClock:
    def now(self):
        return dt.datetime(2026, 9, 3, 15, 0, tzinfo=dt.UTC)


def _svc(tmp_path: Path) -> tuple[IngestService, ClarificationRecoveryService]:
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'k.db'}")
    init_database(engine)
    factory = session_factory(engine)
    # Recovery never calls interpret — empty FakeInterpreter proves spy.
    interpreter = FakeInterpreter({})
    ingest = IngestService(
        interpreter,  # type: ignore[arg-type]
        ontology,
        lambda: SqliteUnitOfWork(factory),
        FixedClock(),
    )
    recovery = ClarificationRecoveryService(ingest)
    return ingest, recovery


def _ctx(user_id: str = "u1") -> tuple[UserContext, SessionContext]:
    return (
        UserContext(user_id=user_id, timezone="America/Fortaleza"),
        SessionContext(personal=PersonalContext(user_id=user_id)),
    )


def test_corpus_size() -> None:
    assert len(I1213_CORPUS) >= 240


def test_mp1_recovery_success(tmp_path: Path) -> None:
    _, recovery = _svc(tmp_path)
    user, session = _ctx()
    pending = mp1_pending()
    original_dump = dict(pending.proposal_dump)
    result = recovery.recover(pending, "O tanque do Corolla.", user, session)
    assert result.status is RecoveryStatus.RESOLVED_COMMITTED
    assert result.ingest is not None
    assert result.ingest.status is IngestStatus.COMMITTED
    assert result.ingest.materialization is not None
    assert result.ingest.materialization.measurement_ids
    # Event must not fake-canonicalize solely from recovery
    # subject filled; original proposal dump immutable
    assert pending.proposal_dump == original_dump
    assert result.filled_proposal is not None
    assert result.filled_proposal.subject is not None
    assert "Corolla" in result.filled_proposal.subject.text or "tanque" in result.filled_proposal.subject.text.casefold()
    assert result.filled_proposal.raw_input == original_dump["raw_input"]
    assert result.trace.interpreter_called is False
    assert result.trace.original_raw_reinterpreted is False
    assert result.trace.provider_calls == 0
    assert result.trace.non_target_slot_mutated is False
    assert result.trace.unrelated_primitive_added is False


def test_mp1_irrelevant_temporal(tmp_path: Path) -> None:
    _, recovery = _svc(tmp_path)
    user, session = _ctx()
    result = recovery.recover(mp1_pending(), "foi ontem", user, session)
    assert result.status is RecoveryStatus.REMAINS_UNRESOLVED
    assert result.ingest is None or result.ingest.status is not IngestStatus.COMMITTED


def test_mp1_replay_idempotent(tmp_path: Path) -> None:
    _, recovery = _svc(tmp_path)
    user, session = _ctx()
    pending = mp1_pending()
    first = recovery.recover(pending, "temperatura", user, session)
    assert first.status is RecoveryStatus.RESOLVED_COMMITTED
    assert first.pending is not None
    mid = first.ingest.materialization.measurement_ids if first.ingest and first.ingest.materialization else []
    second = recovery.recover(first.pending, "temperatura", user, session)
    assert second.status is RecoveryStatus.IDEMPOTENT_REPLAY
    assert second.trace.duplicate_target_commit is False
    # no second materialization object
    assert second.ingest is None


def test_fake_interpreter_never_called(tmp_path: Path) -> None:
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'k2.db'}")
    init_database(engine)
    factory = session_factory(engine)

    class SpyInterpreter(FakeInterpreter):
        def __init__(self) -> None:
            super().__init__({})
            self.calls = 0

        def interpret(self, raw, ctx):  # type: ignore[no-untyped-def]
            self.calls += 1
            return super().interpret(raw, ctx)

    spy = SpyInterpreter()
    ingest = IngestService(spy, ontology, lambda: SqliteUnitOfWork(factory), FixedClock())  # type: ignore[arg-type]
    recovery = ClarificationRecoveryService(ingest)
    user, session = _ctx()
    recovery.recover(mp1_pending(), "sensor X", user, session)
    assert spy.calls == 0


def test_wrong_user_rejected(tmp_path: Path) -> None:
    _, recovery = _svc(tmp_path)
    user, _ = _ctx("u1")
    session = SessionContext(personal=PersonalContext(user_id="u2"))
    result = recovery.recover(mp1_pending(), "sensor", user, session)
    assert result.status is RecoveryStatus.REJECTED
    assert result.ingest is None


def test_max_rounds_constant() -> None:
    assert MAX_CLARIFICATION_ROUNDS_PER_PENDING_OPERATION == 1


def test_corpus_metrics(tmp_path: Path) -> None:
    _, recovery = _svc(tmp_path)
    user, session = _ctx()
    success = 0
    unresolved = 0
    unsupported = 0
    expected_ok = 0
    expected_n = 0
    safety = Counter()
    for case in I1213_CORPUS:
        pending = case.pending_factory()
        result = recovery.recover(pending, case.answer, user, session)
        if result.status is RecoveryStatus.RESOLVED_COMMITTED:
            success += 1
        elif result.status is RecoveryStatus.REMAINS_UNRESOLVED:
            unresolved += 1
        elif result.status is RecoveryStatus.UNSUPPORTED_SLOT:
            unsupported += 1
        if case.expected == "resolved_committed":
            expected_n += 1
            if result.status is RecoveryStatus.RESOLVED_COMMITTED:
                expected_ok += 1
        if case.expected == "unsupported_slot":
            assert result.status is RecoveryStatus.UNSUPPORTED_SLOT
        if case.family in {"irrelevant", "mp1_irrelevant"}:
            assert result.status is RecoveryStatus.REMAINS_UNRESOLVED
        if case.expected == "remains_unresolved" and case.family in {
            "relation_object",
            "relation_subject",
            "state_entity",
        }:
            assert result.status in {
                RecoveryStatus.REMAINS_UNRESOLVED,
                RecoveryStatus.RESOLVED_COMMITTED,
            }
        for key, flag in (
            ("FULL_INTERPRETER_CALLED_DURING_RECOVERY", result.trace.interpreter_called),
            ("ORIGINAL_RAW_TEXT_REINTERPRETED", result.trace.original_raw_reinterpreted),
            ("NON_TARGET_SLOT_MUTATED", result.trace.non_target_slot_mutated),
            ("UNRELATED_PRIMITIVE_ADDED", result.trace.unrelated_primitive_added),
            ("UNRELATED_PRIMITIVE_REMOVED", result.trace.unrelated_primitive_removed),
            ("RECOVERY_DUPLICATE_TARGET_COMMIT", result.trace.duplicate_target_commit),
        ):
            if flag:
                safety[key] += 1

    recall = expected_ok / max(1, expected_n)
    assert all(v == 0 for v in safety.values())
    assert success > 0
    assert unsupported > 0
    assert unresolved > 0
    assert recall >= 0.95


def test_orchestrator_avoids_full_reinterpretation(tmp_path: Path) -> None:
    from pke.application.clarification_recovery import ClarificationRecoveryService
    from pke.product.auth import AuthUser
    from pke.product.api.v1.dtos import ApiClarificationAnswerRequest
    from pke.product.conversation.engine_gateway import EngineGateway, TurnCachedInterpreter
    from pke.product.conversation.orchestrator import ConversationOrchestrator
    from pke.product.conversation.store import ProductStore
    from pke.persist.sqlite.read_store import SqliteKnowledgeReadStore
    from pke.application.ask import AskService

    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'k3.db'}")
    init_database(engine)
    factory = session_factory(engine)

    class Spy(FakeInterpreter):
        def __init__(self) -> None:
            super().__init__({})
            self.calls: list[str] = []

        def interpret(self, raw, ctx):  # type: ignore[no-untyped-def]
            self.calls.append(raw)
            raise AssertionError("Interpreter must not be called during recovery")

    spy = Spy()
    ingest = IngestService(spy, ontology, lambda: SqliteUnitOfWork(factory), FixedClock())  # type: ignore[arg-type]
    ask = AskService(spy, ontology, SqliteKnowledgeReadStore(factory), FixedClock())  # type: ignore[arg-type]
    gateway = EngineGateway(TurnCachedInterpreter(spy), ingest, ask)
    store = ProductStore(tmp_path / "product.db")
    recovery = ClarificationRecoveryService(ingest)
    orch = ConversationOrchestrator(
        store,
        gateway,
        SqliteKnowledgeReadStore(factory),
        clarification_recovery=recovery,
    )
    user = AuthUser(id="u1", display_name="T", auth_mode="dev")
    conv = orch.create_conversation(user)
    pending = mp1_pending()
    cid = store.add_clarification(
        user_id=user.id,
        conversation_id_value=conv.id,
        message_id_value="m1",
        mode="text",
        options=[],
        original_text=pending.originating_raw,
        pending_operation_json=pending.model_dump_json(),
    )
    resp = orch.answer_clarification(
        user, cid, ApiClarificationAnswerRequest(text="tanque do Corolla")
    )
    assert spy.calls == []
    assert resp.operation is not None
    assert resp.operation.outcome.value in {"committed", "unsupported", "needs_clarification"}
