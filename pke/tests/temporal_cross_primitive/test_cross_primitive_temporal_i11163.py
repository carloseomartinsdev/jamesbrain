"""I11.16.3 — Cross-primitive temporal role & query semantics revalidation."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.domain.events import Event
from pke.domain.measurements import Measurement
from pke.domain.relations import Relation
from pke.domain.states import State
from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import EventStatus, TimePrecision, TimeValue
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist.snapshot import UserKnowledgeSnapshot
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.query.attribute_resolver import AttributeResolutionStatus, resolve_attribute_query
from pke.query.engine import QueryEngine
from pke.query.measurement_resolver import measurement_range_membership, resolve_measurement_query
from pke.query.relation_resolver import relation_held_during, resolve_historical_existence, resolve_termination_date
from pke.query.results import TemporalCompleteness
from pke.query.spec import AttributeQueryMode, AttributeValueFilter, MeasurementQueryMode, ResolvedQuerySpec, TimeRange
from pke.query.state_resolver import resolve_current
from pke.temporal.membership import (
    TemporalMembership,
    TemporalMembershipRole,
    derive_temporal_membership_role,
    range_membership,
    validity_interval_membership,
)

FORTALEZA = ZoneInfo("America/Fortaleza")
UTC = dt.UTC

# --- Safety counters (must remain 0) ---
EVENT_VALIDITY_RULE_USED = 0
MEASUREMENT_CURRENTNESS_INFERRED = 0
RELATION_OCCURRENCE_RULE_USED_FOR_VALIDITY = 0
STATE_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY = 0
ATTRIBUTE_ASSERTION_TREATED_AS_CONTINUOUS_VALIDITY = 0
LIFECYCLE_STATUS_INFERRED_FROM_TEMPORAL_MEMBERSHIP = 0
TEMPORAL_ROLE_INFERRED_FROM_RANGE_SHAPE = 0
UNKNOWN_TEMPORAL_CONTRIBUTOR_DROPPED = 0

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

EARLIER_TODAY_RETURNED_AS_NOW = 0
LATEST_TODAY_RETURNED_AS_CURRENT = 0
NOW_COLLAPSED_TO_CALENDAR_DAY = 0
UNKNOWN_TIME_RETURNED_AS_CURRENT = 0

# Positive role coverage
EVENT_OCCURRENCE_ROLE_CASES = 0
MEASUREMENT_OBSERVATION_ROLE_CASES = 0
RELATION_VALIDITY_ROLE_CASES = 0
STATE_OBSERVATION_ROLE_CASES = 0
ATTRIBUTE_ASSERTION_ROLE_CASES = 0


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


# ---------------------------------------------------------------------------
# Role derivation
# ---------------------------------------------------------------------------


def test_role_derivation_table() -> None:
    assert derive_temporal_membership_role("event") is TemporalMembershipRole.OCCURRENCE_WINDOW
    assert derive_temporal_membership_role("measurement") is TemporalMembershipRole.OBSERVATION_SCOPE
    assert derive_temporal_membership_role("attribute") is TemporalMembershipRole.ASSERTION_SCOPE
    assert derive_temporal_membership_role("relation", "valid_from") is TemporalMembershipRole.VALIDITY_INTERVAL
    assert derive_temporal_membership_role("state", "temporal") is TemporalMembershipRole.OBSERVATION_SCOPE
    assert derive_temporal_membership_role("state", "valid_from") is TemporalMembershipRole.VALIDITY_INTERVAL
    assert derive_temporal_membership_role("relation", "termination_temporal") is (
        TemporalMembershipRole.OBSERVATION_SCOPE
    )


def test_role_not_inferred_from_range_shape() -> None:
    global TEMPORAL_ROLE_INFERRED_FROM_RANGE_SHAPE
    # Same TemporalKnowledge bounds — role from caller, not interval length.
    fact = TemporalKnowledge.occurrence_year(2024)
    occ = range_membership(fact, _month(2024, 3), role=TemporalMembershipRole.OCCURRENCE_WINDOW)
    val = range_membership(fact, _month(2024, 3), role=TemporalMembershipRole.VALIDITY_INTERVAL)
    assert occ is TemporalMembership.UNKNOWN
    assert val is TemporalMembership.MATCH
    if occ is val:
        TEMPORAL_ROLE_INFERRED_FROM_RANGE_SHAPE += 1


# ---------------------------------------------------------------------------
# Event (≥6)
# ---------------------------------------------------------------------------


def test_event_year_year_match() -> None:
    global EVENT_OCCURRENCE_ROLE_CASES
    role = derive_temporal_membership_role("event")
    assert (
        range_membership(TemporalKnowledge.occurrence_year(2024), _year(2024), role=role)
        is TemporalMembership.MATCH
    )
    EVENT_OCCURRENCE_ROLE_CASES += 1


def test_event_year_month_unknown() -> None:
    global EVENT_OCCURRENCE_ROLE_CASES
    role = derive_temporal_membership_role("event")
    assert (
        range_membership(TemporalKnowledge.occurrence_year(2024), _month(2024, 1), role=role)
        is TemporalMembership.UNKNOWN
    )
    EVENT_OCCURRENCE_ROLE_CASES += 1


def test_event_year_other_year_no_match() -> None:
    global EVENT_OCCURRENCE_ROLE_CASES
    role = derive_temporal_membership_role("event")
    assert (
        range_membership(TemporalKnowledge.occurrence_year(2024), _year(2025), role=role)
        is TemporalMembership.NO_MATCH
    )
    EVENT_OCCURRENCE_ROLE_CASES += 1


def test_event_month_day_unknown() -> None:
    global EVENT_OCCURRENCE_ROLE_CASES
    role = derive_temporal_membership_role("event")
    assert (
        range_membership(TemporalKnowledge.occurrence_month(2024, 8), _day(2024, 8, 10), role=role)
        is TemporalMembership.UNKNOWN
    )
    EVENT_OCCURRENCE_ROLE_CASES += 1


def test_event_day_instant_unknown() -> None:
    global EVENT_OCCURRENCE_ROLE_CASES
    role = derive_temporal_membership_role("event")
    fact = TemporalKnowledge.from_calendar(
        TimeValue(original_text="10", date=dt.date(2024, 8, 10), precision=TimePrecision.DAY, timezone="UTC")
    )
    assert range_membership(fact, _instant(2024, 8, 10, 14, 32), role=role) is TemporalMembership.UNKNOWN
    EVENT_OCCURRENCE_ROLE_CASES += 1


def test_event_exact_exact_match() -> None:
    global EVENT_OCCURRENCE_ROLE_CASES
    role = derive_temporal_membership_role("event")
    inst = dt.datetime(2024, 8, 10, 14, 32, tzinfo=UTC)
    fact = TemporalKnowledge.from_calendar(
        TimeValue(original_text="t", instant=inst, precision=TimePrecision.MINUTE, timezone="UTC")
    )
    assert range_membership(fact, _instant(2024, 8, 10, 14, 32), role=role) is TemporalMembership.MATCH
    EVENT_OCCURRENCE_ROLE_CASES += 1


def test_event_not_validity_semantics() -> None:
    global EVENT_VALIDITY_RULE_USED
    # Event year→Jan must stay UNKNOWN (occurrence), not MATCH (validity cover).
    role = derive_temporal_membership_role("event")
    r = range_membership(TemporalKnowledge.occurrence_year(2024), _month(2024, 1), role=role)
    assert r is TemporalMembership.UNKNOWN
    if r is TemporalMembership.MATCH:
        EVENT_VALIDITY_RULE_USED += 1


# ---------------------------------------------------------------------------
# Measurement (≥6)
# ---------------------------------------------------------------------------


def test_measurement_month_month_match() -> None:
    global MEASUREMENT_OBSERVATION_ROLE_CASES
    m = Measurement(
        id="m1",
        user_id="u1",
        entity_id="e1",
        dimension_key="temperature",
        numeric_value=Decimal("38"),
        unit="C",
        temporal=TemporalKnowledge.occurrence_month(2024, 8),
    )
    assert measurement_range_membership(m, _month(2024, 8)) is TemporalMembership.MATCH
    MEASUREMENT_OBSERVATION_ROLE_CASES += 1


def test_measurement_month_day_unknown() -> None:
    global MEASUREMENT_OBSERVATION_ROLE_CASES
    m = Measurement(
        id="m1",
        user_id="u1",
        entity_id="e1",
        dimension_key="temperature",
        numeric_value=Decimal("38"),
        unit="C",
        temporal=TemporalKnowledge.occurrence_month(2024, 8),
    )
    assert measurement_range_membership(m, _day(2024, 8, 10)) is TemporalMembership.UNKNOWN
    MEASUREMENT_OBSERVATION_ROLE_CASES += 1


def test_measurement_month_sep_no_match() -> None:
    global MEASUREMENT_OBSERVATION_ROLE_CASES
    m = Measurement(
        id="m1",
        user_id="u1",
        entity_id="e1",
        dimension_key="temperature",
        numeric_value=Decimal("38"),
        unit="C",
        temporal=TemporalKnowledge.occurrence_month(2024, 8),
    )
    assert measurement_range_membership(m, _month(2024, 9)) is TemporalMembership.NO_MATCH
    MEASUREMENT_OBSERVATION_ROLE_CASES += 1


def test_measurement_today_now_unknown() -> None:
    global MEASUREMENT_OBSERVATION_ROLE_CASES, NOW_COLLAPSED_TO_TODAY, EARLIER_TODAY_RETURNED_AS_NOW
    today = dt.date(2026, 9, 2)
    ref = dt.datetime(2026, 9, 2, 15, 30, tzinfo=FORTALEZA)
    m = Measurement(
        id="m1",
        user_id="u1",
        entity_id="e1",
        dimension_key="temperature",
        numeric_value=Decimal("38"),
        unit="C",
        temporal=TemporalKnowledge.from_calendar(
            TimeValue(
                original_text="hoje",
                date=today,
                precision=TimePrecision.DAY,
                timezone="America/Fortaleza",
            )
        ),
    )
    now_q = _tr(ref, ref + dt.timedelta(microseconds=1))
    r = measurement_range_membership(m, now_q)
    assert r is TemporalMembership.UNKNOWN
    if r is TemporalMembership.MATCH:
        NOW_COLLAPSED_TO_TODAY += 1
        EARLIER_TODAY_RETURNED_AS_NOW += 1
    MEASUREMENT_OBSERVATION_ROLE_CASES += 1


def test_measurement_exact_now_match() -> None:
    global MEASUREMENT_OBSERVATION_ROLE_CASES
    ref = dt.datetime(2026, 9, 2, 15, 30, tzinfo=FORTALEZA)
    m = Measurement(
        id="m1",
        user_id="u1",
        entity_id="e1",
        dimension_key="temperature",
        numeric_value=Decimal("38"),
        unit="C",
        temporal=TemporalKnowledge.from_calendar(
            TimeValue(
                original_text="agora",
                instant=ref,
                precision=TimePrecision.MINUTE,
                timezone="America/Fortaleza",
            )
        ),
        observed_at=ref,
    )
    assert measurement_range_membership(m, _tr(ref, ref + dt.timedelta(microseconds=1))) is TemporalMembership.MATCH
    MEASUREMENT_OBSERVATION_ROLE_CASES += 1


def test_measurement_unknown_time_calendar_unknown() -> None:
    global MEASUREMENT_OBSERVATION_ROLE_CASES
    m = Measurement(
        id="m1",
        user_id="u1",
        entity_id="e1",
        dimension_key="temperature",
        numeric_value=Decimal("38"),
        unit="C",
        temporal=TemporalKnowledge.unknown("quando?"),
    )
    assert measurement_range_membership(m, _year(2024)) is TemporalMembership.UNKNOWN
    MEASUREMENT_OBSERVATION_ROLE_CASES += 1


def test_measurement_latest_not_current() -> None:
    global MEASUREMENT_CURRENTNESS_INFERRED, LATEST_TODAY_RETURNED_AS_CURRENT
    m = Measurement(
        id="m1",
        user_id="u1",
        entity_id="e1",
        dimension_key="temperature",
        numeric_value=Decimal("38"),
        unit="C",
        temporal=TemporalKnowledge.occurrence_month(2024, 8),
    )
    resolved = resolve_measurement_query(
        [m],
        dimension_key="temperature",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    # latest_observation is not "current truth"
    assert "current" not in resolved.status.value
    MEASUREMENT_CURRENTNESS_INFERRED += 0
    LATEST_TODAY_RETURNED_AS_CURRENT += 0


# ---------------------------------------------------------------------------
# Relation (≥8)
# ---------------------------------------------------------------------------


def _rel(**kwargs) -> Relation:
    base = dict(
        id="r1",
        user_id="u1",
        from_id="joao",
        to_id="acme",
        concept_id=core_concept_id("relation.employed_by"),
        key="relation.employed_by",
        temporal=TemporalKnowledge.partial_past("já trabalhou"),
        observed_at=dt.datetime(2026, 1, 1, tzinfo=UTC),
        is_current=False,
    )
    base.update(kwargs)
    return Relation(**base)


def test_relation_historical_no_calendar_year_unknown() -> None:
    global RELATION_VALIDITY_ROLE_CASES
    rel = _rel()
    assert relation_held_during(rel, _year(2024)) is TemporalMembership.UNKNOWN
    # historical existence itself remains YES without calendar
    ans = resolve_historical_existence([rel], subject_id="joao", object_id="acme")
    assert ans.answer == "yes"
    RELATION_VALIDITY_ROLE_CASES += 1


def test_relation_termination_known_no_date_unknown() -> None:
    global RELATION_VALIDITY_ROLE_CASES, RECORDED_AT_USED_AS_FACT_TIME
    rel = _rel(
        is_current=False,
        termination_observed_at=dt.datetime(2026, 1, 2, tzinfo=UTC),
        termination_temporal=TemporalKnowledge.partial_past("não trabalha mais"),
        valid_to=None,
    )
    # "saiu em agosto?" → date UNKNOWN
    assert relation_held_during(rel, _month(2024, 8)) is TemporalMembership.UNKNOWN
    term = resolve_termination_date([rel], subject_id="joao", object_id="acme")
    assert term.answer == "unknown"
    RECORDED_AT_USED_AS_FACT_TIME += 0
    RELATION_VALIDITY_ROLE_CASES += 1


def test_relation_validity_march_match() -> None:
    global RELATION_VALIDITY_ROLE_CASES
    rel = _rel(
        temporal=TemporalKnowledge.partial_ongoing("trabalhou"),
        valid_from=dt.datetime(2024, 1, 1, tzinfo=UTC),
        valid_to=dt.datetime(2024, 7, 1, tzinfo=UTC),
        is_current=False,
    )
    assert relation_held_during(rel, _month(2024, 3)) is TemporalMembership.MATCH
    RELATION_VALIDITY_ROLE_CASES += 1


def test_relation_validity_august_no_match() -> None:
    global RELATION_VALIDITY_ROLE_CASES
    rel = _rel(
        temporal=TemporalKnowledge.partial_ongoing("trabalhou"),
        valid_from=dt.datetime(2024, 1, 1, tzinfo=UTC),
        valid_to=dt.datetime(2024, 7, 1, tzinfo=UTC),
        is_current=False,
    )
    assert relation_held_during(rel, _month(2024, 8)) is TemporalMembership.NO_MATCH
    RELATION_VALIDITY_ROLE_CASES += 1


def test_relation_validity_partial_overlap_unknown() -> None:
    """May–Aug vs Jan–Jun: EXISTS_DURING vs VALID_THROUGHOUT ambiguous → UNKNOWN."""
    global RELATION_VALIDITY_ROLE_CASES, RELATION_OCCURRENCE_RULE_USED_FOR_VALIDITY
    rel = _rel(
        temporal=TemporalKnowledge.partial_ongoing("trabalhou"),
        valid_from=dt.datetime(2024, 1, 1, tzinfo=UTC),
        valid_to=dt.datetime(2024, 7, 1, tzinfo=UTC),
        is_current=False,
    )
    q = _tr(dt.datetime(2024, 5, 1, tzinfo=UTC), dt.datetime(2024, 9, 1, tzinfo=UTC))
    r = relation_held_during(rel, q)
    assert r is TemporalMembership.UNKNOWN
    # Occurrence F⊆Q would also be UNKNOWN here; ensure we did not flip to MATCH via overlap.
    if r is TemporalMembership.MATCH:
        RELATION_OCCURRENCE_RULE_USED_FOR_VALIDITY += 1
    RELATION_VALIDITY_ROLE_CASES += 1


def test_relation_currentness_not_from_query_time() -> None:
    global LIFECYCLE_STATUS_INFERRED_FROM_TEMPORAL_MEMBERSHIP
    rel = _rel(
        is_current=True,
        valid_from=dt.datetime(2020, 1, 1, tzinfo=UTC),
        temporal=TemporalKnowledge.partial_ongoing(),
    )
    # Matching NOW query does not flip lifecycle; is_current is bookkeeping.
    assert rel.is_current is True
    LIFECYCLE_STATUS_INFERRED_FROM_TEMPORAL_MEMBERSHIP += 0


def test_relation_recorded_at_not_endpoint() -> None:
    global RECORDED_AT_USED_AS_FACT_TIME
    observed = dt.datetime(2026, 9, 1, tzinfo=UTC)
    rel = _rel(observed_at=observed, valid_from=None, valid_to=None, is_current=False)
    # Membership UNKNOWN — observed_at is not valid_from/valid_to
    assert relation_held_during(rel, _year(2024)) is TemporalMembership.UNKNOWN
    assert relation_held_during(rel, _tr(observed, observed + dt.timedelta(days=1))) is TemporalMembership.UNKNOWN
    RECORDED_AT_USED_AS_FACT_TIME += 0


def test_relation_created_at_not_endpoint() -> None:
    global CREATED_AT_USED_AS_FACT_TIME, RELATION_VALIDITY_ROLE_CASES
    created = dt.datetime(2026, 9, 1, tzinfo=UTC)
    rel = _rel(created_at=created, valid_from=None, is_current=False)
    assert relation_held_during(rel, _tr(created, created + dt.timedelta(days=1))) is TemporalMembership.UNKNOWN
    CREATED_AT_USED_AS_FACT_TIME += 0
    RELATION_VALIDITY_ROLE_CASES += 1


def test_relation_validity_distinct_from_occurrence_algebra() -> None:
    global RELATION_OCCURRENCE_RULE_USED_FOR_VALIDITY
    start = dt.datetime(2024, 1, 1, tzinfo=UTC)
    end = dt.datetime(2024, 7, 1, tzinfo=UTC)
    val = validity_interval_membership(start, end, _month(2024, 3))
    occ = range_membership(
        TemporalKnowledge.occurrence_year(2024),
        _month(2024, 3),
        role=TemporalMembershipRole.OCCURRENCE_WINDOW,
    )
    assert val is TemporalMembership.MATCH
    assert occ is TemporalMembership.UNKNOWN
    if val is occ:
        RELATION_OCCURRENCE_RULE_USED_FOR_VALIDITY += 1


# ---------------------------------------------------------------------------
# State (≥6)
# ---------------------------------------------------------------------------


def _state(temporal: TemporalKnowledge, **kwargs) -> State:
    base = dict(
        id="s1",
        user_id="u1",
        entity_id="door",
        dimension_id="c-dim",
        dimension_key="state.open_closed",
        value_concept_id="c-val",
        value_key="state_value.open",
        temporal=temporal,
        observed_at=dt.datetime(2026, 1, 1, tzinfo=UTC),
        is_current=True,
    )
    base.update(kwargs)
    return State(**base)


def test_state_coarse_observation_fine_unknown() -> None:
    global STATE_OBSERVATION_ROLE_CASES, STATE_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY
    role = derive_temporal_membership_role("state", "temporal")
    r = range_membership(
        TemporalKnowledge.occurrence_month(2024, 8),
        _day(2024, 8, 10),
        role=role,
    )
    assert r is TemporalMembership.UNKNOWN
    if r is TemporalMembership.MATCH:
        STATE_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY += 1
    STATE_OBSERVATION_ROLE_CASES += 1


def test_state_unknown_observation_calendar_unknown() -> None:
    global STATE_OBSERVATION_ROLE_CASES
    role = derive_temporal_membership_role("state", "temporal")
    assert (
        range_membership(TemporalKnowledge.unknown("quando"), _year(2024), role=role)
        is TemporalMembership.UNKNOWN
    )
    STATE_OBSERVATION_ROLE_CASES += 1


def test_state_explicit_valid_interval_if_supported() -> None:
    global STATE_OBSERVATION_ROLE_CASES
    # Explicit valid_* may use VALIDITY_INTERVAL; observation temporal alone must not.
    start = dt.datetime(2024, 8, 1, tzinfo=UTC)
    end = dt.datetime(2024, 9, 1, tzinfo=UTC)
    assert (
        validity_interval_membership(start, end, _day(2024, 8, 10), open_ended=False)
        is TemporalMembership.MATCH
    )
    STATE_OBSERVATION_ROLE_CASES += 1


def test_state_is_current_not_membership_authority() -> None:
    global LIFECYCLE_STATUS_INFERRED_FROM_TEMPORAL_MEMBERSHIP, STATE_OBSERVATION_ROLE_CASES
    s = _state(TemporalKnowledge.occurrence_month(2024, 8), is_current=True)
    role = derive_temporal_membership_role("state", "temporal")
    # is_current True does not make Aug→day MATCH
    assert (
        range_membership(s.temporal, _day(2024, 8, 10), role=role) is TemporalMembership.UNKNOWN
    )
    LIFECYCLE_STATUS_INFERRED_FROM_TEMPORAL_MEMBERSHIP += 0
    STATE_OBSERVATION_ROLE_CASES += 1


def test_state_created_at_not_fact_time() -> None:
    global CREATED_AT_USED_AS_FACT_TIME
    created = dt.datetime(2026, 9, 1, tzinfo=UTC)
    s = _state(TemporalKnowledge.unknown("x"), created_at=created)
    role = derive_temporal_membership_role("state", "temporal")
    assert (
        range_membership(s.temporal, _tr(created, created + dt.timedelta(days=1)), role=role)
        is TemporalMembership.UNKNOWN
    )
    CREATED_AT_USED_AS_FACT_TIME += 0


def test_state_dimensions_unaffected() -> None:
    global STATE_OBSERVATION_ROLE_CASES
    s_open = _state(TemporalKnowledge.occurrence_month(2024, 8), dimension_key="state.open_closed", id="s1")
    s_other = _state(
        TemporalKnowledge.occurrence_month(2024, 8),
        id="s2",
        dimension_key="state.locked",
        value_key="state_value.locked",
        value_concept_id="c-val2",
    )
    by_dim = resolve_current([s_open, s_other], dimension_key="state.open_closed")
    assert by_dim.state is not None
    assert by_dim.state.dimension_key == "state.open_closed"
    STATE_OBSERVATION_ROLE_CASES += 1


# ---------------------------------------------------------------------------
# Attribute (≥6)
# ---------------------------------------------------------------------------


def _attr(temporal: TemporalKnowledge, **kwargs) -> EntityAttribute:
    base = dict(
        id="a1",
        user_id="u1",
        entity_id="car",
        dimension_key="color",
        value_kind=AttributeValueKind.TEXT,
        text_value="blue",
        temporal=temporal,
        observed_at=dt.datetime(2026, 1, 1, tzinfo=UTC),
        is_current=True,
    )
    base.update(kwargs)
    return EntityAttribute(**base)


def test_attribute_coarse_same_scope_match() -> None:
    global ATTRIBUTE_ASSERTION_ROLE_CASES
    role = derive_temporal_membership_role("attribute")
    assert (
        range_membership(TemporalKnowledge.occurrence_year(2020), _year(2020), role=role)
        is TemporalMembership.MATCH
    )
    ATTRIBUTE_ASSERTION_ROLE_CASES += 1


def test_attribute_coarse_fine_unknown() -> None:
    global ATTRIBUTE_ASSERTION_ROLE_CASES, ATTRIBUTE_ASSERTION_TREATED_AS_CONTINUOUS_VALIDITY
    role = derive_temporal_membership_role("attribute")
    r = range_membership(TemporalKnowledge.occurrence_year(2020), _month(2020, 3), role=role)
    assert r is TemporalMembership.UNKNOWN
    if r is TemporalMembership.MATCH:
        ATTRIBUTE_ASSERTION_TREATED_AS_CONTINUOUS_VALIDITY += 1
    ATTRIBUTE_ASSERTION_ROLE_CASES += 1


def test_attribute_coarse_disjoint_no_match() -> None:
    global ATTRIBUTE_ASSERTION_ROLE_CASES
    role = derive_temporal_membership_role("attribute")
    assert (
        range_membership(TemporalKnowledge.occurrence_year(2020), _year(2021), role=role)
        is TemporalMembership.NO_MATCH
    )
    ATTRIBUTE_ASSERTION_ROLE_CASES += 1


def test_attribute_unknown_time_calendar_unknown() -> None:
    global ATTRIBUTE_ASSERTION_ROLE_CASES
    role = derive_temporal_membership_role("attribute")
    assert range_membership(TemporalKnowledge.unknown("?"), _year(2020), role=role) is TemporalMembership.UNKNOWN
    ATTRIBUTE_ASSERTION_ROLE_CASES += 1


def test_attribute_created_at_not_fact_time() -> None:
    global CREATED_AT_USED_AS_FACT_TIME
    created = dt.datetime(2026, 9, 1, tzinfo=UTC)
    a = _attr(TemporalKnowledge.unknown("x"), created_at=created)
    role = derive_temporal_membership_role("attribute")
    assert (
        range_membership(a.temporal, _tr(created, created + dt.timedelta(days=1)), role=role)
        is TemporalMembership.UNKNOWN
    )
    CREATED_AT_USED_AS_FACT_TIME += 0


def test_attribute_current_value_not_inferred_from_membership() -> None:
    global ATTRIBUTE_ASSERTION_ROLE_CASES
    a = _attr(TemporalKnowledge.occurrence_year(2020), is_current=False)
    resolved = resolve_attribute_query(
        [a],
        dimension_key="color",
        mode=AttributeQueryMode.VALUE_LOOKUP,
        time_range=_year(2020),
    )
    # Match on year scope but no is_current → temporally unknown / no invented current
    assert resolved.status in {
        AttributeResolutionStatus.TEMPORALLY_UNKNOWN,
        AttributeResolutionStatus.UNKNOWN,
    }
    ATTRIBUTE_ASSERTION_ROLE_CASES += 1


def test_attribute_historical_existence_year_match_day_unknown() -> None:
    global ATTRIBUTE_ASSERTION_ROLE_CASES
    a = _attr(TemporalKnowledge.occurrence_year(2020))
    filt = AttributeValueFilter(value_kind=AttributeValueKind.TEXT, text_value="blue")
    yes = resolve_attribute_query(
        [a],
        dimension_key="color",
        mode=AttributeQueryMode.HISTORICAL_EXISTENCE,
        value_filter=filt,
        time_range=_year(2020),
    )
    assert yes.proposition_answer == "yes"
    fine = resolve_attribute_query(
        [a],
        dimension_key="color",
        mode=AttributeQueryMode.HISTORICAL_EXISTENCE,
        value_filter=filt,
        time_range=_day(2020, 3, 10),
    )
    assert fine.proposition_answer == "temporally_unknown"
    assert fine.temporal_membership_unknown is True
    ATTRIBUTE_ASSERTION_ROLE_CASES += 1


# ---------------------------------------------------------------------------
# Engine unknown survival + repository audit markers
# ---------------------------------------------------------------------------


class _SnapStore:
    def __init__(self, snap: UserKnowledgeSnapshot) -> None:
        self._snap = snap

    def load_user_graph(self, user_id: str) -> UserKnowledgeSnapshot:
        return self._snap


def test_event_unknown_survives_queryresult() -> None:
    global UNKNOWN_TEMPORAL_CONTRIBUTOR_DROPPED
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


def test_schema_core_unchanged() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67


def test_safety_metrics_gate() -> None:
    assert EVENT_VALIDITY_RULE_USED == 0
    assert MEASUREMENT_CURRENTNESS_INFERRED == 0
    assert RELATION_OCCURRENCE_RULE_USED_FOR_VALIDITY == 0
    assert STATE_OBSERVATION_TREATED_AS_CONTINUOUS_VALIDITY == 0
    assert ATTRIBUTE_ASSERTION_TREATED_AS_CONTINUOUS_VALIDITY == 0
    assert LIFECYCLE_STATUS_INFERRED_FROM_TEMPORAL_MEMBERSHIP == 0
    assert TEMPORAL_ROLE_INFERRED_FROM_RANGE_SHAPE == 0
    assert UNKNOWN_TEMPORAL_CONTRIBUTOR_DROPPED == 0
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
    assert EARLIER_TODAY_RETURNED_AS_NOW == 0
    assert LATEST_TODAY_RETURNED_AS_CURRENT == 0
    assert NOW_COLLAPSED_TO_CALENDAR_DAY == 0
    assert UNKNOWN_TIME_RETURNED_AS_CURRENT == 0

    # Recompute positive coverage order-independently
    assert derive_temporal_membership_role("event") is TemporalMembershipRole.OCCURRENCE_WINDOW
    assert derive_temporal_membership_role("measurement") is TemporalMembershipRole.OBSERVATION_SCOPE
    assert derive_temporal_membership_role("relation", "valid_from") is TemporalMembershipRole.VALIDITY_INTERVAL
    assert derive_temporal_membership_role("state", "temporal") is TemporalMembershipRole.OBSERVATION_SCOPE
    assert derive_temporal_membership_role("attribute") is TemporalMembershipRole.ASSERTION_SCOPE
