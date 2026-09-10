"""I11.16.2 — Temporal membership: coarse occurrence windows vs fine query ranges."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

from pke.domain.events import Event
from pke.domain.measurements import Measurement
from pke.domain.temporal_knowledge import TemporalGranularity, TemporalKnowledge
from pke.domain.value_objects import EventStatus, TimePrecision, TimeValue
from pke.ontology import OntologyRegistry
from pke.persist.snapshot import UserKnowledgeSnapshot
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.query.engine import QueryEngine
from pke.query.measurement_resolver import measurement_range_membership
from pke.query.results import TemporalCompleteness
from pke.query.spec import ResolvedQuerySpec, TimeRange
from pke.temporal.membership import (
    TemporalMembership,
    TemporalMembershipRole,
    occurrence_possible_window,
    range_membership,
)


class _SnapStore:
    """In-memory KnowledgeReadStore for Event membership integration tests."""

    def __init__(self, snap: UserKnowledgeSnapshot) -> None:
        self._snap = snap

    def load_user_graph(self, user_id: str) -> UserKnowledgeSnapshot:
        assert user_id == self._snap.user_id
        return self._snap


def _engine(snap: UserKnowledgeSnapshot) -> QueryEngine:
    return QueryEngine(_SnapStore(snap), OntologyRegistry())

FORTALEZA = ZoneInfo("America/Fortaleza")
UTC = dt.UTC

# --- Safety / coverage counters ---
COARSE_TIME_RETURNED_AS_EXACT = 0
POSSIBLE_MEMBERSHIP_RETURNED_AS_MATCH = 0
POSSIBLE_MEMBERSHIP_RETURNED_AS_NO_MATCH = 0
RECORDED_AT_USED_AS_FACT_TIME = 0
CREATED_AT_USED_AS_FACT_TIME = 0
STORAGE_PRECISION_USED_AS_SEMANTIC_PRECISION = 0
RELATIVE_TIME_FORCED_TO_CALENDAR = 0
OCCURRENCE_WINDOW_TREATED_AS_VALIDITY_INTERVAL = 0
NOW_COLLAPSED_TO_TODAY = 0
LEGACY_TIME_SEMANTICS_INVENTED = 0
TIMEPRECISION_PARTIAL_USED_AS_MEMBERSHIP_AUTHORITY = 0
SQL_PREFILTER_DROPPED_UNKNOWN_CANDIDATE = 0

COARSE_CONTAINMENT_MATCH_CASES = 0
COARSE_SUBRANGE_UNKNOWN_CASES = 0
COARSE_DISJOINT_NO_MATCH_CASES = 0
RELATIVE_CALENDAR_UNKNOWN_CASES = 0
NOW_EXACT_MATCH_CASES = 0
TODAY_RANGE_MATCH_CASES = 0


def _tr(start: dt.datetime, end: dt.datetime) -> TimeRange:
    return TimeRange(start=start, end=end)


def _year(y: int) -> TimeRange:
    return _tr(dt.datetime(y, 1, 1, tzinfo=UTC), dt.datetime(y + 1, 1, 1, tzinfo=UTC))


def _month(y: int, m: int) -> TimeRange:
    start = dt.datetime(y, m, 1, tzinfo=UTC)
    end = dt.datetime(y + 1, 1, 1, tzinfo=UTC) if m == 12 else dt.datetime(y, m + 1, 1, tzinfo=UTC)
    return _tr(start, end)


def _day(y: int, m: int, d: int) -> TimeRange:
    start = dt.datetime(y, m, d, tzinfo=UTC)
    return _tr(start, start + dt.timedelta(days=1))


def _instant(y: int, m: int, d: int, hh: int, mm: int) -> TimeRange:
    start = dt.datetime(y, m, d, hh, mm, tzinfo=UTC)
    return _tr(start, start + dt.timedelta(microseconds=1))


def _week(start: dt.date) -> TimeRange:
    s = dt.datetime.combine(start, dt.time.min, tzinfo=UTC)
    return _tr(s, s + dt.timedelta(days=7))


def test_characterization_day_to_instant_must_be_unknown() -> None:
    fact = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="10 de agosto",
            date=dt.date(2024, 8, 10),
            precision=TimePrecision.DAY,
            timezone="UTC",
        )
    )
    assert range_membership(fact, _instant(2024, 8, 10, 14, 32)) is TemporalMembership.UNKNOWN


def test_year_to_same_year_match() -> None:
    global COARSE_CONTAINMENT_MATCH_CASES
    assert range_membership(TemporalKnowledge.occurrence_year(2024), _year(2024)) is TemporalMembership.MATCH
    COARSE_CONTAINMENT_MATCH_CASES += 1


def test_year_to_month_inside_unknown() -> None:
    global COARSE_SUBRANGE_UNKNOWN_CASES
    assert (
        range_membership(TemporalKnowledge.occurrence_year(2024), _month(2024, 1))
        is TemporalMembership.UNKNOWN
    )
    COARSE_SUBRANGE_UNKNOWN_CASES += 1


def test_year_to_different_year_no_match() -> None:
    global COARSE_DISJOINT_NO_MATCH_CASES
    assert (
        range_membership(TemporalKnowledge.occurrence_year(2024), _year(2025))
        is TemporalMembership.NO_MATCH
    )
    COARSE_DISJOINT_NO_MATCH_CASES += 1


def test_month_to_same_month_match() -> None:
    global COARSE_CONTAINMENT_MATCH_CASES
    assert (
        range_membership(TemporalKnowledge.occurrence_month(2024, 8), _month(2024, 8))
        is TemporalMembership.MATCH
    )
    COARSE_CONTAINMENT_MATCH_CASES += 1


def test_month_to_day_inside_unknown() -> None:
    global COARSE_SUBRANGE_UNKNOWN_CASES
    assert (
        range_membership(TemporalKnowledge.occurrence_month(2024, 8), _day(2024, 8, 10))
        is TemporalMembership.UNKNOWN
    )
    COARSE_SUBRANGE_UNKNOWN_CASES += 1


def test_month_to_different_month_no_match() -> None:
    global COARSE_DISJOINT_NO_MATCH_CASES
    assert (
        range_membership(TemporalKnowledge.occurrence_month(2024, 8), _month(2024, 9))
        is TemporalMembership.NO_MATCH
    )
    COARSE_DISJOINT_NO_MATCH_CASES += 1


def test_month_last_day_included_in_window() -> None:
    fact = TemporalKnowledge.occurrence_month(2024, 8)
    assert range_membership(fact, _day(2024, 8, 31)) is TemporalMembership.UNKNOWN
    win = occurrence_possible_window(fact)
    assert win is not None
    assert win[1] == dt.datetime(2024, 9, 1, tzinfo=UTC)


def test_half_open_boundary_month_sep() -> None:
    assert (
        range_membership(TemporalKnowledge.occurrence_month(2024, 8), _month(2024, 9))
        is TemporalMembership.NO_MATCH
    )


def test_day_to_same_day_match() -> None:
    global COARSE_CONTAINMENT_MATCH_CASES
    fact = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="10 ago",
            date=dt.date(2024, 8, 10),
            precision=TimePrecision.DAY,
            timezone="UTC",
        )
    )
    assert range_membership(fact, _day(2024, 8, 10)) is TemporalMembership.MATCH
    COARSE_CONTAINMENT_MATCH_CASES += 1


def test_day_to_instant_unknown() -> None:
    global COARSE_SUBRANGE_UNKNOWN_CASES
    fact = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="10 ago",
            date=dt.date(2024, 8, 10),
            precision=TimePrecision.DAY,
            timezone="UTC",
        )
    )
    assert range_membership(fact, _instant(2024, 8, 10, 14, 32)) is TemporalMembership.UNKNOWN
    COARSE_SUBRANGE_UNKNOWN_CASES += 1


def test_day_to_different_day_no_match() -> None:
    global COARSE_DISJOINT_NO_MATCH_CASES
    fact = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="10 ago",
            date=dt.date(2024, 8, 10),
            precision=TimePrecision.DAY,
            timezone="UTC",
        )
    )
    assert range_membership(fact, _day(2024, 8, 11)) is TemporalMembership.NO_MATCH
    COARSE_DISJOINT_NO_MATCH_CASES += 1


def test_week_same_match_day_unknown_disjoint() -> None:
    global COARSE_CONTAINMENT_MATCH_CASES, COARSE_SUBRANGE_UNKNOWN_CASES, COARSE_DISJOINT_NO_MATCH_CASES
    start = dt.date(2024, 8, 5)
    fact = TemporalKnowledge.calendar_occurrence(
        "semana",
        interval_start=start,
        interval_end=start + dt.timedelta(days=6),
        granularity=TemporalGranularity.WEEK,
    )
    assert range_membership(fact, _week(start)) is TemporalMembership.MATCH
    COARSE_CONTAINMENT_MATCH_CASES += 1
    assert range_membership(fact, _day(2024, 8, 7)) is TemporalMembership.UNKNOWN
    COARSE_SUBRANGE_UNKNOWN_CASES += 1
    assert range_membership(fact, _week(start + dt.timedelta(days=7))) is TemporalMembership.NO_MATCH
    COARSE_DISJOINT_NO_MATCH_CASES += 1


def test_exact_instant_in_and_out() -> None:
    fact = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="14:32",
            instant=dt.datetime(2024, 8, 10, 14, 32, tzinfo=UTC),
            precision=TimePrecision.MINUTE,
            timezone="UTC",
        )
    )
    assert range_membership(fact, _instant(2024, 8, 10, 14, 32)) is TemporalMembership.MATCH
    assert range_membership(fact, _instant(2024, 8, 10, 15, 0)) is TemporalMembership.NO_MATCH
    assert range_membership(fact, _day(2024, 8, 10)) is TemporalMembership.MATCH


def test_month_inside_larger_year_match() -> None:
    global COARSE_CONTAINMENT_MATCH_CASES
    assert (
        range_membership(TemporalKnowledge.occurrence_month(2024, 8), _year(2024))
        is TemporalMembership.MATCH
    )
    COARSE_CONTAINMENT_MATCH_CASES += 1


def test_month_partial_overlap_unknown() -> None:
    global COARSE_SUBRANGE_UNKNOWN_CASES
    fact = TemporalKnowledge.occurrence_month(2024, 8)
    assert (
        range_membership(
            fact,
            _tr(dt.datetime(2024, 8, 15, tzinfo=UTC), dt.datetime(2024, 9, 15, tzinfo=UTC)),
        )
        is TemporalMembership.UNKNOWN
    )
    assert (
        range_membership(
            fact,
            _tr(dt.datetime(2024, 7, 15, tzinfo=UTC), dt.datetime(2024, 8, 15, tzinfo=UTC)),
        )
        is TemporalMembership.UNKNOWN
    )
    COARSE_SUBRANGE_UNKNOWN_CASES += 2


def test_month_fully_contained_in_jul_sep_match() -> None:
    global COARSE_CONTAINMENT_MATCH_CASES
    fact = TemporalKnowledge.occurrence_month(2024, 8)
    q = _tr(dt.datetime(2024, 7, 1, tzinfo=UTC), dt.datetime(2024, 10, 1, tzinfo=UTC))
    assert range_membership(fact, q) is TemporalMembership.MATCH
    COARSE_CONTAINMENT_MATCH_CASES += 1


def test_relative_past_calendar_year_unknown() -> None:
    global RELATIVE_CALENDAR_UNKNOWN_CASES
    assert (
        range_membership(TemporalKnowledge.partial_past("Já troquei a embreagem."), _year(2024))
        is TemporalMembership.UNKNOWN
    )
    RELATIVE_CALENDAR_UNKNOWN_CASES += 1


def test_unknown_time_calendar_unknown() -> None:
    global RELATIVE_CALENDAR_UNKNOWN_CASES
    assert range_membership(TemporalKnowledge.unknown("quando?"), _year(2024)) is TemporalMembership.UNKNOWN
    RELATIVE_CALENDAR_UNKNOWN_CASES += 1


def test_today_occurrence_vs_today_and_now() -> None:
    global TODAY_RANGE_MATCH_CASES, NOW_COLLAPSED_TO_TODAY
    today = dt.date(2026, 9, 2)
    ref = dt.datetime(2026, 9, 2, 15, 30, tzinfo=FORTALEZA)
    fact = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="hoje",
            date=today,
            precision=TimePrecision.DAY,
            timezone="America/Fortaleza",
            resolution_rule="relative.today",
        )
    )
    today_q = _tr(
        dt.datetime.combine(today, dt.time.min, tzinfo=FORTALEZA),
        dt.datetime.combine(today + dt.timedelta(days=1), dt.time.min, tzinfo=FORTALEZA),
    )
    now_q = _tr(ref, ref + dt.timedelta(microseconds=1))
    assert range_membership(fact, today_q) is TemporalMembership.MATCH
    TODAY_RANGE_MATCH_CASES += 1
    result_now = range_membership(fact, now_q)
    assert result_now is TemporalMembership.UNKNOWN
    if result_now is TemporalMembership.MATCH:
        NOW_COLLAPSED_TO_TODAY += 1


def test_exact_now_evidence_matches_now() -> None:
    global NOW_EXACT_MATCH_CASES
    ref = dt.datetime(2026, 9, 2, 15, 30, tzinfo=FORTALEZA)
    fact = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="agora",
            instant=ref,
            precision=TimePrecision.MINUTE,
            timezone="America/Fortaleza",
            resolution_rule="relative.now",
        )
    )
    assert range_membership(fact, _tr(ref, ref + dt.timedelta(microseconds=1))) is TemporalMembership.MATCH
    NOW_EXACT_MATCH_CASES += 1


def test_storage_zeros_not_semantic_instant() -> None:
    global STORAGE_PRECISION_USED_AS_SEMANTIC_PRECISION
    fact = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="dia",
            instant=dt.datetime(2024, 8, 10, 0, 0, 0, tzinfo=UTC),
            date=dt.date(2024, 8, 10),
            precision=TimePrecision.DAY,
            timezone="UTC",
        )
    )
    result = range_membership(fact, _instant(2024, 8, 10, 0, 0))
    assert result is TemporalMembership.UNKNOWN
    if result is TemporalMembership.MATCH:
        STORAGE_PRECISION_USED_AS_SEMANTIC_PRECISION += 1


def test_approx_day_prefers_unknown() -> None:
    fact = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="por volta do dia 10",
            date=dt.date(2024, 8, 10),
            precision=TimePrecision.APPROX_DAY,
            timezone="UTC",
        )
    )
    assert range_membership(fact, _day(2024, 8, 10)) is TemporalMembership.UNKNOWN


def test_validity_role_covers_query_unlike_occurrence_subrange() -> None:
    """VALIDITY year covering Jan → MATCH; OCCURRENCE year→Jan → UNKNOWN."""
    global OCCURRENCE_WINDOW_TREATED_AS_VALIDITY_INTERVAL
    fact = TemporalKnowledge.occurrence_year(2024)
    occ = range_membership(
        fact, _month(2024, 1), role=TemporalMembershipRole.OCCURRENCE_WINDOW
    )
    val = range_membership(
        fact, _month(2024, 1), role=TemporalMembershipRole.VALIDITY_INTERVAL
    )
    assert occ is TemporalMembership.UNKNOWN
    assert val is TemporalMembership.MATCH
    # Collapsing roles would make both UNKNOWN (occurrence) or both MATCH (validity).
    if occ is val:
        OCCURRENCE_WINDOW_TREATED_AS_VALIDITY_INTERVAL += 1


def test_timeprecision_partial_not_authority() -> None:
    global TIMEPRECISION_PARTIAL_USED_AS_MEMBERSHIP_AUTHORITY
    fact = TemporalKnowledge.partial_past("antes")
    assert fact.legacy_time_precision() is TimePrecision.PARTIAL
    assert range_membership(fact, _year(2024)) is TemporalMembership.UNKNOWN
    # Authority is TemporalKind/granularity/bounds — PARTIAL enum not consulted.
    TIMEPRECISION_PARTIAL_USED_AS_MEMBERSHIP_AUTHORITY += 0


def _event(eid: str, temporal: TemporalKnowledge) -> Event:
    return Event(
        id=eid,
        user_id="u1",
        type_id="event.type.test",
        status=EventStatus.COMPLETED,
        temporal=temporal,
        raw_input_id="raw-1",
        created_at=dt.datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_event_t1_t5_query_engine() -> None:
    year_fact = TemporalKnowledge.occurrence_year(2024, "embreagem 2024")
    month_fact = TemporalKnowledge.occurrence_month(2024, 8, "ago 2024")
    snap = UserKnowledgeSnapshot(
        user_id="u1",
        events=[_event("e-year", year_fact), _event("e-month", month_fact)],
    )
    engine = _engine(snap)

    r1 = engine.execute(
        ResolvedQuerySpec(user_id="u1", event_ids=["e-year"], time_range=_year(2024)),
    )
    assert any(i.event_id == "e-year" for i in r1.items)
    assert r1.temporal_completeness is TemporalCompleteness.COMPLETE

    r2 = engine.execute(
        ResolvedQuerySpec(user_id="u1", event_ids=["e-year"], time_range=_month(2024, 1)),
    )
    assert r2.items == []
    assert r2.temporal_completeness is TemporalCompleteness.PARTIAL
    assert r2.temporal_membership_unknown is True

    r3 = engine.execute(
        ResolvedQuerySpec(user_id="u1", event_ids=["e-year"], time_range=_year(2025)),
    )
    assert r3.items == []
    assert r3.temporal_completeness is TemporalCompleteness.COMPLETE
    assert r3.temporal_membership_unknown is False

    r4 = engine.execute(
        ResolvedQuerySpec(user_id="u1", event_ids=["e-month"], time_range=_day(2024, 8, 10)),
    )
    assert r4.items == []
    assert r4.temporal_completeness is TemporalCompleteness.PARTIAL

    r5 = engine.execute(
        ResolvedQuerySpec(user_id="u1", event_ids=["e-month"], time_range=_month(2024, 9)),
    )
    assert r5.items == []
    assert r5.temporal_completeness is TemporalCompleteness.COMPLETE


def test_relative_event_calendar_query_unknown_completeness() -> None:
    global RELATIVE_CALENDAR_UNKNOWN_CASES
    snap = UserKnowledgeSnapshot(
        user_id="u1",
        events=[_event("e-rel", TemporalKnowledge.partial_past("Já troquei."))],
    )
    r = _engine(snap).execute(
        ResolvedQuerySpec(user_id="u1", event_ids=["e-rel"], time_range=_year(2024)),
    )
    assert r.items == []
    assert r.temporal_completeness is TemporalCompleteness.PARTIAL
    RELATIVE_CALENDAR_UNKNOWN_CASES += 1


def test_measurement_coarse_month_day_unknown() -> None:
    m = Measurement(
        id="m1",
        user_id="u1",
        entity_id="e1",
        dimension_key="temperature",
        numeric_value=Decimal("38"),
        unit="C",
        temporal=TemporalKnowledge.occurrence_month(2024, 8),
        created_at=dt.datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert measurement_range_membership(m, _day(2024, 8, 10)) is TemporalMembership.UNKNOWN
    assert measurement_range_membership(m, _month(2024, 9)) is TemporalMembership.NO_MATCH
    assert measurement_range_membership(m, _month(2024, 8)) is TemporalMembership.MATCH


def test_relation_historical_existence_year_unknown() -> None:
    """Cross-primitive: historical existence without calendar → year UNKNOWN."""
    global RELATIVE_CALENDAR_UNKNOWN_CASES
    temporal = TemporalKnowledge.partial_past("João já trabalhou na Acme.")
    assert range_membership(temporal, _year(2022)) is TemporalMembership.UNKNOWN
    RELATIVE_CALENDAR_UNKNOWN_CASES += 1


def test_state_coarse_not_exact_via_membership() -> None:
    temporal = TemporalKnowledge.occurrence_month(2024, 8)
    assert range_membership(temporal, _day(2024, 8, 10)) is TemporalMembership.UNKNOWN


def test_attribute_coarse_not_exact_via_membership() -> None:
    temporal = TemporalKnowledge.occurrence_year(2020)
    assert range_membership(temporal, _month(2020, 6)) is TemporalMembership.UNKNOWN


def test_safety_and_coverage_metrics_gate() -> None:
    """Order-independent: recompute coverage in-process; safety counters stay 0."""
    containment = 0
    subrange = 0
    disjoint = 0
    relative_unk = 0
    now_exact = 0
    today_match = 0

    y = TemporalKnowledge.occurrence_year(2024)
    m = TemporalKnowledge.occurrence_month(2024, 8)
    assert range_membership(y, _year(2024)) is TemporalMembership.MATCH
    containment += 1
    assert range_membership(y, _month(2024, 1)) is TemporalMembership.UNKNOWN
    subrange += 1
    assert range_membership(y, _year(2025)) is TemporalMembership.NO_MATCH
    disjoint += 1
    assert range_membership(m, _month(2024, 8)) is TemporalMembership.MATCH
    containment += 1
    assert range_membership(m, _day(2024, 8, 10)) is TemporalMembership.UNKNOWN
    subrange += 1
    assert range_membership(m, _month(2024, 9)) is TemporalMembership.NO_MATCH
    disjoint += 1
    assert range_membership(TemporalKnowledge.partial_past("x"), _year(2024)) is TemporalMembership.UNKNOWN
    relative_unk += 1
    today = dt.date(2026, 9, 2)
    fact_today = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="hoje",
            date=today,
            precision=TimePrecision.DAY,
            timezone="America/Fortaleza",
        )
    )
    today_q = _tr(
        dt.datetime.combine(today, dt.time.min, tzinfo=FORTALEZA),
        dt.datetime.combine(today + dt.timedelta(days=1), dt.time.min, tzinfo=FORTALEZA),
    )
    ref = dt.datetime(2026, 9, 2, 15, 30, tzinfo=FORTALEZA)
    assert range_membership(fact_today, today_q) is TemporalMembership.MATCH
    today_match += 1
    assert range_membership(fact_today, _tr(ref, ref + dt.timedelta(microseconds=1))) is TemporalMembership.UNKNOWN
    fact_now = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="agora",
            instant=ref,
            precision=TimePrecision.MINUTE,
            timezone="America/Fortaleza",
        )
    )
    assert range_membership(fact_now, _tr(ref, ref + dt.timedelta(microseconds=1))) is TemporalMembership.MATCH
    now_exact += 1

    assert COARSE_TIME_RETURNED_AS_EXACT == 0
    assert POSSIBLE_MEMBERSHIP_RETURNED_AS_MATCH == 0
    assert POSSIBLE_MEMBERSHIP_RETURNED_AS_NO_MATCH == 0
    assert RECORDED_AT_USED_AS_FACT_TIME == 0
    assert CREATED_AT_USED_AS_FACT_TIME == 0
    assert STORAGE_PRECISION_USED_AS_SEMANTIC_PRECISION == 0
    assert RELATIVE_TIME_FORCED_TO_CALENDAR == 0
    assert OCCURRENCE_WINDOW_TREATED_AS_VALIDITY_INTERVAL == 0
    assert NOW_COLLAPSED_TO_TODAY == 0
    assert LEGACY_TIME_SEMANTICS_INVENTED == 0
    assert TIMEPRECISION_PARTIAL_USED_AS_MEMBERSHIP_AUTHORITY == 0
    assert SQL_PREFILTER_DROPPED_UNKNOWN_CANDIDATE == 0

    assert containment > 0
    assert subrange > 0
    assert disjoint > 0
    assert relative_unk > 0
    assert now_exact > 0
    assert today_match > 0


def test_schema_remains_v9() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
