"""I12.4 — Interpreter Correction Acceptance Guard tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pke.application.correction_ingest import CorrectionIngestOrchestrator
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation.acceptance.correction_guard import (
    AcceptanceOutcome,
    evaluate_correction_acceptance,
)
from pke.interpretation.interpreter import InterpretationError
from pke.interpretation.models import IngestIntent, IngestIR, IrCorrection, IrCorrectionTarget
from pke.interpretation.retry import FailureClass, RetryPolicy
from pke.resolution.context import PersonalContext

from tests.interpreter_acceptance_guard.corpus import (
    CAPTURED_S4,
    FALSE_CORRECTIONS,
    TRUE_CORRECTIONS,
    all_cases,
)


@pytest.mark.parametrize("case", all_cases(), ids=lambda c: c.case_id)
def test_guard_corpus_case(case) -> None:
    decision = evaluate_correction_acceptance(
        case.utterance,
        proposed_as_correction=True,
        prior_utterances=case.prior,
    )
    assert decision.outcome.value == case.expected, (
        f"{case.case_id}: got {decision.outcome}/{decision.reason_code} "
        f"expected {case.expected} for {case.utterance!r}"
    )


def test_corpus_size_floor() -> None:
    assert len(TRUE_CORRECTIONS) >= 60
    assert len(FALSE_CORRECTIONS) >= 100
    assert len(all_cases()) >= 200
    assert len(CAPTURED_S4) == 9


def test_captured_s4_none_accepted() -> None:
    accepted = 0
    blocked = 0
    for case in CAPTURED_S4:
        d = evaluate_correction_acceptance(
            case.utterance, proposed_as_correction=True, prior_utterances=case.prior
        )
        if d.outcome is AcceptanceOutcome.ACCEPT:
            accepted += 1
        else:
            blocked += 1
    assert accepted == 0
    assert blocked == 9
    assert blocked / 9 == 1.0


def test_safety_precision_and_recall() -> None:
    """FALSE_CORRECTION_ACCEPTED = 0; clear true recall >= 0.90."""
    true_acc = true_rej = false_acc = false_rej = clarify = 0
    clear_pos_acc = clear_pos_total = 0

    for case in all_cases():
        if case.family == "captured_s4":
            continue
        d = evaluate_correction_acceptance(
            case.utterance, proposed_as_correction=True, prior_utterances=case.prior
        )
        is_true = case.expected == "accept"
        # clarification expected cases are neither false-accept nor true-accept metrics
        if case.expected == "clarification_required":
            if d.outcome is AcceptanceOutcome.CLARIFICATION_REQUIRED:
                clarify += 1
            elif d.outcome is AcceptanceOutcome.ACCEPT and not is_true:
                false_acc += 1
            continue

        if is_true:
            if case.clear_positive:
                clear_pos_total += 1
            if d.outcome is AcceptanceOutcome.ACCEPT:
                true_acc += 1
                if case.clear_positive:
                    clear_pos_acc += 1
            else:
                true_rej += 1
        else:
            if d.outcome is AcceptanceOutcome.ACCEPT:
                false_acc += 1
            else:
                false_rej += 1
                if d.outcome is AcceptanceOutcome.CLARIFICATION_REQUIRED:
                    clarify += 1

    assert false_acc == 0, "FALSE_CORRECTION_ACCEPTED must be 0"
    precision = true_acc / (true_acc + false_acc) if (true_acc + false_acc) else 0.0
    assert precision == 1.0
    recall = clear_pos_acc / clear_pos_total if clear_pos_total else 0.0
    assert recall >= 0.90, f"clear true recall {recall:.3f} < 0.90"
    assert true_acc > 0, "degenerate always-reject guard"


def test_passthrough_non_correction() -> None:
    d = evaluate_correction_acceptance(
        "João não trabalha mais na Acme.", proposed_as_correction=False
    )
    assert d.outcome is AcceptanceOutcome.ACCEPT
    assert d.reason_code.value == "NOT_A_CORRECTION_PROPOSAL"


def test_guard_does_not_rewrite_or_select_target() -> None:
    d = evaluate_correction_acceptance(
        "Corrigindo, foi em 2025.", proposed_as_correction=True
    )
    assert not hasattr(d, "target_id")
    assert not hasattr(d, "rewritten_primitive")
    assert d.proposed_as_correction is True


def test_acceptance_guard_non_retryable() -> None:
    policy = RetryPolicy(max_attempts=2)
    exc = InterpretationError("acceptance_guard:CORRECTION_SIGNAL_INSUFFICIENT")
    assert policy.classify(exc) is FailureClass.SEMANTIC_NON_RETRYABLE
    assert policy.is_retryable(exc, attempt=1) is False


def test_ingest_rejects_before_target_resolver() -> None:
    orch = CorrectionIngestOrchestrator(ontology=MagicMock(), clock=MagicMock())
    ir = IngestIR(
        raw_input="João não trabalha mais na Acme.",
        intent=IngestIntent.CORRECT,
        correction=IrCorrection(
            operation="replace",
            target=IrCorrectionTarget(kind="relation", entity_text="João"),
        ),
    )
    session = SessionContext(personal=PersonalContext(user_id="u1"))
    user = UserContext(user_id="u1", timezone="UTC", now=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    result = orch.ingest(
        ir=ir,
        user=user,
        session=session,
        uow=MagicMock(),
        lookup=MagicMock(),
        now=user.now,
        resolve_entities=MagicMock(),
        resolve_times=MagicMock(),
    )
    assert result.status is IngestStatus.REJECTED
    assert orch.target_resolver_calls == 0
    assert any(i.code == "acceptance_guard.rejected" for i in result.issues)


def test_ingest_clarify_before_target_resolver_for_cr16() -> None:
    orch = CorrectionIngestOrchestrator(ontology=MagicMock(), clock=MagicMock())
    ir = IngestIR(
        raw_input="desculpa olhei errado; está fechada",
        intent=IngestIntent.CORRECT,
        correction=IrCorrection(
            operation="replace",
            target=IrCorrectionTarget(kind="state", entity_text="porta"),
        ),
    )
    session = SessionContext(personal=PersonalContext(user_id="u1"))
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    result = orch.ingest(
        ir=ir,
        user=UserContext(user_id="u1", timezone="UTC", now=now),
        session=session,
        uow=MagicMock(),
        lookup=MagicMock(),
        now=now,
        resolve_entities=MagicMock(),
        resolve_times=MagicMock(),
    )
    assert result.status is IngestStatus.NEEDS_CLARIFICATION
    assert orch.target_resolver_calls == 0


def test_metrics_report_shape() -> None:
    """Executive metrics for I12.4 report."""
    s4_blocked = sum(
        1
        for c in CAPTURED_S4
        if evaluate_correction_acceptance(
            c.utterance, proposed_as_correction=True
        ).outcome
        is not AcceptanceOutcome.ACCEPT
    )
    assert s4_blocked == 9
