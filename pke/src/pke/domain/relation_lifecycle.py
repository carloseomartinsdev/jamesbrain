"""Lifecycle de Relation — asserção vs término e valid_to epistêmico."""

from __future__ import annotations

import datetime as dt

from pke.domain.temporal_knowledge import TemporalGranularity, TemporalKind, TemporalKnowledge
from pke.domain.value_objects import TimePrecision


def relation_calendar_endpoint(temporal: TemporalKnowledge | None) -> dt.datetime | None:
    """Melhor conhecimento calendário de endpoint — nunca recorded_at."""
    if temporal is None:
        return None
    if temporal.has_calendar_anchor() and temporal.calendar is not None:
        cal = temporal.calendar
        if cal.instant is not None:
            return cal.instant
        if cal.date is not None:
            return dt.datetime.combine(cal.date, dt.time.min, tzinfo=dt.UTC)
    if temporal.interval_end is not None:
        return dt.datetime.combine(temporal.interval_end, dt.time.min, tzinfo=dt.UTC)
    return None


def relation_calendar_start(temporal: TemporalKnowledge | None) -> dt.datetime | None:
    """Melhor conhecimento calendário de início — nunca recorded_at."""
    if temporal is None:
        return None
    if temporal.has_calendar_anchor() and temporal.calendar is not None:
        cal = temporal.calendar
        if cal.instant is not None:
            return cal.instant
        if cal.date is not None:
            return dt.datetime.combine(cal.date, dt.time.min, tzinfo=dt.UTC)
    if temporal.interval_start is not None:
        return dt.datetime.combine(temporal.interval_start, dt.time.min, tzinfo=dt.UTC)
    return None


def termination_calendar_known(temporal: TemporalKnowledge | None) -> bool:
    if temporal is None:
        return False
    if temporal.has_calendar_anchor():
        return True
    if temporal.kind is TemporalKind.INTERVAL and temporal.interval_start and temporal.interval_end:
        return True
    if (
        temporal.granularity is not TemporalGranularity.UNSPECIFIED
        and temporal.interval_start is not None
    ):
        return True
    return temporal.calendar is not None and temporal.calendar.precision in {
        TimePrecision.DAY,
        TimePrecision.MINUTE,
    }
