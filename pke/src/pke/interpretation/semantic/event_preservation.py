"""Event semantic preservation helpers (I12.7.1)."""

from __future__ import annotations

from pke.interpretation.semantic.models import (
    PrimitiveKind,
    ResolutionResult,
    SemanticResolutionOutcome,
)


def event_assertion_present(result: ResolutionResult) -> bool:
    return any(f.primitive is PrimitiveKind.EVENT for f in result.assertions)


def event_semantically_preserved(outcome: SemanticResolutionOutcome) -> bool:
    """True when Event assertion survives as materialized IR or explicit non-materialized."""
    result = outcome.result
    if not event_assertion_present(result):
        return False
    if outcome.ir is not None and outcome.ir.event is not None:
        return True
    return PrimitiveKind.EVENT in result.non_materialized_primitives


def event_false_canonicalization(outcome: SemanticResolutionOutcome) -> bool:
    """True when partial Event was assigned an unrelated wire type (e.g. false event.intent)."""
    if outcome.ir is None or outcome.ir.event is None:
        return False
    result = outcome.result
    concepts = result.concepts
    if concepts.event_type and outcome.ir.event.type.key == concepts.event_type:
        return False
    if concepts.action and outcome.ir.event.action:
        return False
    key = outcome.ir.event.type.key
    if key == "event.intent" and concepts.event_type != "event.intent":
        return True
    return False
