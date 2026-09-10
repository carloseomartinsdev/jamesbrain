"""Testes unitários — State dimension/value semantics (I11.4.1)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from pke.domain import (
    ConceptKind,
    State,
    TemporalKnowledge,
    TimePrecision,
    TimeValue,
    new_ulid,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.query.results import TemporalCompleteness
from pke.query.state_resolver import resolve_current, resolve_current_by_dimension

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 2, 12, 0, tzinfo=FORTALEZA)


def _state(
    *,
    dimension_key: str,
    value_key: str,
    temporal: TemporalKnowledge | None = None,
    observed_at: dt.datetime | None = None,
    is_current: bool = True,
    payload: object | None = None,
) -> State:
    return State(
        id=new_ulid(),
        user_id="u1",
        entity_id="ent-1",
        dimension_id=core_concept_id(dimension_key),
        dimension_key=dimension_key,
        value_concept_id=core_concept_id(value_key),
        value_key=value_key,
        payload=payload,
        temporal=temporal or TemporalKnowledge.partial_ongoing(),
        observed_at=observed_at or NOW,
        is_current=is_current,
    )


def test_state_value_concepts_are_state_value_kind() -> None:
    registry = OntologyRegistry.with_core_seeds()
    broken = registry.get_by_key("state.value.broken")
    assert broken is not None
    assert broken.kind is ConceptKind.STATE_VALUE
    dim = registry.get_by_id(broken.parent_id or "")
    assert dim is not None
    assert dim.key == "state.operational_condition"


def test_same_dimension_known_ordering_picks_latest() -> None:
    older = _state(
        dimension_key="state.operational_condition",
        value_key="state.value.broken",
        temporal=TemporalKnowledge.from_calendar(
            TimeValue(original_text="2026-09-01", date=dt.date(2026, 9, 1), precision=TimePrecision.DAY)
        ),
        observed_at=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
        is_current=False,
    )
    newer = _state(
        dimension_key="state.operational_condition",
        value_key="state.value.working",
        temporal=TemporalKnowledge.from_calendar(
            TimeValue(original_text="2026-09-05", date=dt.date(2026, 9, 5), precision=TimePrecision.DAY)
        ),
        observed_at=dt.datetime(2026, 9, 5, tzinfo=FORTALEZA),
    )
    result = resolve_current(
        [older, newer],
        dimension_key="state.operational_condition",
    )
    assert result.state is newer
    assert result.completeness is TemporalCompleteness.COMPLETE


def test_same_dimension_unknown_ordering_is_partial() -> None:
    known = _state(
        dimension_key="state.operational_condition",
        value_key="state.value.broken",
        temporal=TemporalKnowledge.from_calendar(
            TimeValue(original_text="2026-09-01", date=dt.date(2026, 9, 1), precision=TimePrecision.DAY)
        ),
    )
    unknown = _state(
        dimension_key="state.operational_condition",
        value_key="state.value.working",
        temporal=TemporalKnowledge.partial_ongoing(),
    )
    result = resolve_current([known, unknown], dimension_key="state.operational_condition")
    assert result.completeness is TemporalCompleteness.PARTIAL
    assert result.indeterminate_count == 1


def test_different_dimensions_coexist_as_current() -> None:
    working = _state(
        dimension_key="state.operational_condition",
        value_key="state.value.working",
    )
    open_state = _state(
        dimension_key="state.openness",
        value_key="state.value.open",
    )
    by_dim = resolve_current_by_dimension([working, open_state], entity_id="ent-1")
    assert by_dim["state.operational_condition"].state is working
    assert by_dim["state.openness"].state is open_state
    assert working.is_current
    assert open_state.is_current


def test_unpaid_and_overdue_are_distinct_values() -> None:
    registry = OntologyRegistry.with_core_seeds()
    unpaid = registry.get_by_key("state.value.unpaid")
    overdue = registry.get_by_key("state.value.overdue")
    assert unpaid is not None and overdue is not None
    assert unpaid.parent_id != overdue.parent_id
    payment = registry.get_by_key("state.payment_status")
    due = registry.get_by_key("state.due_status")
    assert payment is not None and due is not None


def test_depleted_is_availability_not_generic_unavailable() -> None:
    registry = OntologyRegistry.with_core_seeds()
    depleted = registry.get_by_key("state.value.depleted")
    assert depleted is not None
    parent = registry.get_by_id(depleted.parent_id or "")
    assert parent is not None
    assert parent.key == "state.availability"
    assert registry.get_by_key("state.value.unavailable") is None


def test_state_has_no_invented_causal_event() -> None:
    state = _state(
        dimension_key="state.operational_condition",
        value_key="state.value.broken",
    )
    assert state.caused_by_event_id is None
