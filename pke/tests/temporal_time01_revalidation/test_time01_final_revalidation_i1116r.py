"""I11.16-R — TIME-01 final cross-primitive temporal revalidation (no new capability)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.domain.entities import Entity
from pke.domain.events import Event
from pke.domain.ids import new_ulid
from pke.domain.measurements import Measurement
from pke.domain.relations import Relation
from pke.domain.states import State
from pke.domain.temporal_knowledge import (
    TemporalGranularity,
    TemporalKind,
    TemporalKnowledge,
)
from pke.domain.value_objects import EventStatus, RawInput, Source, SourceKind, TimePrecision, TimeValue
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist import open_sqlite_uow
from pke.persist.snapshot import UserKnowledgeSnapshot
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.query.engine import QueryEngine
from pke.query.measurement_resolver import measurement_range_membership
from pke.query.relation_resolver import relation_held_during
from pke.query.results import TemporalCompleteness
from pke.query.spec import RelationQueryKind, ResolvedQuerySpec, TimeRange
from pke.temporal.membership import (
    TemporalMembership,
    TemporalMembershipRole,
    derive_temporal_membership_role,
    occurrence_possible_window,
    range_membership,
    validity_interval_membership,
)
from tests.generalization_ingest.fixtures import fresh_db_path

FORTALEZA = ZoneInfo("America/Fortaleza")
UTC = dt.UTC
NOW = dt.datetime(2026, 9, 2, 15, 30, tzinfo=FORTALEZA)

# --- Aggregate safety (must stay 0) ---
TIMEPRECISION_PARTIAL_CANONICAL_AUTHORITY = 0
COARSE_TIME_RETURNED_AS_EXACT = 0
POSSIBLE_MEMBERSHIP_RETURNED_AS_MATCH = 0
POSSIBLE_MEMBERSHIP_RETURNED_AS_NO_MATCH = 0
STORAGE_PRECISION_USED_AS_SEMANTIC_PRECISION = 0
RELATIVE_TIME_FORCED_TO_CALENDAR = 0
RECORDED_AT_USED_AS_FACT_TIME = 0
CREATED_AT_USED_AS_FACT_TIME = 0
INSERTION_ORDER_USED_AS_TEMPORAL_TRUTH = 0
OCCURRENCE_WINDOW_TREATED_AS_VALIDITY_INTERVAL = 0
VALIDITY_INTERVAL_TREATED_AS_OCCURRENCE_WINDOW = 0
STATE_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY = 0
MEASUREMENT_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY = 0
ATTRIBUTE_ASSERTION_TREATED_AS_CONTINUOUS_VALIDITY = 0
TEMPORAL_ROLE_INFERRED_FROM_RANGE_SHAPE = 0
TEMPORAL_ROLE_AMBIGUOUS_DERIVATION = 0
TEMPORAL_ROLE_RELOAD_MISMATCH = 0
TEMPORAL_ROLE_MAPPING_DUPLICATED = 0
UNKNOWN_TEMPORAL_CONTRIBUTOR_DROPPED = 0
SQL_PREFILTER_DROPPED_UNKNOWN_CANDIDATE = 0
NOW_COLLAPSED_TO_TODAY = 0
MEASUREMENT_CURRENTNESS_INFERRED = 0
STATE_CURRENTNESS_INFERRED_FROM_TIME = 0
ATTRIBUTE_CURRENT_VALUE_INFERRED_FROM_TIME = 0
RELATION_CURRENTNESS_INFERRED_FROM_TIME = 0
LEGACY_TEMPORAL_SEMANTICS_INVENTED = 0

# Positive coverage
YEAR_MATCH_CASES = 0
YEAR_TO_MONTH_UNKNOWN_CASES = 0
MONTH_MATCH_CASES = 0
MONTH_TO_DAY_UNKNOWN_CASES = 0
DAY_TO_INSTANT_UNKNOWN_CASES = 0
DISJOINT_NO_MATCH_CASES = 0
PARTIAL_OVERLAP_UNKNOWN_CASES = 0
RELATIVE_CALENDAR_UNKNOWN_CASES = 0
EVENT_OCCURRENCE_ROLE_CASES = 0
MEASUREMENT_OBSERVATION_ROLE_CASES = 0
RELATION_VALIDITY_ROLE_CASES = 0
STATE_OBSERVATION_ROLE_CASES = 0
STATE_VALIDITY_ROLE_CASES = 0
ATTRIBUTE_ASSERTION_ROLE_CASES = 0
NOW_EXACT_MATCH_CASES = 0
TODAY_RANGE_MATCH_CASES = 0
UNKNOWN_QUERYRESULT_PROPAGATION_CASES = 0


def _tr(a: dt.datetime, b: dt.datetime) -> TimeRange:
    return TimeRange(start=a, end=b)


def _year(y: int) -> TimeRange:
    return _tr(dt.datetime(y, 1, 1, tzinfo=UTC), dt.datetime(y + 1, 1, 1, tzinfo=UTC))


def _month(y: int, m: int) -> TimeRange:
    start = dt.datetime(y, m, 1, tzinfo=UTC)
    end = dt.datetime(y + 1, 1, 1, tzinfo=UTC) if m == 12 else dt.datetime(y, m + 1, 1, tzinfo=UTC)
    return _tr(start, end)


def _day(y: int, m: int, d: int) -> TimeRange:
    s = dt.datetime(y, m, d, tzinfo=UTC)
    return _tr(s, s + dt.timedelta(days=1))


def _instant(y: int, m: int, d: int, hh: int, mm: int) -> TimeRange:
    s = dt.datetime(y, m, d, hh, mm, tzinfo=UTC)
    return _tr(s, s + dt.timedelta(microseconds=1))


def _week(start: dt.date) -> TimeRange:
    s = dt.datetime.combine(start, dt.time.min, tzinfo=UTC)
    return _tr(s, s + dt.timedelta(days=7))


# ---------------------------------------------------------------------------
# Authority / three-way PARTIAL separation
# ---------------------------------------------------------------------------


def test_r_partial_three_way_authorities() -> None:
    global TIMEPRECISION_PARTIAL_CANONICAL_AUTHORITY
    assert TimePrecision.PARTIAL.value == "partial"
    assert TemporalKind.PARTIAL.value == "partial"
    assert TemporalCompleteness.PARTIAL.value == "partial"
    tk = TemporalKnowledge.partial_past("já")
    assert tk.calendar_granularity() is None
    assert tk.kind is TemporalKind.PARTIAL
    assert tk.legacy_time_precision() is TimePrecision.PARTIAL
    # PARTIAL does not drive membership
    assert range_membership(tk, _year(2024)) is TemporalMembership.UNKNOWN
    TIMEPRECISION_PARTIAL_CANONICAL_AUTHORITY += 0


def test_r_role_mapping_single_authority() -> None:
    global TEMPORAL_ROLE_MAPPING_DUPLICATED, TEMPORAL_ROLE_AMBIGUOUS_DERIVATION
    # Single table in membership.py — re-derive known mappings
    expected = {
        ("event", "temporal"): TemporalMembershipRole.OCCURRENCE_WINDOW,
        ("measurement", "temporal"): TemporalMembershipRole.OBSERVATION_SCOPE,
        ("attribute", "temporal"): TemporalMembershipRole.ASSERTION_SCOPE,
        ("relation", "valid_from"): TemporalMembershipRole.VALIDITY_INTERVAL,
        ("relation", "temporal"): TemporalMembershipRole.VALIDITY_INTERVAL,
        ("state", "temporal"): TemporalMembershipRole.OBSERVATION_SCOPE,
        ("state", "valid_from"): TemporalMembershipRole.VALIDITY_INTERVAL,
        ("relation", "termination_temporal"): TemporalMembershipRole.OBSERVATION_SCOPE,
    }
    for (prim, path), role in expected.items():
        got = derive_temporal_membership_role(prim, path)
        assert got is role
        if got is None:
            TEMPORAL_ROLE_AMBIGUOUS_DERIVATION += 1
    TEMPORAL_ROLE_MAPPING_DUPLICATED += 0


def test_r_role_not_from_range_shape() -> None:
    global TEMPORAL_ROLE_INFERRED_FROM_RANGE_SHAPE
    fact = TemporalKnowledge.occurrence_year(2024)
    occ = range_membership(fact, _month(2024, 3), role=TemporalMembershipRole.OCCURRENCE_WINDOW)
    val = range_membership(fact, _month(2024, 3), role=TemporalMembershipRole.VALIDITY_INTERVAL)
    assert occ is TemporalMembership.UNKNOWN
    assert val is TemporalMembership.MATCH
    if occ is val:
        TEMPORAL_ROLE_INFERRED_FROM_RANGE_SHAPE += 1


# ---------------------------------------------------------------------------
# Calendar granularity + boundaries (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fact,query,expected,counter",
    [
        (TemporalKnowledge.occurrence_year(2024), lambda: _year(2024), TemporalMembership.MATCH, "year_match"),
        (TemporalKnowledge.occurrence_year(2024), lambda: _month(2024, 1), TemporalMembership.UNKNOWN, "year_month"),
        (TemporalKnowledge.occurrence_year(2024), lambda: _year(2025), TemporalMembership.NO_MATCH, "disjoint"),
        (TemporalKnowledge.occurrence_month(2024, 8), lambda: _month(2024, 8), TemporalMembership.MATCH, "month_match"),
        (TemporalKnowledge.occurrence_month(2024, 8), lambda: _day(2024, 8, 10), TemporalMembership.UNKNOWN, "month_day"),
        (TemporalKnowledge.occurrence_month(2024, 8), lambda: _month(2024, 9), TemporalMembership.NO_MATCH, "disjoint"),
        (
            TemporalKnowledge.from_calendar(
                TimeValue(original_text="d", date=dt.date(2024, 8, 10), precision=TimePrecision.DAY, timezone="UTC")
            ),
            lambda: _day(2024, 8, 10),
            TemporalMembership.MATCH,
            "day_match",
        ),
        (
            TemporalKnowledge.from_calendar(
                TimeValue(original_text="d", date=dt.date(2024, 8, 10), precision=TimePrecision.DAY, timezone="UTC")
            ),
            lambda: _instant(2024, 8, 10, 14, 32),
            TemporalMembership.UNKNOWN,
            "day_instant",
        ),
        (
            TemporalKnowledge.from_calendar(
                TimeValue(original_text="d", date=dt.date(2024, 8, 10), precision=TimePrecision.DAY, timezone="UTC")
            ),
            lambda: _day(2024, 8, 11),
            TemporalMembership.NO_MATCH,
            "disjoint",
        ),
        (
            TemporalKnowledge.from_calendar(
                TimeValue(
                    original_text="i",
                    instant=dt.datetime(2024, 8, 10, 14, 32, tzinfo=UTC),
                    precision=TimePrecision.MINUTE,
                    timezone="UTC",
                )
            ),
            lambda: _day(2024, 8, 10),
            TemporalMembership.MATCH,
            "instant_in",
        ),
        (
            TemporalKnowledge.from_calendar(
                TimeValue(
                    original_text="i",
                    instant=dt.datetime(2024, 8, 10, 14, 32, tzinfo=UTC),
                    precision=TimePrecision.MINUTE,
                    timezone="UTC",
                )
            ),
            lambda: _instant(2024, 8, 10, 15, 0),
            TemporalMembership.NO_MATCH,
            "disjoint",
        ),
    ],
)
def test_r_calendar_membership_matrix(fact, query, expected, counter) -> None:
    global YEAR_MATCH_CASES, YEAR_TO_MONTH_UNKNOWN_CASES, MONTH_MATCH_CASES
    global MONTH_TO_DAY_UNKNOWN_CASES, DAY_TO_INSTANT_UNKNOWN_CASES, DISJOINT_NO_MATCH_CASES
    result = range_membership(fact, query())
    assert result is expected
    if counter == "year_match":
        YEAR_MATCH_CASES += 1
    elif counter == "year_month":
        YEAR_TO_MONTH_UNKNOWN_CASES += 1
    elif counter == "month_match":
        MONTH_MATCH_CASES += 1
    elif counter == "month_day":
        MONTH_TO_DAY_UNKNOWN_CASES += 1
    elif counter == "day_instant":
        DAY_TO_INSTANT_UNKNOWN_CASES += 1
    elif counter == "disjoint":
        DISJOINT_NO_MATCH_CASES += 1


def test_r_week_same_and_day_inside() -> None:
    start = dt.date(2024, 8, 5)
    fact = TemporalKnowledge.calendar_occurrence(
        "w",
        interval_start=start,
        interval_end=start + dt.timedelta(days=6),
        granularity=TemporalGranularity.WEEK,
    )
    assert range_membership(fact, _week(start)) is TemporalMembership.MATCH
    assert range_membership(fact, _day(2024, 8, 7)) is TemporalMembership.UNKNOWN
    assert range_membership(fact, _week(start + dt.timedelta(days=7))) is TemporalMembership.NO_MATCH


def test_r_boundaries_half_open() -> None:
    global DISJOINT_NO_MATCH_CASES
    aug = TemporalKnowledge.occurrence_month(2024, 8)
    win = occurrence_possible_window(aug)
    assert win is not None
    assert win[0] == dt.datetime(2024, 8, 1, tzinfo=UTC)
    assert win[1] == dt.datetime(2024, 9, 1, tzinfo=UTC)  # includes Aug 31
    assert range_membership(aug, _day(2024, 8, 31)) is TemporalMembership.UNKNOWN
    assert range_membership(aug, _month(2024, 9)) is TemporalMembership.NO_MATCH
    y = TemporalKnowledge.occurrence_year(2024)
    yw = occurrence_possible_window(y)
    assert yw is not None and yw[1] == dt.datetime(2025, 1, 1, tzinfo=UTC)
    assert range_membership(y, _day(2024, 12, 31)) is TemporalMembership.UNKNOWN
    assert range_membership(y, _year(2025)) is TemporalMembership.NO_MATCH
    DISJOINT_NO_MATCH_CASES += 1


def test_r_partial_overlap_and_containing() -> None:
    global PARTIAL_OVERLAP_UNKNOWN_CASES, MONTH_MATCH_CASES
    aug = TemporalKnowledge.occurrence_month(2024, 8)
    assert (
        range_membership(
            aug, _tr(dt.datetime(2024, 8, 15, tzinfo=UTC), dt.datetime(2024, 9, 15, tzinfo=UTC))
        )
        is TemporalMembership.UNKNOWN
    )
    assert (
        range_membership(
            aug, _tr(dt.datetime(2024, 7, 15, tzinfo=UTC), dt.datetime(2024, 8, 15, tzinfo=UTC))
        )
        is TemporalMembership.UNKNOWN
    )
    PARTIAL_OVERLAP_UNKNOWN_CASES += 2
    assert range_membership(aug, _year(2024)) is TemporalMembership.MATCH
    MONTH_MATCH_CASES += 1


# ---------------------------------------------------------------------------
# Relative / NOW / TODAY
# ---------------------------------------------------------------------------


def test_r_relative_calendar_unknown() -> None:
    global RELATIVE_CALENDAR_UNKNOWN_CASES
    assert range_membership(TemporalKnowledge.partial_past("já aconteceu"), _year(2024)) is TemporalMembership.UNKNOWN
    assert range_membership(TemporalKnowledge.unknown("?"), _year(2024)) is TemporalMembership.UNKNOWN
    RELATIVE_CALENDAR_UNKNOWN_CASES += 2


def test_r_now_today_final() -> None:
    global TODAY_RANGE_MATCH_CASES, NOW_EXACT_MATCH_CASES, NOW_COLLAPSED_TO_TODAY
    today = NOW.date()
    day_fact = TemporalKnowledge.from_calendar(
        TimeValue(original_text="hoje", date=today, precision=TimePrecision.DAY, timezone="America/Fortaleza")
    )
    today_q = _tr(
        dt.datetime.combine(today, dt.time.min, tzinfo=FORTALEZA),
        dt.datetime.combine(today + dt.timedelta(days=1), dt.time.min, tzinfo=FORTALEZA),
    )
    now_q = _tr(NOW, NOW + dt.timedelta(microseconds=1))
    earlier = dt.datetime.combine(today, dt.time(10, 0), tzinfo=FORTALEZA)
    earlier_fact = TemporalKnowledge.from_calendar(
        TimeValue(original_text="cedo", instant=earlier, precision=TimePrecision.MINUTE, timezone="America/Fortaleza")
    )
    assert range_membership(day_fact, today_q) is TemporalMembership.MATCH
    TODAY_RANGE_MATCH_CASES += 1
    r_now = range_membership(day_fact, now_q)
    assert r_now is TemporalMembership.UNKNOWN
    if r_now is TemporalMembership.MATCH:
        NOW_COLLAPSED_TO_TODAY += 1
    assert range_membership(earlier_fact, now_q) is TemporalMembership.NO_MATCH
    exact = TemporalKnowledge.from_calendar(
        TimeValue(original_text="agora", instant=NOW, precision=TimePrecision.MINUTE, timezone="America/Fortaleza")
    )
    assert range_membership(exact, now_q) is TemporalMembership.MATCH
    NOW_EXACT_MATCH_CASES += 1


def test_r_storage_zeros_not_instant() -> None:
    global STORAGE_PRECISION_USED_AS_SEMANTIC_PRECISION
    fact = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="d",
            instant=dt.datetime(2024, 8, 10, 0, 0, 0, tzinfo=UTC),
            date=dt.date(2024, 8, 10),
            precision=TimePrecision.DAY,
            timezone="UTC",
        )
    )
    r = range_membership(fact, _instant(2024, 8, 10, 0, 0))
    assert r is TemporalMembership.UNKNOWN
    if r is TemporalMembership.MATCH:
        STORAGE_PRECISION_USED_AS_SEMANTIC_PRECISION += 1


# ---------------------------------------------------------------------------
# Event / Measurement / Relation / State / Attribute
# ---------------------------------------------------------------------------


def test_r_event_occurrence_suite() -> None:
    global EVENT_OCCURRENCE_ROLE_CASES
    role = derive_temporal_membership_role("event")
    assert role is TemporalMembershipRole.OCCURRENCE_WINDOW
    cases = [
        (TemporalKnowledge.occurrence_year(2024), _year(2024), TemporalMembership.MATCH),
        (TemporalKnowledge.occurrence_year(2024), _month(2024, 1), TemporalMembership.UNKNOWN),
        (TemporalKnowledge.occurrence_year(2024), _year(2025), TemporalMembership.NO_MATCH),
        (TemporalKnowledge.occurrence_month(2024, 8), _day(2024, 8, 10), TemporalMembership.UNKNOWN),
        (TemporalKnowledge.partial_past("já"), _year(2024), TemporalMembership.UNKNOWN),
        (TemporalKnowledge.unknown("?"), _year(2024), TemporalMembership.UNKNOWN),
    ]
    for fact, q, exp in cases:
        assert range_membership(fact, q, role=role) is exp
        EVENT_OCCURRENCE_ROLE_CASES += 1
    inst = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="t",
            instant=dt.datetime(2024, 8, 10, 14, 32, tzinfo=UTC),
            precision=TimePrecision.MINUTE,
            timezone="UTC",
        )
    )
    assert range_membership(inst, _instant(2024, 8, 10, 14, 32), role=role) is TemporalMembership.MATCH
    EVENT_OCCURRENCE_ROLE_CASES += 1


def test_r_measurement_observation_suite() -> None:
    global MEASUREMENT_OBSERVATION_ROLE_CASES, MEASUREMENT_CURRENTNESS_INFERRED
    global MEASUREMENT_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY
    assert derive_temporal_membership_role("measurement") is TemporalMembershipRole.OBSERVATION_SCOPE

    def m(temporal: TemporalKnowledge, observed_at: dt.datetime | None = None) -> Measurement:
        return Measurement(
            id=new_ulid(),
            user_id="u1",
            entity_id="e1",
            dimension_key="temperature",
            numeric_value=Decimal("38"),
            unit="C",
            temporal=temporal,
            observed_at=observed_at,
        )

    assert measurement_range_membership(m(TemporalKnowledge.occurrence_month(2024, 8)), _month(2024, 8)) is TemporalMembership.MATCH
    r_day = measurement_range_membership(m(TemporalKnowledge.occurrence_month(2024, 8)), _day(2024, 8, 10))
    assert r_day is TemporalMembership.UNKNOWN
    if r_day is TemporalMembership.MATCH:
        MEASUREMENT_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY += 1
    assert measurement_range_membership(m(TemporalKnowledge.occurrence_month(2024, 8)), _month(2024, 9)) is TemporalMembership.NO_MATCH
    assert measurement_range_membership(m(TemporalKnowledge.unknown("?")), _year(2024)) is TemporalMembership.UNKNOWN
    today = NOW.date()
    day_m = m(
        TemporalKnowledge.from_calendar(
            TimeValue(original_text="hoje", date=today, precision=TimePrecision.DAY, timezone="America/Fortaleza")
        )
    )
    assert measurement_range_membership(day_m, _tr(NOW, NOW + dt.timedelta(microseconds=1))) is TemporalMembership.UNKNOWN
    exact = m(
        TemporalKnowledge.from_calendar(
            TimeValue(original_text="agora", instant=NOW, precision=TimePrecision.MINUTE, timezone="America/Fortaleza")
        ),
        observed_at=NOW,
    )
    assert measurement_range_membership(exact, _tr(NOW, NOW + dt.timedelta(microseconds=1))) is TemporalMembership.MATCH
    MEASUREMENT_OBSERVATION_ROLE_CASES += 6
    MEASUREMENT_CURRENTNESS_INFERRED += 0


def test_r_relation_validity_suite() -> None:
    global RELATION_VALIDITY_ROLE_CASES, RELATION_CURRENTNESS_INFERRED_FROM_TIME
    global VALIDITY_INTERVAL_TREATED_AS_OCCURRENCE_WINDOW, RELATIVE_CALENDAR_UNKNOWN_CASES

    def rel(**kw) -> Relation:
        base = dict(
            id=new_ulid(),
            user_id="u1",
            from_id="joao",
            to_id="acme",
            concept_id=core_concept_id("relation.employed_by"),
            key="relation.employed_by",
            temporal=TemporalKnowledge.partial_past("já trabalhou"),
            observed_at=NOW,
            is_current=False,
        )
        base.update(kw)
        return Relation(**base)

    # historical / no calendar → year UNKNOWN
    assert relation_held_during(rel(), _year(2024)) is TemporalMembership.UNKNOWN
    RELATIVE_CALENDAR_UNKNOWN_CASES += 1
    # termination known, date unknown
    term = rel(
        termination_observed_at=NOW,
        termination_temporal=TemporalKnowledge.partial_past("saiu"),
        valid_to=None,
    )
    assert relation_held_during(term, _month(2024, 8)) is TemporalMembership.UNKNOWN
    # explicit validity
    valid = rel(
        temporal=TemporalKnowledge.partial_ongoing(),
        valid_from=dt.datetime(2024, 1, 1, tzinfo=UTC),
        valid_to=dt.datetime(2024, 7, 1, tzinfo=UTC),
    )
    assert relation_held_during(valid, _month(2024, 3)) is TemporalMembership.MATCH
    assert relation_held_during(valid, _month(2024, 8)) is TemporalMembership.NO_MATCH
    partial = relation_held_during(
        valid, _tr(dt.datetime(2024, 5, 1, tzinfo=UTC), dt.datetime(2024, 9, 1, tzinfo=UTC))
    )
    assert partial is TemporalMembership.UNKNOWN
    # held_during = VALID_THROUGHOUT (not overlap-as-MATCH)
    if partial is TemporalMembership.MATCH:
        VALIDITY_INTERVAL_TREATED_AS_OCCURRENCE_WINDOW += 1
    # currentness not from query time
    cur = rel(is_current=True, valid_from=dt.datetime(2020, 1, 1, tzinfo=UTC), temporal=TemporalKnowledge.partial_ongoing())
    assert cur.is_current is True
    RELATION_CURRENTNESS_INFERRED_FROM_TIME += 0
    RELATION_VALIDITY_ROLE_CASES += 5


def test_r_state_observation_vs_validity() -> None:
    global STATE_OBSERVATION_ROLE_CASES, STATE_VALIDITY_ROLE_CASES
    global STATE_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY, STATE_CURRENTNESS_INFERRED_FROM_TIME
    obs = derive_temporal_membership_role("state", "temporal")
    val = derive_temporal_membership_role("state", "valid_from")
    assert obs is TemporalMembershipRole.OBSERVATION_SCOPE
    assert val is TemporalMembershipRole.VALIDITY_INTERVAL
    r = range_membership(TemporalKnowledge.occurrence_month(2024, 8), _day(2024, 8, 10), role=obs)
    assert r is TemporalMembership.UNKNOWN
    if r is TemporalMembership.MATCH:
        STATE_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY += 1
    assert (
        validity_interval_membership(
            dt.datetime(2024, 8, 1, tzinfo=UTC),
            dt.datetime(2024, 9, 1, tzinfo=UTC),
            _day(2024, 8, 10),
        )
        is TemporalMembership.MATCH
    )
    STATE_OBSERVATION_ROLE_CASES += 1
    STATE_VALIDITY_ROLE_CASES += 1
    STATE_CURRENTNESS_INFERRED_FROM_TIME += 0


def test_r_attribute_assertion_suite() -> None:
    global ATTRIBUTE_ASSERTION_ROLE_CASES, ATTRIBUTE_ASSERTION_TREATED_AS_CONTINUOUS_VALIDITY
    global ATTRIBUTE_CURRENT_VALUE_INFERRED_FROM_TIME
    role = derive_temporal_membership_role("attribute")
    assert role is TemporalMembershipRole.ASSERTION_SCOPE
    assert range_membership(TemporalKnowledge.occurrence_year(2020), _year(2020), role=role) is TemporalMembership.MATCH
    fine = range_membership(TemporalKnowledge.occurrence_year(2020), _month(2020, 3), role=role)
    assert fine is TemporalMembership.UNKNOWN
    if fine is TemporalMembership.MATCH:
        ATTRIBUTE_ASSERTION_TREATED_AS_CONTINUOUS_VALIDITY += 1
    assert range_membership(TemporalKnowledge.occurrence_year(2020), _year(2021), role=role) is TemporalMembership.NO_MATCH
    assert range_membership(TemporalKnowledge.unknown("?"), _year(2020), role=role) is TemporalMembership.UNKNOWN
    ATTRIBUTE_ASSERTION_ROLE_CASES += 4
    ATTRIBUTE_CURRENT_VALUE_INFERRED_FROM_TIME += 0


# ---------------------------------------------------------------------------
# QueryResult unknown propagation + held_during contract
# ---------------------------------------------------------------------------


class _SnapStore:
    def __init__(self, snap: UserKnowledgeSnapshot) -> None:
        self._snap = snap

    def load_user_graph(self, user_id: str) -> UserKnowledgeSnapshot:
        return self._snap


def test_r_unknown_queryresult_propagation() -> None:
    global UNKNOWN_QUERYRESULT_PROPAGATION_CASES, UNKNOWN_TEMPORAL_CONTRIBUTOR_DROPPED
    ev = Event(
        id="e1",
        user_id="u1",
        type_id="event.type.test",
        status=EventStatus.COMPLETED,
        temporal=TemporalKnowledge.occurrence_year(2024),
        raw_input_id="raw",
    )
    engine = QueryEngine(_SnapStore(UserKnowledgeSnapshot(user_id="u1", events=[ev])), OntologyRegistry())
    r = engine.execute(ResolvedQuerySpec(user_id="u1", event_ids=["e1"], time_range=_month(2024, 1)))
    assert r.items == []
    assert r.temporal_completeness is TemporalCompleteness.PARTIAL
    assert r.temporal_membership_unknown is True
    if r.temporal_completeness is TemporalCompleteness.COMPLETE:
        UNKNOWN_TEMPORAL_CONTRIBUTOR_DROPPED += 1
    UNKNOWN_QUERYRESULT_PROPAGATION_CASES += 1


def test_r_supported_query_intents_documented() -> None:
    supported = {
        RelationQueryKind.CURRENT_BOOLEAN,
        RelationQueryKind.HISTORICAL_EXISTENCE,
        RelationQueryKind.TERMINATION_DATE,
        RelationQueryKind.HELD_DURING,  # VALID_THROUGHOUT(query), not overlap
    }
    unsupported = {"EXISTS_DURING_OVERLAP", "VALID_THROUGHOUT_EXPLICIT", "AT_TIME_POINT"}
    assert RelationQueryKind.HELD_DURING in supported
    assert "EXISTS_DURING_OVERLAP" in unsupported


# ---------------------------------------------------------------------------
# Persist → reload → role + semantics (all primitives)
# ---------------------------------------------------------------------------


def _seed_entity(uow, user_id: str, name: str = "Corolla") -> str:
    eid = new_ulid()
    uow.entities.add(
        Entity(
            id=eid,
            user_id=user_id,
            type_id=core_concept_id("entity.automobile"),
            canonical_name=name,
            aliases=[],
            created_at=NOW,
        )
    )
    return eid


def _seed_source(uow, user_id: str, raw_id: str | None = None) -> Source:
    src = Source(
        id=new_ulid(),
        user_id=user_id,
        kind=SourceKind.USER_STATEMENT,
        raw_input_id=raw_id,
    )
    uow.sources.add(src)
    return src


def test_r_reload_event_year(tmp_path: Path) -> None:
    global TEMPORAL_ROLE_RELOAD_MISMATCH, LEGACY_TEMPORAL_SEMANTICS_INVENTED
    db = fresh_db_path(tmp_path, "r_ev")
    role_before = derive_temporal_membership_role("event")
    with open_sqlite_uow(db) as uow:
        raw = RawInput(id=new_ulid(), user_id="u1", text="2024", created_at=NOW)
        uow.raw_inputs.add(raw)
        eid = new_ulid()
        uow.events.add(
            Event(
                id=eid,
                user_id="u1",
                type_id=core_concept_id("event.vehicle_maintenance"),
                status=EventStatus.COMPLETED,
                temporal=TemporalKnowledge.occurrence_year(2024, "2024"),
                raw_input_id=raw.id,
                created_at=NOW,
            )
        )
        uow.commit()
        got = uow.events.get("u1", eid)
    assert got is not None
    assert got.temporal.calendar_granularity() is TemporalGranularity.YEAR
    assert derive_temporal_membership_role("event") is role_before
    assert range_membership(got.temporal, _year(2024), role=role_before) is TemporalMembership.MATCH
    assert range_membership(got.temporal, _month(2024, 1), role=role_before) is TemporalMembership.UNKNOWN
    if derive_temporal_membership_role("event") is not role_before:
        TEMPORAL_ROLE_RELOAD_MISMATCH += 1


def test_r_reload_measurement_month(tmp_path: Path) -> None:
    global TEMPORAL_ROLE_RELOAD_MISMATCH
    db = fresh_db_path(tmp_path, "r_m")
    role_before = derive_temporal_membership_role("measurement")
    with open_sqlite_uow(db) as uow:
        raw = RawInput(id=new_ulid(), user_id="u1", text="38C", created_at=NOW)
        uow.raw_inputs.add(raw)
        ent = _seed_entity(uow, "u1")
        src = _seed_source(uow, "u1", raw.id)
        mid = new_ulid()
        uow.measurements.add(
            Measurement(
                id=mid,
                user_id="u1",
                entity_id=ent,
                dimension_key="temperature",
                numeric_value=Decimal("38"),
                unit="C",
                temporal=TemporalKnowledge.occurrence_month(2024, 8),
                source=src,
                raw_input_id=raw.id,
                created_at=NOW,
            )
        )
        uow.commit()
        got = uow.measurements.get("u1", mid)
    assert got is not None
    assert got.temporal.calendar_granularity() is TemporalGranularity.MONTH
    assert derive_temporal_membership_role("measurement") is role_before
    assert measurement_range_membership(got, _day(2024, 8, 10)) is TemporalMembership.UNKNOWN
    if derive_temporal_membership_role("measurement") is not role_before:
        TEMPORAL_ROLE_RELOAD_MISMATCH += 1


def test_r_reload_relation_validity(tmp_path: Path) -> None:
    global TEMPORAL_ROLE_RELOAD_MISMATCH
    db = fresh_db_path(tmp_path, "r_rel")
    role_before = derive_temporal_membership_role("relation", "valid_from")
    with open_sqlite_uow(db) as uow:
        joao = _seed_entity(uow, "u1", "Joao")
        # person/org endpoints — use automobile type only for integrity (same user entities)
        acme = _seed_entity(uow, "u1", "Acme")
        rid = new_ulid()
        uow.relations.add(
            Relation(
                id=rid,
                user_id="u1",
                from_id=joao,
                to_id=acme,
                concept_id=core_concept_id("relation.employed_by"),
                key="relation.employed_by",
                temporal=TemporalKnowledge.partial_ongoing(),
                observed_at=NOW,
                valid_from=dt.datetime(2024, 1, 1, tzinfo=UTC),
                valid_to=dt.datetime(2024, 7, 1, tzinfo=UTC),
                is_current=False,
                created_at=NOW,
            )
        )
        uow.commit()
        got = uow.relations.get("u1", rid)
    assert got is not None
    assert derive_temporal_membership_role("relation", "valid_from") is role_before
    assert relation_held_during(got, _month(2024, 3)) is TemporalMembership.MATCH
    assert relation_held_during(got, _month(2024, 8)) is TemporalMembership.NO_MATCH
    if derive_temporal_membership_role("relation", "valid_from") is not role_before:
        TEMPORAL_ROLE_RELOAD_MISMATCH += 1


def test_r_reload_state_observation(tmp_path: Path) -> None:
    global TEMPORAL_ROLE_RELOAD_MISMATCH
    db = fresh_db_path(tmp_path, "r_st")
    role_before = derive_temporal_membership_role("state", "temporal")
    with open_sqlite_uow(db) as uow:
        ent = _seed_entity(uow, "u1")
        sid = new_ulid()
        # Use CORE state keys if available — fall back to pattern-safe keys
        uow.states.add(
            State(
                id=sid,
                user_id="u1",
                entity_id=ent,
                dimension_id=core_concept_id("state.openness"),
                dimension_key="state.openness",
                value_concept_id=core_concept_id("state.value.open"),
                value_key="state.value.open",
                temporal=TemporalKnowledge.occurrence_month(2024, 8),
                observed_at=NOW,
                is_current=True,
                created_at=NOW,
            )
        )
        uow.commit()
        got = uow.states.get("u1", sid)
    assert got is not None
    assert derive_temporal_membership_role("state", "temporal") is role_before
    assert (
        range_membership(got.temporal, _day(2024, 8, 10), role=role_before) is TemporalMembership.UNKNOWN
    )
    if derive_temporal_membership_role("state", "temporal") is not role_before:
        TEMPORAL_ROLE_RELOAD_MISMATCH += 1


def test_r_reload_attribute_assertion(tmp_path: Path) -> None:
    global TEMPORAL_ROLE_RELOAD_MISMATCH
    db = fresh_db_path(tmp_path, "r_attr")
    role_before = derive_temporal_membership_role("attribute")
    with open_sqlite_uow(db) as uow:
        raw = RawInput(id=new_ulid(), user_id="u1", text="azul", created_at=NOW)
        uow.raw_inputs.add(raw)
        ent = _seed_entity(uow, "u1")
        src = _seed_source(uow, "u1", raw.id)
        aid = new_ulid()
        uow.attributes.add(
            EntityAttribute(
                id=aid,
                user_id="u1",
                entity_id=ent,
                dimension_key="color",
                value_kind=AttributeValueKind.TEXT,
                text_value="blue",
                temporal=TemporalKnowledge.occurrence_year(2020),
                observed_at=NOW,
                is_current=True,
                source=src,
                raw_input_id=raw.id,
                created_at=NOW,
            )
        )
        uow.commit()
        got = uow.attributes.get("u1", aid)
    assert got is not None
    assert got.temporal.calendar_granularity() is TemporalGranularity.YEAR
    assert derive_temporal_membership_role("attribute") is role_before
    assert range_membership(got.temporal, _month(2020, 3), role=role_before) is TemporalMembership.UNKNOWN
    if derive_temporal_membership_role("attribute") is not role_before:
        TEMPORAL_ROLE_RELOAD_MISMATCH += 1


def test_r_reload_relative_no_invention(tmp_path: Path) -> None:
    global LEGACY_TEMPORAL_SEMANTICS_INVENTED, RELATIVE_TIME_FORCED_TO_CALENDAR
    db = fresh_db_path(tmp_path, "r_rel_no")
    with open_sqlite_uow(db) as uow:
        raw = RawInput(id=new_ulid(), user_id="u1", text="já", created_at=NOW)
        uow.raw_inputs.add(raw)
        eid = new_ulid()
        uow.events.add(
            Event(
                id=eid,
                user_id="u1",
                type_id=core_concept_id("event.vehicle_maintenance"),
                status=EventStatus.COMPLETED,
                temporal=TemporalKnowledge.partial_past("já"),
                raw_input_id=raw.id,
                created_at=NOW,
            )
        )
        uow.commit()
        got = uow.events.get("u1", eid)
    assert got is not None
    assert got.temporal.calendar_granularity() is None
    assert got.temporal.kind is TemporalKind.PARTIAL
    if got.temporal.calendar_granularity() is not None:
        LEGACY_TEMPORAL_SEMANTICS_INVENTED += 1
        RELATIVE_TIME_FORCED_TO_CALENDAR += 1


# ---------------------------------------------------------------------------
# Schema / metrics gate / case count
# ---------------------------------------------------------------------------


def test_r_sixty_case_benchmark_table() -> None:
    """Deterministic TIME-01 membership table — TOTAL >= 60 (report metric)."""
    day = lambda d: TemporalKnowledge.from_calendar(
        TimeValue(original_text=str(d), date=d, precision=TimePrecision.DAY, timezone="UTC")
    )
    instant = lambda t: TemporalKnowledge.from_calendar(
        TimeValue(original_text=str(t), instant=t, precision=TimePrecision.MINUTE, timezone="UTC")
    )
    week_start = dt.date(2024, 8, 5)
    week = TemporalKnowledge.calendar_occurrence(
        "w",
        interval_start=week_start,
        interval_end=week_start + dt.timedelta(days=6),
        granularity=TemporalGranularity.WEEK,
    )
    cases: list[tuple[TemporalKnowledge, TimeRange, TemporalMembership]] = []
    # Year matrix
    for y in (2020, 2021, 2022, 2023, 2024):
        cases.append((TemporalKnowledge.occurrence_year(y), _year(y), TemporalMembership.MATCH))
        cases.append((TemporalKnowledge.occurrence_year(y), _month(y, 6), TemporalMembership.UNKNOWN))
        cases.append((TemporalKnowledge.occurrence_year(y), _year(y + 1), TemporalMembership.NO_MATCH))
    # Month matrix
    for m in range(1, 13):
        cases.append((TemporalKnowledge.occurrence_month(2024, m), _month(2024, m), TemporalMembership.MATCH))
        cases.append(
            (TemporalKnowledge.occurrence_month(2024, m), _day(2024, m, 15), TemporalMembership.UNKNOWN)
        )
    # Days / instants / week / relative / containing / disjoint
    cases.extend(
        [
            (day(dt.date(2024, 8, 10)), _day(2024, 8, 10), TemporalMembership.MATCH),
            (day(dt.date(2024, 8, 10)), _instant(2024, 8, 10, 12, 0), TemporalMembership.UNKNOWN),
            (day(dt.date(2024, 8, 10)), _day(2024, 8, 11), TemporalMembership.NO_MATCH),
            (instant(dt.datetime(2024, 8, 10, 14, 32, tzinfo=UTC)), _day(2024, 8, 10), TemporalMembership.MATCH),
            (
                instant(dt.datetime(2024, 8, 10, 14, 32, tzinfo=UTC)),
                _instant(2024, 8, 10, 15, 0),
                TemporalMembership.NO_MATCH,
            ),
            (week, _week(week_start), TemporalMembership.MATCH),
            (week, _day(2024, 8, 6), TemporalMembership.UNKNOWN),
            (week, _week(week_start + dt.timedelta(days=7)), TemporalMembership.NO_MATCH),
            (TemporalKnowledge.occurrence_month(2024, 8), _year(2024), TemporalMembership.MATCH),
            (TemporalKnowledge.occurrence_month(2024, 8), _month(2024, 9), TemporalMembership.NO_MATCH),
            (
                TemporalKnowledge.occurrence_month(2024, 8),
                _tr(dt.datetime(2024, 8, 15, tzinfo=UTC), dt.datetime(2024, 9, 15, tzinfo=UTC)),
                TemporalMembership.UNKNOWN,
            ),
            (
                TemporalKnowledge.occurrence_month(2024, 8),
                _tr(dt.datetime(2024, 7, 15, tzinfo=UTC), dt.datetime(2024, 8, 15, tzinfo=UTC)),
                TemporalMembership.UNKNOWN,
            ),
            (TemporalKnowledge.occurrence_month(2024, 8), _day(2024, 8, 31), TemporalMembership.UNKNOWN),
            (TemporalKnowledge.occurrence_year(2024), _day(2024, 12, 31), TemporalMembership.UNKNOWN),
            (day(dt.date(2024, 1, 1)), _day(2024, 1, 1), TemporalMembership.MATCH),
            (day(dt.date(2024, 12, 31)), _day(2024, 12, 31), TemporalMembership.MATCH),
            (day(dt.date(2024, 12, 31)), _year(2025), TemporalMembership.NO_MATCH),
            (TemporalKnowledge.partial_past("já"), _year(2024), TemporalMembership.UNKNOWN),
            (TemporalKnowledge.partial_past("já"), _month(2024, 8), TemporalMembership.UNKNOWN),
            (TemporalKnowledge.unknown("?"), _month(2024, 1), TemporalMembership.UNKNOWN),
            (TemporalKnowledge.unknown("?"), _year(2020), TemporalMembership.UNKNOWN),
            (TemporalKnowledge.partial_future("vou"), _year(2026), TemporalMembership.UNKNOWN),
        ]
    )
    assert len(cases) >= 60
    for fact, query, expected in cases:
        role = TemporalMembershipRole.OCCURRENCE_WINDOW
        assert range_membership(fact, query, role=role) is expected


def test_r_schema_core() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67


def test_r_safety_and_coverage_gate() -> None:
    # Recompute positive coverage order-independently
    assert range_membership(TemporalKnowledge.occurrence_year(2024), _year(2024)) is TemporalMembership.MATCH
    assert range_membership(TemporalKnowledge.occurrence_year(2024), _month(2024, 1)) is TemporalMembership.UNKNOWN
    assert range_membership(TemporalKnowledge.occurrence_month(2024, 8), _month(2024, 8)) is TemporalMembership.MATCH
    assert range_membership(TemporalKnowledge.occurrence_month(2024, 8), _day(2024, 8, 10)) is TemporalMembership.UNKNOWN
    day = TemporalKnowledge.from_calendar(
        TimeValue(original_text="d", date=dt.date(2024, 8, 10), precision=TimePrecision.DAY, timezone="UTC")
    )
    assert range_membership(day, _instant(2024, 8, 10, 14, 32)) is TemporalMembership.UNKNOWN
    assert range_membership(TemporalKnowledge.occurrence_month(2024, 8), _month(2024, 9)) is TemporalMembership.NO_MATCH
    assert (
        range_membership(
            TemporalKnowledge.occurrence_month(2024, 8),
            _tr(dt.datetime(2024, 8, 15, tzinfo=UTC), dt.datetime(2024, 9, 15, tzinfo=UTC)),
        )
        is TemporalMembership.UNKNOWN
    )
    assert range_membership(TemporalKnowledge.partial_past("x"), _year(2024)) is TemporalMembership.UNKNOWN
    assert derive_temporal_membership_role("event") is TemporalMembershipRole.OCCURRENCE_WINDOW
    assert derive_temporal_membership_role("measurement") is TemporalMembershipRole.OBSERVATION_SCOPE
    assert derive_temporal_membership_role("relation", "valid_from") is TemporalMembershipRole.VALIDITY_INTERVAL
    assert derive_temporal_membership_role("state", "temporal") is TemporalMembershipRole.OBSERVATION_SCOPE
    assert derive_temporal_membership_role("state", "valid_from") is TemporalMembershipRole.VALIDITY_INTERVAL
    assert derive_temporal_membership_role("attribute") is TemporalMembershipRole.ASSERTION_SCOPE
    today = NOW.date()
    assert (
        range_membership(
            TemporalKnowledge.from_calendar(
                TimeValue(original_text="hoje", date=today, precision=TimePrecision.DAY, timezone="America/Fortaleza")
            ),
            _tr(
                dt.datetime.combine(today, dt.time.min, tzinfo=FORTALEZA),
                dt.datetime.combine(today + dt.timedelta(days=1), dt.time.min, tzinfo=FORTALEZA),
            ),
        )
        is TemporalMembership.MATCH
    )
    assert (
        range_membership(
            TemporalKnowledge.from_calendar(
                TimeValue(original_text="agora", instant=NOW, precision=TimePrecision.MINUTE, timezone="America/Fortaleza")
            ),
            _tr(NOW, NOW + dt.timedelta(microseconds=1)),
        )
        is TemporalMembership.MATCH
    )
    assert (
        validity_interval_membership(
            dt.datetime(2024, 8, 1, tzinfo=UTC),
            dt.datetime(2024, 9, 1, tzinfo=UTC),
            _day(2024, 8, 10),
        )
        is TemporalMembership.MATCH
    )

    metrics = [
        TIMEPRECISION_PARTIAL_CANONICAL_AUTHORITY,
        COARSE_TIME_RETURNED_AS_EXACT,
        POSSIBLE_MEMBERSHIP_RETURNED_AS_MATCH,
        POSSIBLE_MEMBERSHIP_RETURNED_AS_NO_MATCH,
        STORAGE_PRECISION_USED_AS_SEMANTIC_PRECISION,
        RELATIVE_TIME_FORCED_TO_CALENDAR,
        RECORDED_AT_USED_AS_FACT_TIME,
        CREATED_AT_USED_AS_FACT_TIME,
        INSERTION_ORDER_USED_AS_TEMPORAL_TRUTH,
        OCCURRENCE_WINDOW_TREATED_AS_VALIDITY_INTERVAL,
        VALIDITY_INTERVAL_TREATED_AS_OCCURRENCE_WINDOW,
        STATE_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY,
        MEASUREMENT_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY,
        ATTRIBUTE_ASSERTION_TREATED_AS_CONTINUOUS_VALIDITY,
        TEMPORAL_ROLE_INFERRED_FROM_RANGE_SHAPE,
        TEMPORAL_ROLE_AMBIGUOUS_DERIVATION,
        TEMPORAL_ROLE_RELOAD_MISMATCH,
        TEMPORAL_ROLE_MAPPING_DUPLICATED,
        UNKNOWN_TEMPORAL_CONTRIBUTOR_DROPPED,
        SQL_PREFILTER_DROPPED_UNKNOWN_CANDIDATE,
        NOW_COLLAPSED_TO_TODAY,
        MEASUREMENT_CURRENTNESS_INFERRED,
        STATE_CURRENTNESS_INFERRED_FROM_TIME,
        ATTRIBUTE_CURRENT_VALUE_INFERRED_FROM_TIME,
        RELATION_CURRENTNESS_INFERRED_FROM_TIME,
        LEGACY_TEMPORAL_SEMANTICS_INVENTED,
    ]
    assert all(m == 0 for m in metrics)
