"""I12.6 dual scoring: RAW_MODEL vs POST_ENGINE (guards applied)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from pke.interpretation.interpreter import InterpretationError
from pke.interpretation.models import InterpretationResult
from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.router import collect_assertions
from tests.engine_v1_baseline.corpus import EngineCase
from tests.engine_v1_live_characterization.scoring import (
    RunScore,
    score_failure,
    score_success,
)


@dataclass
class DualRunRecord:
    experiment_id: str
    candidate_id: str
    case_id: str
    run: int
    utterance: str
    category: str
    logical_request_id: str | None = None
    provider_request_id: str | None = None
    attempts: int = 1
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw_content: str | None = None
    proposal_dump: dict[str, Any] | None = None
    raw_score: dict[str, Any] = field(default_factory=dict)
    post_score: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _score_to_dict(score: RunScore) -> dict[str, Any]:
    return asdict(score)


def score_raw_from_proposal(case: EngineCase, proposal: SemanticProposal, *, run: int) -> RunScore:
    """Score as if proposal were accepted without guards (RAW_MODEL)."""
    frames = collect_assertions(proposal)
    kinds = {f.primitive for f in frames}
    if PrimitiveKind.EVENT in kinds and PrimitiveKind.MEASUREMENT in kinds:
        observed_prim = "multi"
    elif len(kinds) == 1:
        observed_prim = next(iter(kinds)).value
    elif not kinds:
        observed_prim = "unknown"
    else:
        # multi other — report primary-ish
        observed_prim = sorted(k.value for k in kinds)[0]

    observed_intent = proposal.utterance_kind
    if observed_intent == "none":
        observed_intent = "none"
    elif observed_intent in {"assert", "describe", "change"}:
        observed_intent = "assert"
    elif observed_intent == "correct":
        observed_intent = "correct"
    elif observed_intent == "query":
        observed_intent = "query"

    # Build a synthetic IR-like evaluation using score_success path via intent/prim
    # Reuse intent/primitive rules by constructing RunScore manually for false correction.
    if observed_intent == "correct" and case.expected_intent != "correct":
        return RunScore(
            case_id=case.id,
            run=run,
            utterance=case.utterance,
            category=case.category,
            ok=False,
            verdict="UNSAFE",
            severity="S4",
            primary_root="A_INTENT",
            observed_intent=observed_intent,
            observed_primitive=observed_prim,
            expected_intent=case.expected_intent,
            expected_primitive=case.expected_primitive,
            notes=["RAW_FALSE_CORRECTION"],
            canonicalization="WRONG_CANONICAL",
        )

    intent_ok = case.expected_intent is None or observed_intent == case.expected_intent
    if case.expected_intent == "assert" and observed_intent == "assert":
        intent_ok = True
    if case.expected_intent == "query" and observed_intent == "query":
        intent_ok = True

    prim_ok = True
    if case.expected_primitive == "multi":
        prim_ok = observed_prim == "multi"
    elif case.expected_primitive is not None:
        prim_ok = observed_prim == case.expected_primitive or (
            case.expected_primitive == "unknown"
        )

    if case.expected_safe_abstention or case.expected_primitive == "unknown":
        if observed_prim in {"unknown", "none"}:
            return RunScore(
                case_id=case.id,
                run=run,
                utterance=case.utterance,
                category=case.category,
                ok=True,
                verdict="SAFE_ABSTENTION",
                severity="S0",
                primary_root="NONE",
                observed_intent=observed_intent,
                observed_primitive=observed_prim,
                expected_intent=case.expected_intent,
                expected_primitive=case.expected_primitive,
                notes=["RAW safe abstention"],
                canonicalization="SAFE_UNRESOLVED",
            )

    if not intent_ok:
        return RunScore(
            case_id=case.id,
            run=run,
            utterance=case.utterance,
            category=case.category,
            ok=False,
            verdict="WRONG_INTENT",
            severity="S3",
            primary_root="A_INTENT",
            observed_intent=observed_intent,
            observed_primitive=observed_prim,
            expected_intent=case.expected_intent,
            expected_primitive=case.expected_primitive,
            notes=["RAW intent mismatch"],
            canonicalization="AMBIGUOUS",
        )

    if not prim_ok:
        return RunScore(
            case_id=case.id,
            run=run,
            utterance=case.utterance,
            category=case.category,
            ok=False,
            verdict="WRONG_PRIMITIVE",
            severity="S3",
            primary_root="B_PRIMITIVE_ROUTING",
            observed_intent=observed_intent,
            observed_primitive=observed_prim,
            expected_intent=case.expected_intent,
            expected_primitive=case.expected_primitive,
            notes=["RAW primitive mismatch"],
            canonicalization="WRONG_CANONICAL",
        )

    return RunScore(
        case_id=case.id,
        run=run,
        utterance=case.utterance,
        category=case.category,
        ok=True,
        verdict="CORRECT",
        severity="S0",
        primary_root="NONE",
        observed_intent=observed_intent,
        observed_primitive=observed_prim,
        expected_intent=case.expected_intent,
        expected_primitive=case.expected_primitive,
        notes=["RAW ok"],
        canonicalization="CORRECT_CANONICAL",
    )


def score_post_engine(
    case: EngineCase,
    *,
    run: int,
    ir: InterpretationResult | None = None,
    exc: BaseException | None = None,
    attempts: int = 1,
) -> RunScore:
    """POST_ENGINE: after Correction Guard + multi-primitive preservation + resolution."""
    if exc is not None:
        msg = str(exc)
        # Guard blocked Correction → safe for Engine (not a mutation path)
        if isinstance(exc, InterpretationError) and msg.startswith("acceptance_guard:"):
            if case.expected_intent != "correct":
                return RunScore(
                    case_id=case.id,
                    run=run,
                    utterance=case.utterance,
                    category=case.category,
                    ok=True,
                    verdict="SAFE_ABSTENTION",
                    severity="S0",
                    primary_root="NONE",
                    observed_intent="correct",
                    observed_primitive=None,
                    expected_intent=case.expected_intent,
                    expected_primitive=case.expected_primitive,
                    attempts=attempts,
                    error=msg[:200],
                    notes=["POST_GUARD_BLOCKED_FALSE_CORRECTION"],
                    canonicalization="SAFE_UNRESOLVED",
                )
            # true correction rejected by guard — reliability miss, not S4 mutation
            return RunScore(
                case_id=case.id,
                run=run,
                utterance=case.utterance,
                category=case.category,
                ok=False,
                verdict="COVERAGE_MISS",
                severity="S1",
                primary_root="A_INTENT",
                observed_intent="correct",
                observed_primitive=None,
                expected_intent=case.expected_intent,
                expected_primitive=case.expected_primitive,
                attempts=attempts,
                error=msg[:200],
                notes=["POST_GUARD_REJECTED_TRUE_CORRECTION"],
                canonicalization="SAFE_UNRESOLVED",
            )
        return score_failure(case, exc, run=run, attempts=attempts)
    assert ir is not None
    return score_success(case, ir, run=run, attempts=attempts)


def attach_dicts(raw: RunScore, post: RunScore) -> tuple[dict[str, Any], dict[str, Any]]:
    return _score_to_dict(raw), _score_to_dict(post)
