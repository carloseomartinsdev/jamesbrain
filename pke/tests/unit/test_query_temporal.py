from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from pke.domain import UserContext
from pke.interpretation import IrQueryTime, RelativePeriod
from pke.resolution import (
    InsufficientTemporalContextError,
    QueryTemporalContext,
    QueryTemporalResolver,
    TemporalConflictError,
    WeekStart,
)

FORTALEZA = ZoneInfo("America/Fortaleza")
HONOLULU = ZoneInfo("Pacific/Honolulu")
NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)


def _ctx(tz: str = "America/Fortaleza", now: dt.datetime = NOW) -> QueryTemporalContext:
    return QueryTemporalContext(
        user=UserContext(user_id="u1", timezone=tz, now=now),
        reference_at=now,
        week_start=WeekStart.MONDAY,
    )


def test_now_half_open_exact_instant() -> None:
    resolved = QueryTemporalResolver().resolve(
        IrQueryTime(relative_period=RelativePeriod.NOW, original_text="agora"),
        _ctx(),
    )
    assert resolved is not None
    assert resolved.start == NOW
    assert resolved.end == NOW + dt.timedelta(microseconds=1)


def test_this_month_half_open() -> None:
    resolved = QueryTemporalResolver().resolve(
        IrQueryTime(relative_period=RelativePeriod.THIS_MONTH),
        _ctx(),
    )
    assert resolved is not None
    assert resolved.start == dt.datetime(2026, 9, 1, tzinfo=FORTALEZA)
    assert resolved.end == dt.datetime(2026, 10, 1, tzinfo=FORTALEZA)
    assert resolved.start <= NOW < resolved.end


def test_last_month() -> None:
    resolved = QueryTemporalResolver().resolve(
        IrQueryTime(relative_period=RelativePeriod.LAST_MONTH),
        _ctx(),
    )
    assert resolved is not None
    assert resolved.start == dt.datetime(2026, 8, 1, tzinfo=FORTALEZA)
    assert resolved.end == dt.datetime(2026, 9, 1, tzinfo=FORTALEZA)


def test_this_week_monday_policy() -> None:
    # terça 01/09/2026
    resolved = QueryTemporalResolver().resolve(
        IrQueryTime(relative_period=RelativePeriod.THIS_WEEK),
        _ctx(),
    )
    assert resolved is not None
    assert resolved.start == dt.datetime(2026, 8, 31, tzinfo=FORTALEZA)
    assert resolved.end == dt.datetime(2026, 9, 7, tzinfo=FORTALEZA)


def test_last_week_monday_policy() -> None:
    resolved = QueryTemporalResolver().resolve(
        IrQueryTime(relative_period=RelativePeriod.LAST_WEEK),
        _ctx(),
    )
    assert resolved is not None
    assert resolved.start == dt.datetime(2026, 8, 24, tzinfo=FORTALEZA)
    assert resolved.end == dt.datetime(2026, 8, 31, tzinfo=FORTALEZA)


def test_explicit_datetime_range() -> None:
    start = dt.datetime(2026, 9, 1, tzinfo=FORTALEZA)
    end = dt.datetime(2026, 10, 1, tzinfo=FORTALEZA)
    resolved = QueryTemporalResolver().resolve(
        IrQueryTime(start=start, end=end),
        _ctx(),
    )
    assert resolved == type(resolved)(start=start, end=end) if resolved else None
    assert resolved is not None
    assert resolved.start == start
    assert resolved.end == end


def test_explicit_date_range_exclusive_end() -> None:
    resolved = QueryTemporalResolver().resolve(
        IrQueryTime(date_from=dt.date(2026, 9, 1), date_to=dt.date(2026, 10, 1)),
        _ctx(),
    )
    assert resolved is not None
    assert resolved.start == dt.datetime(2026, 9, 1, tzinfo=FORTALEZA)
    assert resolved.end == dt.datetime(2026, 10, 1, tzinfo=FORTALEZA)


