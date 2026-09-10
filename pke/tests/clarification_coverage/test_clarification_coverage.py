"""I12.14 clarification coverage expansion — deterministic suite."""

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
from pke.application.pending_operation import MAX_CLARIFICATION_ROUNDS_PER_PENDING_OPERATION
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.sqlite.engine import create_sqlite_engine, init_database, session_factory
from pke.persist.sqlite.uow import SqliteUnitOfWork
from pke.resolution import PersonalContext
from tests.clarification_coverage.corpus import I1214_CORPUS
from tests.clarification_recovery.corpus import mp1_pending


class FixedClock:
    def now(self):
        return dt.datetime(2026, 9, 3, 15, 0, tzinfo=dt.UTC)


def _svc(tmp_path: Path) -> ClarificationRecoveryService:
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'k.db'}")
    init_database(engine)
    factory = session_factory(engine)
    interpreter = FakeInterpreter({})
    ingest = IngestService(
        interpreter,  # type: ignore[arg-type]
        ontology,
        lambda: SqliteUnitOfWork(factory),
        FixedClock(),
    )
    return ClarificationRecoveryService(ingest)


def _ctx(user_id: str = "u1") -> tuple[UserContext, SessionContext]:
    return (
        UserContext(user_id=user_id, timezone="America/Fortaleza"),
        SessionContext(personal=PersonalContext(user_id=user_id)),
    )


def test_corpus_size() -> None:
    assert len(I1214_CORPUS) >= 300


def test_max_rounds_unchanged() -> None:
    assert MAX_CLARIFICATION_ROUNDS_PER_PENDING_OPERATION == 1


def test_mp1_entity_regression(tmp_path: Path) -> None:
    recovery = _svc(tmp_path)
    user, session = _ctx()
    result = recovery.recover(mp1_pending(), "O tanque do Corolla.", user, session)
    assert result.status is RecoveryStatus.RESOLVED_COMMITTED
    assert result.trace.original_raw_reinterpreted is False
    assert result.trace.interpreter_called is False


@pytest.mark.parametrize("case", I1214_CORPUS, ids=lambda c: c.case_id)
def test_coverage_case(case, tmp_path: Path) -> None:
    recovery = _svc(tmp_path)
    user, session = _ctx()
    result = recovery.recover(case.pending_factory(), case.answer, user, session)
    status_map = {
        "resolved_committed": RecoveryStatus.RESOLVED_COMMITTED,
        "remains_unresolved": RecoveryStatus.REMAINS_UNRESOLVED,
        "unsupported_slot": RecoveryStatus.UNSUPPORTED_SLOT,
        "rejected": RecoveryStatus.REJECTED,
        "invalid_answer": RecoveryStatus.INVALID_ANSWER,
        "already_resolved": RecoveryStatus.ALREADY_RESOLVED,
        "idempotent_replay": RecoveryStatus.IDEMPOTENT_REPLAY,
    }
    assert result.status is status_map[case.expected], (
        f"{case.case_id}: got {result.status} ({result.message}) expected {case.expected}"
    )
    assert result.trace.interpreter_called is False
    assert result.trace.original_raw_reinterpreted is False
    assert result.trace.provider_calls == 0
    assert result.trace.non_target_slot_mutated is False
    assert result.trace.unrelated_primitive_added is False
    assert result.trace.unrelated_primitive_removed is False
    assert result.trace.missing_information_invented is False
    assert result.trace.duplicate_target_commit is False
    assert result.trace.duplicate_sibling_commit is False
    if case.expected != "invalid_answer":
        assert result.trace.wrong_dimension_accepted is False
    assert result.trace.wrong_value_type_accepted is False
    assert result.trace.invalid_correction_target_accepted is False


def test_aggregate_metrics(tmp_path: Path) -> None:
    recovery = _svc(tmp_path)
    user, session = _ctx()
    by_status: Counter[str] = Counter()
    by_family_success: Counter[str] = Counter()
    by_family_expected: Counter[str] = Counter()
    safety = Counter()

    for case in I1214_CORPUS:
        result = recovery.recover(case.pending_factory(), case.answer, user, session)
        by_status[result.status.value] += 1
        if case.expected == "resolved_committed":
            by_family_expected[case.family] += 1
            if result.status is RecoveryStatus.RESOLVED_COMMITTED:
                by_family_success[case.family] += 1
        for key, flag in (
            ("ORIGINAL_RAW_TEXT_REINTERPRETED", result.trace.original_raw_reinterpreted),
            ("FULL_INTERPRETER_CALLED_DURING_RECOVERY", result.trace.interpreter_called),
            ("NON_TARGET_SLOT_MUTATED", result.trace.non_target_slot_mutated),
            ("UNRELATED_PRIMITIVE_ADDED", result.trace.unrelated_primitive_added),
            ("UNRELATED_PRIMITIVE_REMOVED", result.trace.unrelated_primitive_removed),
            ("MISSING_INFORMATION_INVENTED", result.trace.missing_information_invented),
            ("RECOVERY_DUPLICATE_TARGET_COMMIT", result.trace.duplicate_target_commit),
            ("RECOVERY_DUPLICATE_SIBLING_COMMIT", result.trace.duplicate_sibling_commit),
            ("WRONG_VALUE_TYPE_ACCEPTED", result.trace.wrong_value_type_accepted),
            ("INVALID_CORRECTION_TARGET_ACCEPTED", result.trace.invalid_correction_target_accepted),
        ):
            if flag:
                safety[key] += 1

    assert all(v == 0 for v in safety.values()), dict(safety)
    for family, n in by_family_expected.items():
        precision_denom = n
        recall = by_family_success[family] / max(1, precision_denom)
        assert recall >= 0.95, f"{family} recall {recall}"

    assert by_status["unsupported_slot"] > 0
    assert by_status["resolved_committed"] > 0


def test_wrong_user_rejected(tmp_path: Path) -> None:
    recovery = _svc(tmp_path)
    user, _ = _ctx("u1")
    _, session = _ctx("u2")
    case = next(c for c in I1214_CORPUS if c.expected == "resolved_committed")
    result = recovery.recover(case.pending_factory(), case.answer, user, session)
    assert result.status is RecoveryStatus.REJECTED
    assert result.message == "user_isolation"


def test_replay_idempotent_state(tmp_path: Path) -> None:
    recovery = _svc(tmp_path)
    user, session = _ctx()
    case = next(c for c in I1214_CORPUS if c.case_id.startswith("STATE_VAL_OK_"))
    first = recovery.recover(case.pending_factory(), case.answer, user, session)
    assert first.status is RecoveryStatus.RESOLVED_COMMITTED
    assert first.pending is not None
    second = recovery.recover(first.pending, case.answer, user, session)
    assert second.status is RecoveryStatus.IDEMPOTENT_REPLAY
    assert second.trace.duplicate_target_commit is False
