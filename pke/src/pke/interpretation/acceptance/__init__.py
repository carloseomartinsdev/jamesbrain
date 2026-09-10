"""Interpreter acceptance boundary (pre-commit)."""

from pke.interpretation.acceptance.correction_guard import (
    AcceptanceDecision,
    AcceptanceOutcome,
    CorrectionAcceptanceReason,
    evaluate_correction_acceptance,
    proposal_flags_indicate_correction,
)

__all__ = [
    "AcceptanceDecision",
    "AcceptanceOutcome",
    "CorrectionAcceptanceReason",
    "evaluate_correction_acceptance",
    "proposal_flags_indicate_correction",
]