def test_date_to_excludes_that_civil_day() -> None:
    """date_to=2026-09-03 → fim 03/09 00:00; o dia 03 não participa."""
    resolved = QueryTemporalResolver().resolve(
        IrQueryTime(date_from=dt.date(2026, 9, 1), date_to=dt.date(2026, 9, 3)),
        _ctx(),
    )
    assert resolved is not None
    assert resolved.start == dt.datetime(2026, 9, 1, tzinfo=FORTALEZA)
    assert resolved.end == dt.datetime(2026, 9, 3, tzinfo=FORTALEZA)
    day_three = dt.datetime(2026, 9, 3, tzinfo=FORTALEZA)
    assert not (resolved.start <= day_three < resolved.end)


def test_linguistic_inclusive_days_use_next_exclusive_date() -> None:
    """“de 1 a 3 de setembro” (três dias) chega como date_to=04."""
    resolved = QueryTemporalResolver().resolve(
        IrQueryTime(date_from=dt.date(2026, 9, 1), date_to=dt.date(2026, 9, 4)),
        _ctx(),
    )
    assert resolved is not None
    start = dt.datetime(2026, 9, 1, tzinfo=FORTALEZA)
    last_day = dt.datetime(2026, 9, 3, tzinfo=FORTALEZA)
    exclusive_end = dt.datetime(2026, 9, 4, tzinfo=FORTALEZA)
    assert resolved.start == start
    assert resolved.end == exclusive_end
    assert resolved.start <= start < resolved.end
    assert resolved.start <= last_day < resolved.end
    assert not (resolved.start <= exclusive_end < resolved.end)


def test_timezone_afternoon_does_not_cross_month() -> None:
    """15:00 Fortaleza = 08:00 Honolulu no mesmo 01/09 — não prova fronteira."""
    afternoon = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)
    assert afternoon.astimezone(HONOLULU).date() == dt.date(2026, 9, 1)
    hon = QueryTemporalResolver().resolve(
        IrQueryTime(relative_period=RelativePeriod.THIS_MONTH),
        _ctx("Pacific/Honolulu", afternoon),
    )
    assert hon is not None
    assert hon.start == dt.datetime(2026, 9, 1, tzinfo=HONOLULU)


def test_timezone_civil_date_crosses_month_boundary() -> None:
    """05:00 Fortaleza → 22:00 de 31/08 em Honolulu. Mês civil do usuário."""
    instant = dt.datetime(2026, 9, 1, 5, 0, tzinfo=FORTALEZA)
    assert instant.astimezone(HONOLULU) == dt.datetime(2026, 8, 31, 22, 0, tzinfo=HONOLULU)
    forte = QueryTemporalResolver().resolve(
        IrQueryTime(relative_period=RelativePeriod.THIS_MONTH),
        _ctx("America/Fortaleza", instant),
    )
    hon = QueryTemporalResolver().resolve(
        IrQueryTime(relative_period=RelativePeriod.THIS_MONTH),
        _ctx("Pacific/Honolulu", instant),
    )
    assert forte is not None and hon is not None
    assert forte.start == dt.datetime(2026, 9, 1, tzinfo=FORTALEZA)
    assert forte.end == dt.datetime(2026, 10, 1, tzinfo=FORTALEZA)
    assert hon.start == dt.datetime(2026, 8, 1, tzinfo=HONOLULU)
    assert hon.end == dt.datetime(2026, 9, 1, tzinfo=HONOLULU)


def test_relative_and_explicit_conflict() -> None:
    with pytest.raises(TemporalConflictError):
        QueryTemporalResolver().resolve(
            IrQueryTime(
                relative_period=RelativePeriod.THIS_MONTH,
                start=NOW,
                end=NOW + dt.timedelta(days=1),
            ),
            _ctx(),
        )


def test_empty_query_time_insufficient() -> None:
    with pytest.raises(InsufficientTemporalContextError):
        QueryTemporalResolver().resolve(IrQueryTime(), _ctx())
