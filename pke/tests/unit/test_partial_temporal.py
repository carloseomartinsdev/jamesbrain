"""Testes unitários — TemporalKnowledge e membership."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from pke.domain import (
    EventStatus,
    OccurrenceStatus,
    RelationToReference,
    TemporalKnowledge,
    TemporalUnknownReason,
    TimePrecision,
    TimeValue,
)
from pke.interpretation import IrTime
from pke.resolution import InsufficientTemporalContextError, TemporalContext, TemporalResolver
from pke.domain import RelativeDay, UserContext
from pke.query.spec import TimeRange
from pke.temporal.membership import TemporalMembership, range_membership

FORTALEZA = ZoneInfo("America/Fortaleza")
REF = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)


def _ctx(status: EventStatus | None = None) -> TemporalContext:
    return TemporalContext(
        user=UserContext(user_id="u1", timezone="America/Fortaleza"),
        event_status=status,
        reference_at=REF,
    )


def test_exact_time_still_resolves() -> None:
    tk = TemporalResolver().resolve(
        IrTime(original_text="hoje", relative_day=RelativeDay.TODAY),
        _ctx(EventStatus.COMPLETED),
    )
    assert tk.has_calendar_anchor()
    assert tk.calendar is not None
    assert tk.calendar.date == dt.date(2026, 9, 1)


def test_past_unknown_not_provided() -> None:
    tk = TemporalResolver().resolve(
        IrTime(original_text=""),
        _ctx(EventStatus.COMPLETED),
    )
    assert tk.kind.value == "partial"
    assert tk.unknown_reason is TemporalUnknownReason.NOT_PROVIDED
    assert not tk.has_calendar_anchor()


def test_forgotten_distinct_from_not_provided() -> None:
    forgotten = TemporalResolver().resolve(
        IrTime(
            original_text="não lembro",
            unknown_reason=TemporalUnknownReason.FORGOTTEN,
            relation_to_reference=RelationToReference.BEFORE,
            occurrence_status=OccurrenceStatus.HAPPENED,
        ),
        _ctx(EventStatus.COMPLETED),
    )
    not_provided = TemporalResolver().resolve(IrTime(original_text=""), _ctx(EventStatus.COMPLETED))
    assert forgotten.unknown_reason is TemporalUnknownReason.FORGOTTEN
    assert not_provided.unknown_reason is TemporalUnknownReason.NOT_PROVIDED


def test_future_unknown_planned() -> None:
    tk = TemporalResolver().resolve(
        IrTime(
            original_text="",
            relation_to_reference=RelationToReference.AFTER,
            occurrence_status=OccurrenceStatus.PLANNED,
        ),
        _ctx(EventStatus.SCHEDULED),
    )
    assert tk.relation_to_reference is RelationToReference.AFTER
    assert tk.occurrence_status is OccurrenceStatus.PLANNED


def test_partial_month_interval() -> None:
    tk = TemporalResolver().resolve(
        IrTime(original_text="agosto", partial_month=8),
        _ctx(EventStatus.COMPLETED),
    )
    assert tk.kind.value == "interval"
    assert tk.interval_start == dt.date(2026, 8, 1)
    assert tk.interval_end == dt.date(2026, 8, 31)


def test_range_membership_true_false_unknown() -> None:
    tr = TimeRange(
        start=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 10, 1, tzinfo=FORTALEZA),
    )
    inside = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="hoje",
            date=dt.date(2026, 9, 15),
            precision=TimePrecision.DAY,
            timezone="America/Fortaleza",
        )
    )
    outside = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="ago",
            date=dt.date(2026, 8, 15),
            precision=TimePrecision.DAY,
            timezone="America/Fortaleza",
        )
    )
    partial = TemporalKnowledge.partial_past("x")
    assert range_membership(inside, tr) is TemporalMembership.MATCH
    assert range_membership(outside, tr) is TemporalMembership.NO_MATCH
    assert range_membership(partial, tr) is TemporalMembership.UNKNOWN


def test_scheduled_without_calendar_still_blocks() -> None:
    with pytest.raises(InsufficientTemporalContextError):
        TemporalResolver().resolve(IrTime(original_text=""), _ctx(EventStatus.SCHEDULED))
