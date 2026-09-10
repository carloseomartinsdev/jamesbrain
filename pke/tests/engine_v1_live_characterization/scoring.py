"""Deterministic scoring of live Interpreter outcomes vs corpus expectations.

Does not call the provider. Does not mutate expected labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pke.interpretation.interpreter import InterpretationError
from pke.interpretation.models import IngestIR, IngestIntent, InterpretationResult, QueryIR
from tests.engine_v1_baseline.corpus import EngineCase

CaseVerdict = Literal[
    "STABLE_CORRECT",  # used at case aggregate level
    "CORRECT",
    "SAFE_ABSTENTION",
    "COVERAGE_MISS",
    "SEMANTIC_LOSS",
    "WRONG_PRIMITIVE",
    "WRONG_INTENT",
    "WRONG_CANONICAL",
    "UNSAFE",
    "TRANSPORT_FAILURE",
    "UNKNOWN",
]

VarianceClass = Literal[
    "STABLE_CORRECT",
    "STABLE_SAFE_ABSTENTION",
    "UNSTABLE_BUT_SAFE",
    "UNSAFE_VARIANCE",
]

Severity = Literal["S0", "S1", "S2", "S3", "S4"]

PrimaryRoot = Literal[
    "A_INTENT",
    "B_PRIMITIVE_ROUTING",
    "C_SEMANTIC_FRAME",
    "D_CANONICALIZATION",
    "E_PROVIDER_TRANSPORT",
    "NONE",
]


@dataclass
class RunScore:
    case_id: str
    run: int
    utterance: str
    category: str
    ok: bool
    verdict: CaseVerdict
    severity: Severity
    primary_root: PrimaryRoot
    observed_intent: str | None
    observed_primitive: str | None
    expected_intent: str | None
    expected_primitive: str | None
    attempts: int = 1
    retry_recovered: bool = False
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)
    canonicalization: str = "UNKNOWN"  # CORRECT_CANONICAL|SAFE_UNRESOLVED|AMBIGUOUS|WRONG_CANONICAL


def _intent_of(ir: InterpretationResult) -> str:
    if isinstance(ir, QueryIR):
        return "query"
    if isinstance(ir, IngestIR):
        if ir.intent is IngestIntent.CORRECT:
            return "correct"
        if ir.intent is IngestIntent.NONE:
            return "none"
        return "assert"
    return "unknown"


def _primitive_of(ir: InterpretationResult) -> str:
    if isinstance(ir, QueryIR):
        q = ir.query
        if q.intent == "measurement" or q.measurement_dimension_key:
            return "measurement"
        if q.intent == "state" or q.state_dimensions:
            return "state"
        if q.intent == "relation" or q.relation_types:
            return "relation"
        if q.intent == "attribute":
            return "attribute"
        if q.event_types:
            return "event"
        return "query"
    if not isinstance(ir, IngestIR):
        return "unknown"
    has_e = ir.event is not None
    has_m = ir.measurement is not None
    has_s = ir.state is not None
    has_r = ir.relation is not None
    has_a = ir.attribute is not None
    if ir.intent is IngestIntent.CORRECT:
        # correction meta — still report replacement primitive if present
        if has_m and has_e:
            return "multi"
        if has_m:
            return "measurement"
        if has_a:
            return "attribute"
        if has_s:
            return "state"
        if has_r:
            return "relation"
        if has_e:
            return "event"
        return "correct"
    if has_e and has_m:
        return "multi"
    if has_m or ir.intent is IngestIntent.RECORD_MEASUREMENT:
        return "measurement"
    if has_e or ir.intent is IngestIntent.RECORD_EVENT:
        return "event"
    if has_s or ir.intent is IngestIntent.RECORD_STATE:
        return "state"
    if has_r or ir.intent is IngestIntent.RECORD_RELATION:
        return "relation"
    if has_a or ir.intent is IngestIntent.RECORD_ATTRIBUTE:
        return "attribute"
    return "unknown"


def _primitives_compatible(expected: str | None, observed: str | None) -> bool:
    if expected is None or observed is None:
        return True
    if expected == observed:
        return True
    # query family: observed "query" or specific query primitive OK when expected query intent
    if expected == "unknown":
        return observed in {"unknown", "none", "correct"}
    if expected == "multi":
        return observed == "multi"
    if expected == "type":
        return observed in {"attribute", "type", "unknown"}
    return False


def score_success(case: EngineCase, ir: InterpretationResult, *, run: int, attempts: int = 1) -> RunScore:
    observed_intent = _intent_of(ir)
    observed_prim = _primitive_of(ir)
    notes: list[str] = []
    severity: Severity = "S0"
    verdict: CaseVerdict = "CORRECT"
    root: PrimaryRoot = "NONE"
    canon = "CORRECT_CANONICAL"

    intent_ok = case.expected_intent is None or observed_intent == case.expected_intent
    # query expected: QueryIR is enough even if primitive detail differs
    if case.expected_intent == "query" and observed_intent == "query":
        intent_ok = True
    if case.expected_intent == "assert" and observed_intent == "assert":
        intent_ok = True
    if case.expected_intent == "correct" and observed_intent == "correct":
        intent_ok = True

    prim_ok = _primitives_compatible(case.expected_primitive, observed_prim)
    if case.expected_primitive == "unknown" or case.expected_safe_abstention:
        # Prefer safe unresolved over forced primitive
        if observed_prim in {"unknown", "none"} or (
            isinstance(ir, IngestIR) and ir.intent is IngestIntent.NONE
        ):
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
                attempts=attempts,
                notes=["expected safe abstention / unknown"],
                canonicalization="SAFE_UNRESOLVED",
            )
        if not prim_ok and observed_prim not in {"unknown"}:
            notes.append("forced primitive where abstention preferred")
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
                attempts=attempts,
                notes=notes,
                canonicalization="WRONG_CANONICAL",
            )

    if not intent_ok:
        # False correction is unsafe
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
                attempts=attempts,
                notes=["FALSE_CORRECTION_ROUTING"],
                canonicalization="WRONG_CANONICAL",
            )
        if observed_intent == "assert" and case.expected_intent == "query":
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
                attempts=attempts,
                notes=["QUERY_ASSERTION_CONFUSION"],
                canonicalization="WRONG_CANONICAL",
            )
        if observed_intent == "query" and case.expected_intent == "assert":
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
                attempts=attempts,
                notes=["ASSERTION_QUERY_CONFUSION"],
                canonicalization="AMBIGUOUS",
            )
        return RunScore(
            case_id=case.id,
            run=run,
            utterance=case.utterance,
            category=case.category,
            ok=False,
            verdict="WRONG_INTENT",
            severity=case.severity_if_wrong if case.severity_if_wrong in {"S2", "S3", "S4"} else "S3",
            primary_root="A_INTENT",
            observed_intent=observed_intent,
            observed_primitive=observed_prim,
            expected_intent=case.expected_intent,
            expected_primitive=case.expected_primitive,
            attempts=attempts,
            notes=notes,
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
            attempts=attempts,
            notes=[f"expected={case.expected_primitive} observed={observed_prim}"],
            canonicalization="WRONG_CANONICAL",
        )

    # Soft coverage: missing_hints present → safe unresolved aspect
    if isinstance(ir, IngestIR) and ir.missing_hints:
        notes.append("missing_hints present")
        canon = "SAFE_UNRESOLVED"
        if case.category == "unknown_concept":
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
                attempts=attempts,
                notes=notes,
                canonicalization=canon,
            )
        verdict = "COVERAGE_MISS"
        severity = "S1"
        root = "D_CANONICALIZATION"

    return RunScore(
        case_id=case.id,
        run=run,
        utterance=case.utterance,
        category=case.category,
        ok=verdict in {"CORRECT", "SAFE_ABSTENTION", "COVERAGE_MISS"},
        verdict=verdict if verdict != "CORRECT" or not notes else "CORRECT",
        severity=severity if verdict != "CORRECT" else "S0",
        primary_root=root if verdict != "CORRECT" else "NONE",
        observed_intent=observed_intent,
        observed_primitive=observed_prim,
        expected_intent=case.expected_intent,
        expected_primitive=case.expected_primitive,
        attempts=attempts,
        notes=notes,
        canonicalization=canon,
    )


def score_failure(
    case: EngineCase,
    exc: BaseException,
    *,
    run: int,
    attempts: int = 1,
) -> RunScore:
    msg = str(exc)
    if isinstance(exc, InterpretationError):
        if msg.startswith("proposal_semantics:") or msg.startswith("semantic_resolution:"):
            if case.expected_safe_abstention or case.expected_primitive == "unknown":
                return RunScore(
                    case_id=case.id,
                    run=run,
                    utterance=case.utterance,
                    category=case.category,
                    ok=True,
                    verdict="SAFE_ABSTENTION",
                    severity="S0",
                    primary_root="NONE",
                    observed_intent=None,
                    observed_primitive=None,
                    expected_intent=case.expected_intent,
                    expected_primitive=case.expected_primitive,
                    attempts=attempts,
                    error=msg[:200],
                    notes=["interpreter abstained / non-materializable"],
                    canonicalization="SAFE_UNRESOLVED",
                )
            return RunScore(
                case_id=case.id,
                run=run,
                utterance=case.utterance,
                category=case.category,
                ok=False,
                verdict="COVERAGE_MISS" if "concept" in msg else "SEMANTIC_LOSS",
                severity="S1" if "concept" in msg else "S2",
                primary_root="D_CANONICALIZATION" if "concept" in msg else "C_SEMANTIC_FRAME",
                observed_intent=None,
                observed_primitive=None,
                expected_intent=case.expected_intent,
                expected_primitive=case.expected_primitive,
                attempts=attempts,
                error=msg[:200],
                notes=[msg[:120]],
                canonicalization="SAFE_UNRESOLVED",
            )
        if msg.startswith("provider:"):
            return RunScore(
                case_id=case.id,
                run=run,
                utterance=case.utterance,
                category=case.category,
                ok=False,
                verdict="TRANSPORT_FAILURE",
                severity="S2",
                primary_root="E_PROVIDER_TRANSPORT",
                observed_intent=None,
                observed_primitive=None,
                expected_intent=case.expected_intent,
                expected_primitive=case.expected_primitive,
                attempts=attempts,
                error=msg[:200],
                notes=["provider exhausted or non-retryable"],
                canonicalization="UNKNOWN",
            )
    return RunScore(
        case_id=case.id,
        run=run,
        utterance=case.utterance,
        category=case.category,
        ok=False,
        verdict="UNKNOWN",
        severity="S2",
        primary_root="E_PROVIDER_TRANSPORT",
        observed_intent=None,
        observed_primitive=None,
        expected_intent=case.expected_intent,
        expected_primitive=case.expected_primitive,
        attempts=attempts,
        error=msg[:200],
        canonicalization="UNKNOWN",
    )


def classify_case_variance(scores: list[RunScore]) -> VarianceClass:
    if not scores:
        return "UNSTABLE_BUT_SAFE"
    unsafe = any(s.severity in {"S3", "S4"} or s.verdict == "UNSAFE" for s in scores)
    if unsafe:
        return "UNSAFE_VARIANCE"
    all_correct = all(s.verdict == "CORRECT" and s.ok for s in scores)
    if all_correct:
        return "STABLE_CORRECT"
    all_safe_abs = all(s.verdict == "SAFE_ABSTENTION" and s.ok for s in scores)
    if all_safe_abs:
        return "STABLE_SAFE_ABSTENTION"
    # mix of correct / safe abstention / soft coverage — no S3/S4
    safeish = all(
        s.severity in {"S0", "S1", "S2"} and s.verdict != "UNSAFE" for s in scores
    )
    if safeish:
        # if every run ok and same soft class
        if all(s.ok for s in scores) and len({s.verdict for s in scores}) == 1:
            if scores[0].verdict == "CORRECT":
                return "STABLE_CORRECT"
            if scores[0].verdict == "SAFE_ABSTENTION":
                return "STABLE_SAFE_ABSTENTION"
        return "UNSTABLE_BUT_SAFE"
    return "UNSTABLE_BUT_SAFE"


def aggregate_report(case_scores: dict[str, list[RunScore]]) -> dict[str, Any]:
    variance_counts = {
        "STABLE_CORRECT": 0,
        "STABLE_SAFE_ABSTENTION": 0,
        "UNSTABLE_BUT_SAFE": 0,
        "UNSAFE_VARIANCE": 0,
    }
    severity_runs = {"S0": 0, "S1": 0, "S2": 0, "S3": 0, "S4": 0}
    by_category: dict[str, dict[str, int]] = {}
    for case_id, runs in case_scores.items():
        v = classify_case_variance(runs)
        variance_counts[v] += 1
        cat = runs[0].category if runs else "unknown"
        bucket = by_category.setdefault(
            cat, {"STABLE_CORRECT": 0, "UNSTABLE_BUT_SAFE": 0, "UNSAFE_VARIANCE": 0, "STABLE_SAFE_ABSTENTION": 0}
        )
        bucket[v] += 1
        for r in runs:
            severity_runs[r.severity] = severity_runs.get(r.severity, 0) + 1
    n_cases = max(len(case_scores), 1)
    return {
        "cases": n_cases,
        "variance_counts": variance_counts,
        "STABLE_CORRECT_RATE": variance_counts["STABLE_CORRECT"] / n_cases,
        "STABLE_SAFE_ABSTENTION_RATE": variance_counts["STABLE_SAFE_ABSTENTION"] / n_cases,
        "UNSTABLE_BUT_SAFE_RATE": variance_counts["UNSTABLE_BUT_SAFE"] / n_cases,
        "UNSAFE_VARIANCE_RATE": variance_counts["UNSAFE_VARIANCE"] / n_cases,
        "severity_runs": severity_runs,
        "by_category": by_category,
    }
