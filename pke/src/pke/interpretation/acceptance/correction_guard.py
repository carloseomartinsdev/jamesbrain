"""Correction Acceptance Guard — deterministic pre-commit safety (I12.4).

LLM proposes Correction. This guard decides whether that proposal is *admissible*.
It does not rewrite primitives, invent targets, or call another model.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence


class AcceptanceOutcome(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    CLARIFICATION_REQUIRED = "clarification_required"


class CorrectionAcceptanceReason(StrEnum):
    CORRECTION_SUPPORTED = "CORRECTION_SUPPORTED"
    CORRECTION_SIGNAL_INSUFFICIENT = "CORRECTION_SIGNAL_INSUFFICIENT"
    CORRECTION_CONFLICTS_WITH_TERMINATION_CUE = "CORRECTION_CONFLICTS_WITH_TERMINATION_CUE"
    CORRECTION_CONFLICTS_WITH_EVOLUTION_CUE = "CORRECTION_CONFLICTS_WITH_EVOLUTION_CUE"
    CORRECTION_CONFLICTS_WITH_NEW_OBSERVATION_CUE = "CORRECTION_CONFLICTS_WITH_NEW_OBSERVATION_CUE"
    CORRECTION_CONFLICTS_WITH_REPETITION_CUE = "CORRECTION_CONFLICTS_WITH_REPETITION_CUE"
    CORRECTION_QUERY_FORM = "CORRECTION_QUERY_FORM"
    CORRECTION_TARGET_REFERENCE_AMBIGUOUS = "CORRECTION_TARGET_REFERENCE_AMBIGUOUS"
    CORRECTION_CONTEXT_REQUIRED = "CORRECTION_CONTEXT_REQUIRED"
    NOT_A_CORRECTION_PROPOSAL = "NOT_A_CORRECTION_PROPOSAL"


@dataclass(frozen=True)
class AcceptanceDecision:
    outcome: AcceptanceOutcome
    reason_code: CorrectionAcceptanceReason
    proposed_as_correction: bool


def _fold(text: str) -> str:
    lowered = text.casefold().strip()
    normalized = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


# Explicit meta-correction / error admission (always strong when present).
_META_STRONG = (
    r"\bcorrigindo\b",
    r"\bcorrecao\b",
    r"\bretificando\b",
    r"\beu me enganei\b",
    r"\bme enganei\b",
    r"\beu errei\b",
    r"\bops errei\b",
    r"\berrei:",
    r"\berrei,",
    r"\berrei —",
    r"\berrei -",
    r"\berrei o (valor|ano|mes|nome)\b",
    r"\bfalei errado\b",
    r"\bdisse errado\b",
    r"\bquis dizer\b",
    r"\beu quis dizer\b",
    r"\bdesconsidere\b",
    r"\bdesconsiderar\b",
)

# Perceptual misspeaking — strong only with prior or self-contained replacement.
_PERCEPTUAL_ERROR = (
    r"\bli errado\b",
    r"\bolhei errado\b",
)

# Contrastive replacement structure (X was wrong, Y is right).
_SELF_CONTAINED_REPLACE = (
    r"\bnao era\b.+\bera\b",
    r"\bnao foi\b.+\bfoi\b",
    r"\beri?a(m)?\s+\d",
    r"\bforam\s+\d",
    r"\bnao,?\s+falei errado\b",
)

# Weak / ambiguous — alone insufficient without prior context.
_WEAK_PATTERNS = (
    r"\bna verdade\b",
    r"\bao contrario\b",
    r"\bisso estava errado\b",
    r"\bestava errado\b",
    r"\beu estava enganado\b",
)

_TERMINATION = (
    r"\bnao\b.+\bmais\b",
    r"\bnao trabalha mais\b",
    r"\bnao mora mais\b",
)

_EVOLUTION = (
    r"\bagora\b",
)

_REPETITION = (r"\bde novo\b", r"\bnovamente\b")

_NEW_OBSERVATION = (
    r"\bagora (esta|ta|deu|marcou)\b",
    r"\bmedi (de )?novo\b",
)

_CONTEXTUAL_SHORT = (
    # Require comma after não ("Não, foi…") — bare "não foi em 2024" is negation, not correction.
    r"^nao,\s+foi\b",
    r"^nao,\s+era\b",
    r"^nao,\s+em\b",
    r"^foi em\b",
    r"^era\b",
)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text) for p in patterns)


def has_strong_correction_evidence(utterance: str, *, has_prior: bool = False) -> bool:
    folded = _fold(utterance)
    if _matches_any(folded, _META_STRONG):
        return True
    if _matches_any(folded, _SELF_CONTAINED_REPLACE):
        return True
    if _matches_any(folded, _PERCEPTUAL_ERROR) and (
        has_prior or _matches_any(folded, _SELF_CONTAINED_REPLACE)
    ):
        return True
    return False


def has_weak_correction_cue(utterance: str) -> bool:
    return _matches_any(_fold(utterance), _WEAK_PATTERNS)


def is_query_form(utterance: str) -> bool:
    t = utterance.strip()
    if t.endswith("?"):
        return True
    folded = _fold(t)
    if re.search(r"\b(corrigi|corrigiu|corrigimos)\b.+\?$", folded):
        return True
    if re.search(r"\beu disse que\b", folded) and "?" in t:
        return True
    return False


def evaluate_correction_acceptance(
    utterance: str,
    *,
    proposed_as_correction: bool,
    prior_utterances: Sequence[str] = (),
) -> AcceptanceDecision:
    """Decide whether a Correction *proposal* is admissible.

    If ``proposed_as_correction`` is False, returns NOT_A_CORRECTION_PROPOSAL / ACCEPT
    (passthrough — this guard only constrains Correction proposals).
    """
    if not proposed_as_correction:
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.ACCEPT,
            reason_code=CorrectionAcceptanceReason.NOT_A_CORRECTION_PROPOSAL,
            proposed_as_correction=False,
        )

    text = utterance or ""
    folded = _fold(text)
    priors = [p for p in prior_utterances if (p or "").strip()]
    has_prior = len(priors) > 0
    meta = _matches_any(folded, _META_STRONG)
    self_contained = _matches_any(folded, _SELF_CONTAINED_REPLACE)
    perceptual = _matches_any(folded, _PERCEPTUAL_ERROR)
    weak = has_weak_correction_cue(text)
    strong = meta or self_contained or (perceptual and (has_prior or self_contained))

    # Query form proposing Correction is never admissible as mutation intent —
    # even if the question contains words like "correção" / "quis dizer".
    if is_query_form(text):
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.REJECT,
            reason_code=CorrectionAcceptanceReason.CORRECTION_QUERY_FORM,
            proposed_as_correction=True,
        )

    # Competing lifecycle cues without strong correction evidence → reject.
    if not strong:
        if _matches_any(folded, _TERMINATION):
            return AcceptanceDecision(
                outcome=AcceptanceOutcome.REJECT,
                reason_code=CorrectionAcceptanceReason.CORRECTION_CONFLICTS_WITH_TERMINATION_CUE,
                proposed_as_correction=True,
            )
        if _matches_any(folded, _REPETITION):
            return AcceptanceDecision(
                outcome=AcceptanceOutcome.REJECT,
                reason_code=CorrectionAcceptanceReason.CORRECTION_CONFLICTS_WITH_REPETITION_CUE,
                proposed_as_correction=True,
            )
        if _matches_any(folded, _EVOLUTION) and not weak:
            return AcceptanceDecision(
                outcome=AcceptanceOutcome.REJECT,
                reason_code=CorrectionAcceptanceReason.CORRECTION_CONFLICTS_WITH_EVOLUTION_CUE,
                proposed_as_correction=True,
            )
        if _matches_any(folded, _NEW_OBSERVATION):
            return AcceptanceDecision(
                outcome=AcceptanceOutcome.REJECT,
                reason_code=CorrectionAcceptanceReason.CORRECTION_CONFLICTS_WITH_NEW_OBSERVATION_CUE,
                proposed_as_correction=True,
            )

    if meta or self_contained:
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.ACCEPT,
            reason_code=CorrectionAcceptanceReason.CORRECTION_SUPPORTED,
            proposed_as_correction=True,
        )

    # Perceptual error admission without prior referent → clarify (do not commit).
    if perceptual and not has_prior:
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.CLARIFICATION_REQUIRED,
            reason_code=CorrectionAcceptanceReason.CORRECTION_CONTEXT_REQUIRED,
            proposed_as_correction=True,
        )

    if perceptual and has_prior:
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.ACCEPT,
            reason_code=CorrectionAcceptanceReason.CORRECTION_SUPPORTED,
            proposed_as_correction=True,
        )

    # Contextual short correction after a prior assertion ("Não, foi em 2025.")
    if has_prior and _matches_any(folded, _CONTEXTUAL_SHORT):
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.ACCEPT,
            reason_code=CorrectionAcceptanceReason.CORRECTION_SUPPORTED,
            proposed_as_correction=True,
        )

    # "na verdade" / vague retract with prior → clarification when pronoun-ambiguous
    if weak:
        if has_prior:
            if re.search(r"\b(ele|ela|isso|aquilo)\b", folded):
                return AcceptanceDecision(
                    outcome=AcceptanceOutcome.CLARIFICATION_REQUIRED,
                    reason_code=CorrectionAcceptanceReason.CORRECTION_TARGET_REFERENCE_AMBIGUOUS,
                    proposed_as_correction=True,
                )
            return AcceptanceDecision(
                outcome=AcceptanceOutcome.ACCEPT,
                reason_code=CorrectionAcceptanceReason.CORRECTION_SUPPORTED,
                proposed_as_correction=True,
            )
        return AcceptanceDecision(
            outcome=AcceptanceOutcome.REJECT,
            reason_code=CorrectionAcceptanceReason.CORRECTION_SIGNAL_INSUFFICIENT,
            proposed_as_correction=True,
        )

    # Bare negation / contrast / preference without correction meta
    return AcceptanceDecision(
        outcome=AcceptanceOutcome.REJECT,
        reason_code=CorrectionAcceptanceReason.CORRECTION_SIGNAL_INSUFFICIENT,
        proposed_as_correction=True,
    )


def proposal_flags_indicate_correction(
    *,
    utterance_kind: str | None = None,
    correction_semantics: bool = False,
    correction_operation: str | None = None,
) -> bool:
    return (
        utterance_kind == "correct"
        or correction_semantics
        or correction_operation is not None
    )
