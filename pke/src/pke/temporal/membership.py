"""Predicado temporal ternário: MATCH | NO_MATCH | UNKNOWN.

I11.16.2 / I11.16.3 — shared membership primitives with explicit runtime roles.

Occurrence / observation / assertion (coarse window):

    fact_possible_window ⊆ query  → MATCH
    fact_possible_window ∩ query = ∅ → NO_MATCH
    otherwise → UNKNOWN

Validity interval (Relation / explicit valid_* — query fully covered):

    validity covers query  → MATCH
    validity disjoint query → NO_MATCH
    otherwise → UNKNOWN

Roles are runtime-only (not persisted). Derive via ``derive_temporal_membership_role``.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from zoneinfo import ZoneInfo

from pke.domain.temporal_knowledge import TemporalGranularity, TemporalKind, TemporalKnowledge
from pke.domain.value_objects import TimePrecision, TimeValue
from pke.query.spec import TimeRange


class TemporalMembership(StrEnum):
    MATCH = "match"
    NO_MATCH = "no_match"
    UNKNOWN = "unknown"


class TemporalMembershipRole(StrEnum):
    """Runtime membership role — not persisted (I11.16.1 / I11.16.3).

    Roles share vocabulary and ternary results; they do **not** share interpretation:

    - OCCURRENCE_WINDOW: Event occurred sometime in F
    - OBSERVATION_SCOPE: Measurement/State observed sometime in F
    - ASSERTION_SCOPE: Attribute (or similar) asserted sometime in F
    - VALIDITY_INTERVAL: fact held throughout / covers query (Relation valid_*)
    """

    OCCURRENCE_WINDOW = "occurrence_window"
    OBSERVATION_SCOPE = "observation_scope"
    ASSERTION_SCOPE = "assertion_scope"
    VALIDITY_INTERVAL = "validity_interval"


_COARSE_WINDOW_ROLES = frozenset(
    {
        TemporalMembershipRole.OCCURRENCE_WINDOW,
        TemporalMembershipRole.OBSERVATION_SCOPE,
        TemporalMembershipRole.ASSERTION_SCOPE,
    }
)

_CALENDAR_WINDOW_GRAN = frozenset(
    {
        TemporalGranularity.YEAR,
        TemporalGranularity.MONTH,
        TemporalGranularity.DAY,
        TemporalGranularity.WEEK,
    }
)

# Deterministic (primitive, field_path) → role. Reconstructible after reload.
_ROLE_BY_PRIMITIVE_PATH: dict[tuple[str, str], TemporalMembershipRole] = {
    ("event", "temporal"): TemporalMembershipRole.OCCURRENCE_WINDOW,
    ("measurement", "temporal"): TemporalMembershipRole.OBSERVATION_SCOPE,
    ("measurement", "observed_at"): TemporalMembershipRole.OBSERVATION_SCOPE,
    ("attribute", "temporal"): TemporalMembershipRole.ASSERTION_SCOPE,
    ("relation", "temporal"): TemporalMembershipRole.VALIDITY_INTERVAL,
    ("relation", "valid_from"): TemporalMembershipRole.VALIDITY_INTERVAL,
    ("relation", "valid_to"): TemporalMembershipRole.VALIDITY_INTERVAL,
    ("relation", "termination_temporal"): TemporalMembershipRole.OBSERVATION_SCOPE,
    ("state", "temporal"): TemporalMembershipRole.OBSERVATION_SCOPE,
    ("state", "valid_from"): TemporalMembershipRole.VALIDITY_INTERVAL,
    ("state", "valid_to"): TemporalMembershipRole.VALIDITY_INTERVAL,
}


def derive_temporal_membership_role(
    primitive: str,
    field_path: str = "temporal",
) -> TemporalMembershipRole:
    """Deterministic runtime role from primitive + field path — no persistence."""
    key = (primitive.strip().lower(), field_path.strip().lower())
    role = _ROLE_BY_PRIMITIVE_PATH.get(key)
    if role is None:
        raise ValueError(f"no temporal membership role for {primitive!r}.{field_path!r}")
    return role


def calendar_instant(time: TimeValue) -> dt.datetime | None:
    if time.instant is not None:
        return time.instant
    if time.date is not None:
        zone = ZoneInfo(time.timezone) if time.timezone else dt.UTC
        return dt.datetime.combine(time.date, dt.time.min, tzinfo=zone)
    if time.period_start is not None:
        return time.period_start
    return None


def temporal_instant(temporal: TemporalKnowledge) -> dt.datetime | None:
    """Best-effort point for sorting / display — not membership authority."""
    if temporal.calendar is None:
        return None
    return calendar_instant(temporal.calendar)


def _zone(temporal: TemporalKnowledge) -> ZoneInfo:
    if temporal.calendar and temporal.calendar.timezone:
        return ZoneInfo(temporal.calendar.timezone)
    return dt.UTC


def _exact_instant(temporal: TemporalKnowledge) -> dt.datetime | None:
    """True instant evidence only — never DAY midnight as INSTANT."""
    gran = temporal.calendar_granularity()
    cal = temporal.calendar
    if cal is None or cal.instant is None:
        return None
    if gran is TemporalGranularity.INSTANT:
        return cal.instant
    if cal.precision is TimePrecision.MINUTE:
        return cal.instant
    return None


def _inclusive_dates_to_half_open(
    start_date: dt.date, end_date: dt.date, zone: ZoneInfo
) -> tuple[dt.datetime, dt.datetime]:
    """Stored inclusive calendar end-day → half-open [start, end_exclusive)."""
    start = dt.datetime.combine(start_date, dt.time.min, tzinfo=zone)
    end = dt.datetime.combine(end_date + dt.timedelta(days=1), dt.time.min, tzinfo=zone)
    return start, end


def occurrence_possible_window(
    temporal: TemporalKnowledge,
) -> tuple[dt.datetime, dt.datetime] | None:
    """Derive half-open possible occurrence/observation/assertion window [start, end)."""
    zone = _zone(temporal)
    gran = temporal.calendar_granularity()

    if (
        temporal.interval_start is not None
        and temporal.interval_end is not None
        and gran in _CALENDAR_WINDOW_GRAN
    ):
        return _inclusive_dates_to_half_open(
            temporal.interval_start, temporal.interval_end, zone
        )

    cal = temporal.calendar
    if cal is not None:
        if cal.recurrence is not None:
            return None
        if cal.precision in {TimePrecision.APPROX_DAY, TimePrecision.DAY_PERIOD}:
            return None
        if cal.precision is TimePrecision.RECURRING:
            return None
        if cal.period_start is not None and cal.period_end is not None:
            if cal.period_start < cal.period_end:
                return cal.period_start, cal.period_end
            return None
        if gran is TemporalGranularity.DAY or (
            cal.precision is TimePrecision.DAY and (cal.date is not None or cal.instant is not None)
        ):
            day = cal.date
            if day is None and cal.instant is not None:
                day = cal.instant.date()
            if day is not None:
                start = dt.datetime.combine(day, dt.time.min, tzinfo=zone)
                return start, start + dt.timedelta(days=1)
        return None

    if (
        temporal.kind is TemporalKind.INTERVAL
        and temporal.interval_start is not None
        and temporal.interval_end is not None
    ):
        return _inclusive_dates_to_half_open(
            temporal.interval_start, temporal.interval_end, zone
        )

    return None


def _coarse_window_membership(
    fact_start: dt.datetime,
    fact_end: dt.datetime,
    time_range: TimeRange,
) -> TemporalMembership:
    """Occurrence/observation/assertion: F ⊆ Q / disjoint / otherwise."""
    q_start, q_end = time_range.start, time_range.end
    if fact_start >= q_start and fact_end <= q_end:
        return TemporalMembership.MATCH
    if fact_end <= q_start or fact_start >= q_end:
        return TemporalMembership.NO_MATCH
    return TemporalMembership.UNKNOWN


def validity_interval_membership(
    start: dt.datetime | None,
    end: dt.datetime | None,
    time_range: TimeRange,
    *,
    open_ended: bool = False,
) -> TemporalMembership:
    """Shared validity semantics (Relation held_during).

    MATCH only when the validity interval **covers the full query** (VALID_THROUGHOUT).
    Partial overlap → UNKNOWN (EXISTS_DURING vs VALID_THROUGHOUT not distinguished in QueryIR).
    Never infers endpoints from recorded_at / created_at.
    """
    if start is None and end is None:
        return TemporalMembership.UNKNOWN
    if end is not None and time_range.start >= end:
        return TemporalMembership.NO_MATCH
    if start is not None and time_range.end <= start:
        return TemporalMembership.NO_MATCH
    if start is not None and end is not None:
        if start <= time_range.start and end >= time_range.end:
            return TemporalMembership.MATCH
        if end <= time_range.start or start >= time_range.end:
            return TemporalMembership.NO_MATCH
        return TemporalMembership.UNKNOWN
    if start is not None and open_ended and start <= time_range.start:
        return TemporalMembership.MATCH
    return TemporalMembership.UNKNOWN


def _validity_bounds_from_temporal(
    temporal: TemporalKnowledge,
) -> tuple[dt.datetime | None, dt.datetime | None]:
    """Best calendar bounds for VALIDITY_INTERVAL when only TemporalKnowledge is available."""
    zone = _zone(temporal)
    if temporal.interval_start is not None and temporal.interval_end is not None:
        start, end = _inclusive_dates_to_half_open(
            temporal.interval_start, temporal.interval_end, zone
        )
        return start, end
    cal = temporal.calendar
    if cal is not None:
        if cal.period_start is not None and cal.period_end is not None:
            return cal.period_start, cal.period_end
        if cal.instant is not None and temporal.calendar_granularity() is TemporalGranularity.INSTANT:
            return cal.instant, cal.instant + dt.timedelta(microseconds=1)
        if cal.date is not None:
            start = dt.datetime.combine(cal.date, dt.time.min, tzinfo=zone)
            return start, start + dt.timedelta(days=1)
    return None, None


def _coarse_role_membership(
    temporal: TemporalKnowledge, time_range: TimeRange
) -> TemporalMembership:
    if temporal.kind is TemporalKind.HABITUAL:
        return TemporalMembership.UNKNOWN
    if temporal.calendar is not None and temporal.calendar.recurrence is not None:
        return TemporalMembership.UNKNOWN

    instant = _exact_instant(temporal)
    if instant is not None:
        if time_range.start <= instant < time_range.end:
            return TemporalMembership.MATCH
        return TemporalMembership.NO_MATCH

    if temporal.calendar_granularity() is TemporalGranularity.INSTANT:
        return TemporalMembership.UNKNOWN

    window = occurrence_possible_window(temporal)
    if window is None:
        return TemporalMembership.UNKNOWN

    return _coarse_window_membership(window[0], window[1], time_range)


def range_membership(
    temporal: TemporalKnowledge,
    time_range: TimeRange,
    *,
    role: TemporalMembershipRole = TemporalMembershipRole.OCCURRENCE_WINDOW,
) -> TemporalMembership:
    """TemporalKnowledge × TimeRange → MATCH | NO_MATCH | UNKNOWN.

    Callers with known primitive context should pass ``role=`` explicitly
    (or via ``derive_temporal_membership_role``). Default OCCURRENCE_WINDOW remains
    for Event compatibility.

    Never uses TimePrecision.PARTIAL or storage zero-padding as semantic authority.
    Never infers role from range shape alone.
    """
    if role is TemporalMembershipRole.VALIDITY_INTERVAL:
        start, end = _validity_bounds_from_temporal(temporal)
        return validity_interval_membership(start, end, time_range, open_ended=False)

    if role in _COARSE_WINDOW_ROLES:
        return _coarse_role_membership(temporal, time_range)

    return TemporalMembership.UNKNOWN


def sort_key(temporal: TemporalKnowledge) -> tuple[int, str]:
    """Known times ordered; unknown segregated (deterministic)."""
    instant = temporal_instant(temporal)
    if instant is not None:
        return (0, instant.isoformat())
    if temporal.interval_start is not None:
        return (1, temporal.interval_start.isoformat())
    return (2, temporal.original_text)
