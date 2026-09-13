"""MeasurementResolver — epistemic observation resolution (not repository authority).

created_at / row id / insertion order are NEVER used as observation chronology.
latest_observation ≠ current truth.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pke.domain.measurements import Measurement
from pke.query.spec import MeasurementQueryMode, MeasurementValueFilter, TimeRange
from pke.temporal.membership import (
    TemporalMembership,
    TemporalMembershipRole,
    derive_temporal_membership_role,
    range_membership,
    temporal_instant,
)


class MeasurementResolutionStatus(StrEnum):
    KNOWN_SINGLE = "known_single"
    KNOWN_MULTIPLE = "known_multiple"
    UNKNOWN = "unknown"
    TEMPORALLY_UNKNOWN = "temporally_unknown"
    AMBIGUOUS = "ambiguous"


PropositionAnswer = Literal["yes", "unknown", "ambiguous", "temporally_unknown"]


@dataclass(frozen=True)
class MeasurementValueIdentity:
    numeric_value: Decimal
    unit: str | None = None
    currency_code: str | None = None

    def as_key(self) -> tuple[object, ...]:
        return (self.numeric_value, self.unit, self.currency_code)


@dataclass(frozen=True)
class ResolvedMeasurementValueGroup:
    identity: MeasurementValueIdentity
    observations: tuple[Measurement, ...]
    support_count: int


@dataclass(frozen=True)
class MeasurementResolverResult:
    status: MeasurementResolutionStatus
    dimension_key: str
    mode: MeasurementQueryMode
    groups: tuple[ResolvedMeasurementValueGroup, ...] = ()
    candidate_observations: tuple[Measurement, ...] = ()
    temporal_membership_unknown: bool = False
    unknown_temporal_contributors: tuple[Measurement, ...] = ()
    proposition_answer: PropositionAnswer | None = None
    notes: tuple[str, ...] = ()


def observation_instant(m: Measurement) -> dt.datetime | None:
    """Fact chronology: observed_at or TemporalKnowledge calendar instant — never created_at."""
    if m.observed_at is not None:
        return m.observed_at
    return temporal_instant(m.temporal)


def value_identity_of(m: Measurement) -> MeasurementValueIdentity:
    return MeasurementValueIdentity(
        numeric_value=m.numeric_value,
        unit=m.unit,
        currency_code=m.currency_code,
    )


def _group_by_value(rows: list[Measurement]) -> list[ResolvedMeasurementValueGroup]:
    buckets: dict[tuple[object, ...], list[Measurement]] = {}
    order: list[tuple[object, ...]] = []
    for row in rows:
        key = value_identity_of(row).as_key()
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(row)
    return [
        ResolvedMeasurementValueGroup(
            identity=value_identity_of(buckets[k][0]),
            observations=tuple(buckets[k]),
            support_count=len(buckets[k]),
        )
        for k in order
    ]


def _units_comparable(a_unit: str | None, a_cur: str | None, b_unit: str | None, b_cur: str | None) -> bool:
    """Same unit/currency identity required; no conversion."""
    if a_cur or b_cur:
        return (a_cur or None) == (b_cur or None) and a_unit is None and b_unit is None
    if a_unit is None and b_unit is None:
        return True
    return a_unit is not None and b_unit is not None and a_unit == b_unit


def filter_comparable(m: Measurement, filt: MeasurementValueFilter) -> Literal["match", "mismatch", "incomparable"]:
    if not _units_comparable(m.unit, m.currency_code, filt.unit, filt.currency_code):
        return "incomparable"
    if m.numeric_value != filt.numeric_value:
        return "mismatch"
    return "match"


def measurement_range_membership(
    m: Measurement, time_range: TimeRange
) -> TemporalMembership:
    """Ternary membership using observed_at when exact; else TemporalKnowledge.

    Role = OBSERVATION_SCOPE (not Event occurrence label; same coarse-window algebra).
    Never uses created_at. UNKNOWN remains UNKNOWN (not false).
    """
    role = derive_temporal_membership_role("measurement", "temporal")
    if m.observed_at is not None:
        if time_range.start <= m.observed_at < time_range.end:
            return TemporalMembership.MATCH
        return TemporalMembership.NO_MATCH
    assert role is TemporalMembershipRole.OBSERVATION_SCOPE
    return range_membership(m.temporal, time_range, role=role)


def _partition_temporal(
    rows: list[Measurement], time_range: TimeRange | None
) -> tuple[list[Measurement], list[Measurement], bool]:
    if time_range is None:
        return list(rows), [], False
    matched: list[Measurement] = []
    unknown: list[Measurement] = []
    for row in rows:
        membership = measurement_range_membership(row, time_range)
        if membership is TemporalMembership.MATCH:
            matched.append(row)
        elif membership is TemporalMembership.UNKNOWN:
            unknown.append(row)
    return matched, unknown, bool(unknown)


def resolve_measurement_query(
    observations: list[Measurement],
    *,
    dimension_key: str,
    mode: MeasurementQueryMode,
    value_filter: MeasurementValueFilter | None = None,
    time_range: TimeRange | None = None,
    context_entity_ids: list[str] | None = None,
) -> MeasurementResolverResult:
    """Epistemic Measurement resolution. Repository supplies candidates only."""
    pool = [m for m in observations if m.dimension_key == dimension_key]
    if context_entity_ids:
        ctx = set(context_entity_ids)
        pool = [m for m in pool if m.context_entity_id in ctx]
    notes: list[str] = []

    if mode is MeasurementQueryMode.LATEST_OBSERVATION:
        return _latest(pool, dimension_key, notes)
    if mode is MeasurementQueryMode.OBSERVATIONS_IN_RANGE:
        return _range(pool, dimension_key, time_range, notes)
    if mode is MeasurementQueryMode.OBSERVATION_AT_TIME:
        return _at_time(pool, dimension_key, time_range, notes)
    if mode is MeasurementQueryMode.VALUE_PROPOSITION:
        return _proposition(pool, dimension_key, value_filter, time_range, notes)
    return MeasurementResolverResult(
        status=MeasurementResolutionStatus.UNKNOWN,
        dimension_key=dimension_key,
        mode=mode,
        notes=("unsupported_mode",),
    )


def observable_value_groups(
    resolved: MeasurementResolverResult,
) -> tuple[ResolvedMeasurementValueGroup, ...]:
    """Value identities already known to the resolver.

    `groups` is empty for temporally_unknown / some ambiguous outcomes even when
    `candidate_observations` carry numeric values. Projection must still see those
    values — this does not change epistemic `status`.
    """
    if resolved.groups:
        return resolved.groups
    if resolved.candidate_observations:
        return tuple(_group_by_value(list(resolved.candidate_observations)))
    return ()


def _latest(
    pool: list[Measurement], dimension_key: str, notes: list[str]
) -> MeasurementResolverResult:
    if not pool:
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.LATEST_OBSERVATION,
            notes=("no_measurement_rows",),
        )

    ordered: list[tuple[dt.datetime, Measurement]] = []
    unordered: list[Measurement] = []
    for m in pool:
        instant = observation_instant(m)
        if instant is None:
            unordered.append(m)
        else:
            ordered.append((instant, m))

    # Unknown-time observations block definitive latest certainty
    if unordered and ordered:
        notes.append("unknown_time_blocks_latest_certainty")
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.AMBIGUOUS,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.LATEST_OBSERVATION,
            candidate_observations=tuple(pool),
            temporal_membership_unknown=True,
            unknown_temporal_contributors=tuple(unordered),
            notes=tuple(notes),
        )
    if unordered and not ordered:
        notes.append("all_observations_time_unknown")
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.TEMPORALLY_UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.LATEST_OBSERVATION,
            candidate_observations=tuple(unordered),
            temporal_membership_unknown=True,
            unknown_temporal_contributors=tuple(unordered),
            notes=tuple(notes),
        )

    max_instant = max(t for t, _ in ordered)
    at_max = [m for t, m in ordered if t == max_instant]
    groups = _group_by_value(at_max)
    notes.append("latest_by_observed_instant")
    if len(groups) == 1:
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.KNOWN_SINGLE,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.LATEST_OBSERVATION,
            groups=tuple(groups),
            candidate_observations=tuple(at_max),
            notes=tuple(notes),
        )
    notes.append("conflicting_values_at_latest_instant")
    return MeasurementResolverResult(
        status=MeasurementResolutionStatus.AMBIGUOUS,
        dimension_key=dimension_key,
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
        groups=tuple(groups),
        candidate_observations=tuple(at_max),
        notes=tuple(notes),
    )


def _at_time(
    pool: list[Measurement],
    dimension_key: str,
    time_range: TimeRange | None,
    notes: list[str],
) -> MeasurementResolverResult:
    """Observation at requested temporal scope — never falls back to latest."""
    if time_range is None:
        notes.append("observation_at_time_requires_time_range")
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
            notes=tuple(notes),
        )
    if not pool:
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
            notes=("no_measurement_rows",),
        )
    matched, unknown, had_unknown = _partition_temporal(pool, time_range)
    if not matched and had_unknown:
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.TEMPORALLY_UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
            candidate_observations=tuple(unknown),
            temporal_membership_unknown=True,
            unknown_temporal_contributors=tuple(unknown),
            notes=("temporal_membership_unknown",),
        )
    if not matched:
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
            notes=("no_temporal_match", "not_current_from_latest"),
        )
    groups = _group_by_value(matched)
    if len(groups) == 1:
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.KNOWN_SINGLE,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
            groups=tuple(groups),
            candidate_observations=tuple(matched),
            temporal_membership_unknown=had_unknown,
            unknown_temporal_contributors=tuple(unknown),
            notes=tuple(notes),
        )
    return MeasurementResolverResult(
        status=MeasurementResolutionStatus.AMBIGUOUS,
        dimension_key=dimension_key,
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        groups=tuple(groups),
        candidate_observations=tuple(matched),
        temporal_membership_unknown=had_unknown,
        unknown_temporal_contributors=tuple(unknown),
        notes=("conflicting_values_at_time",),
    )


def _range(
    pool: list[Measurement],
    dimension_key: str,
    time_range: TimeRange | None,
    notes: list[str],
) -> MeasurementResolverResult:
    if not pool:
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.OBSERVATIONS_IN_RANGE,
            notes=("no_measurement_rows",),
        )
    matched, unknown, had_unknown = _partition_temporal(pool, time_range)
    if not matched and had_unknown:
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.TEMPORALLY_UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.OBSERVATIONS_IN_RANGE,
            candidate_observations=tuple(unknown),
            temporal_membership_unknown=True,
            unknown_temporal_contributors=tuple(unknown),
            notes=("range_only_unknown_membership",),
        )
    if not matched:
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.OBSERVATIONS_IN_RANGE,
            notes=("no_range_match",),
        )
    # Sort known matches by observation instant; segregate unknown (do not interleave)
    known_sorted = sorted(
        matched,
        key=lambda m: (observation_instant(m) or dt.datetime.min.replace(tzinfo=dt.UTC)).isoformat(),
    )
    groups = _group_by_value(known_sorted)
    status = (
        MeasurementResolutionStatus.KNOWN_SINGLE
        if len(groups) == 1 and len(known_sorted) == 1
        else MeasurementResolutionStatus.KNOWN_MULTIPLE
    )
    if had_unknown:
        notes.append("range_has_unknown_temporal_contributors")
    return MeasurementResolverResult(
        status=status,
        dimension_key=dimension_key,
        mode=MeasurementQueryMode.OBSERVATIONS_IN_RANGE,
        groups=tuple(groups),
        candidate_observations=tuple(known_sorted),
        temporal_membership_unknown=had_unknown,
        unknown_temporal_contributors=tuple(unknown),
        notes=tuple(notes),
    )


def _proposition(
    pool: list[Measurement],
    dimension_key: str,
    value_filter: MeasurementValueFilter | None,
    time_range: TimeRange | None,
    notes: list[str],
) -> MeasurementResolverResult:
    if value_filter is None:
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.VALUE_PROPOSITION,
            proposition_answer="unknown",
            notes=("proposition_requires_value_filter",),
        )
    if value_filter.unit is not None and value_filter.currency_code is not None:
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.VALUE_PROPOSITION,
            proposition_answer="unknown",
            notes=("unit_currency_coexist_invalid",),
        )

    # Classify candidates vs filter
    matches: list[Measurement] = []
    incomparable: list[Measurement] = []
    for m in pool:
        kind = filter_comparable(m, value_filter)
        if kind == "match":
            matches.append(m)
        elif kind == "incomparable":
            incomparable.append(m)

    if not matches:
        if incomparable:
            return MeasurementResolverResult(
                status=MeasurementResolutionStatus.UNKNOWN,
                dimension_key=dimension_key,
                mode=MeasurementQueryMode.VALUE_PROPOSITION,
                candidate_observations=tuple(incomparable),
                proposition_answer="unknown",
                notes=("unit_or_currency_incomparable",),
            )
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.VALUE_PROPOSITION,
            proposition_answer="unknown",
            notes=("no_matching_value", "absence_not_no"),
        )

    if time_range is not None:
        matched, unknown, had_unknown = _partition_temporal(matches, time_range)
        if matched:
            # Conflicting other values at same scope?
            others_at_scope, _, _ = _partition_temporal(pool, time_range)
            other_vals = [
                o
                for o in others_at_scope
                if filter_comparable(o, value_filter) == "mismatch"
                and _units_comparable(
                    o.unit, o.currency_code, value_filter.unit, value_filter.currency_code
                )
            ]
            if other_vals:
                return MeasurementResolverResult(
                    status=MeasurementResolutionStatus.AMBIGUOUS,
                    dimension_key=dimension_key,
                    mode=MeasurementQueryMode.VALUE_PROPOSITION,
                    groups=tuple(_group_by_value(matched + other_vals)),
                    candidate_observations=tuple(matched + other_vals),
                    proposition_answer="ambiguous",
                    notes=("conflicting_values_at_scope",),
                )
            groups = _group_by_value(matched)
            return MeasurementResolverResult(
                status=MeasurementResolutionStatus.KNOWN_SINGLE
                if len(groups) == 1
                else MeasurementResolutionStatus.KNOWN_MULTIPLE,
                dimension_key=dimension_key,
                mode=MeasurementQueryMode.VALUE_PROPOSITION,
                groups=tuple(groups),
                candidate_observations=tuple(matched),
                proposition_answer="yes",
                notes=("proposition_temporal_match",),
            )
        if had_unknown:
            return MeasurementResolverResult(
                status=MeasurementResolutionStatus.TEMPORALLY_UNKNOWN,
                dimension_key=dimension_key,
                mode=MeasurementQueryMode.VALUE_PROPOSITION,
                candidate_observations=tuple(unknown),
                temporal_membership_unknown=True,
                unknown_temporal_contributors=tuple(unknown),
                proposition_answer="temporally_unknown",
                notes=("proposition_temporal_unknown",),
            )
        return MeasurementResolverResult(
            status=MeasurementResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            mode=MeasurementQueryMode.VALUE_PROPOSITION,
            proposition_answer="unknown",
            notes=("proposition_no_temporal_match", "absence_not_no"),
        )

    # No time constraint — historical existence of the value
    groups = _group_by_value(matches)
    return MeasurementResolverResult(
        status=MeasurementResolutionStatus.KNOWN_SINGLE
        if len(groups) == 1
        else MeasurementResolutionStatus.KNOWN_MULTIPLE,
        dimension_key=dimension_key,
        mode=MeasurementQueryMode.VALUE_PROPOSITION,
        groups=tuple(groups),
        candidate_observations=tuple(matches),
        proposition_answer="yes",
        notes=("proposition_historical_existence",),
    )
