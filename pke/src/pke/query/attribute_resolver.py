"""AttributeResolver — epistemic current-value resolution (not repository authority).

created_at / insertion order / largest id are NEVER used as current-truth selectors.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.query.spec import AttributeQueryMode, AttributeValueFilter, FactVersionPolicy, SortKey, TimeRange
from pke.temporal.membership import (
    TemporalMembership,
    derive_temporal_membership_role,
    range_membership,
)


class AttributeResolutionStatus(StrEnum):
    KNOWN_SINGLE = "known_single"
    KNOWN_MULTIPLE = "known_multiple"
    UNKNOWN = "unknown"
    TEMPORALLY_UNKNOWN = "temporally_unknown"
    AMBIGUOUS = "ambiguous"


PropositionAnswer = Literal["yes", "no", "unknown", "ambiguous", "temporally_unknown"]


@dataclass(frozen=True)
class AttributeValueIdentity:
    value_kind: AttributeValueKind
    text_value: str | None = None
    numeric_value: Decimal | None = None
    unit: str | None = None
    year_value: int | None = None
    date_value: dt.date | None = None
    concept_value_id: str | None = None

    def as_key(self) -> tuple[Any, ...]:
        return (
            self.value_kind.value,
            self.text_value,
            self.numeric_value,
            self.unit,
            self.year_value,
            self.date_value,
            self.concept_value_id,
        )


@dataclass(frozen=True)
class ResolvedAttributeValueGroup:
    identity: AttributeValueIdentity
    assertions: tuple[EntityAttribute, ...]
    support_count: int


@dataclass(frozen=True)
class AttributeResolverResult:
    status: AttributeResolutionStatus
    dimension_key: str
    groups: tuple[ResolvedAttributeValueGroup, ...] = ()
    candidate_assertions: tuple[EntityAttribute, ...] = ()
    temporal_membership_unknown: bool = False
    proposition_answer: PropositionAnswer | None = None
    notes: tuple[str, ...] = ()


def value_identity_of(attr: EntityAttribute) -> AttributeValueIdentity:
    return AttributeValueIdentity(
        value_kind=attr.value_kind,
        text_value=attr.text_value,
        numeric_value=attr.numeric_value,
        unit=attr.unit,
        year_value=attr.year_value,
        date_value=attr.date_value,
        concept_value_id=attr.concept_value_id,
    )


def filter_matches(attr: EntityAttribute, filt: AttributeValueFilter) -> bool:
    if attr.value_kind is not filt.value_kind:
        return False
    if filt.value_kind is AttributeValueKind.TEXT:
        return attr.text_value == filt.text_value
    if filt.value_kind is AttributeValueKind.NUMBER:
        if attr.numeric_value != filt.numeric_value:
            return False
        # Unit conversion NOT in scope — require exact unit equality when both set.
        if filt.unit is not None and attr.unit is not None and attr.unit != filt.unit:
            return False
        return True
    if filt.value_kind is AttributeValueKind.YEAR:
        return attr.year_value == filt.year_value
    if filt.value_kind is AttributeValueKind.DATE:
        return attr.date_value == filt.date_value
    if filt.value_kind is AttributeValueKind.CONCEPT:
        return attr.concept_value_id == filt.concept_value_id
    return False


def _group_by_value(assertions: list[EntityAttribute]) -> list[ResolvedAttributeValueGroup]:
    buckets: dict[tuple[Any, ...], list[EntityAttribute]] = {}
    order: list[tuple[Any, ...]] = []
    for attr in assertions:
        key = value_identity_of(attr).as_key()
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(attr)
    groups: list[ResolvedAttributeValueGroup] = []
    for key in order:
        members = buckets[key]
        groups.append(
            ResolvedAttributeValueGroup(
                identity=value_identity_of(members[0]),
                assertions=tuple(members),
                support_count=len(members),
            )
        )
    return groups


def _partition_temporal(
    assertions: list[EntityAttribute], time_range: TimeRange | None
) -> tuple[list[EntityAttribute], list[EntityAttribute], bool]:
    """Returns (match, unknown_pool, had_unknown). NO_MATCH discarded."""
    if time_range is None:
        return list(assertions), [], False
    matched: list[EntityAttribute] = []
    unknown: list[EntityAttribute] = []
    for attr in assertions:
        membership = range_membership(
            attr.temporal,
            time_range,
            role=derive_temporal_membership_role("attribute", "temporal"),
        )
        if membership is TemporalMembership.MATCH:
            matched.append(attr)
        elif membership is TemporalMembership.UNKNOWN:
            unknown.append(attr)
    return matched, unknown, bool(unknown)


def resolve_attribute_query(
    assertions: list[EntityAttribute],
    *,
    dimension_key: str,
    mode: AttributeQueryMode,
    value_filter: AttributeValueFilter | None = None,
    time_range: TimeRange | None = None,
    version_policy: FactVersionPolicy = FactVersionPolicy.CURRENT,
    sort: SortKey | None = None,
    limit: int | None = None,
) -> AttributeResolverResult:
    """Epistemic Attribute resolution over candidate assertions.

    Repository supplies candidates only; this function decides status.
    """
    pool = [a for a in assertions if a.dimension_key == dimension_key]
    notes: list[str] = []

    if mode is AttributeQueryMode.HISTORICAL_EXISTENCE:
        return _historical_existence(pool, dimension_key, value_filter, time_range, notes)

    if mode is AttributeQueryMode.PROPOSITION:
        return _proposition(pool, dimension_key, value_filter, time_range, notes)

    return _value_lookup(
        pool,
        dimension_key,
        time_range,
        notes,
        version_policy=version_policy,
        sort=sort,
        limit=limit,
    )


def _value_lookup(
    pool: list[EntityAttribute],
    dimension_key: str,
    time_range: TimeRange | None,
    notes: list[str],
    *,
    version_policy: FactVersionPolicy = FactVersionPolicy.CURRENT,
    sort: SortKey | None = None,
    limit: int | None = None,
) -> AttributeResolverResult:
    if not pool:
        return AttributeResolverResult(
            status=AttributeResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            notes=("no_attribute_rows",),
        )

    matched, unknown, had_unknown = _partition_temporal(pool, time_range)
    if time_range is not None:
        if not matched and had_unknown:
            return AttributeResolverResult(
                status=AttributeResolutionStatus.TEMPORALLY_UNKNOWN,
                dimension_key=dimension_key,
                candidate_assertions=tuple(unknown),
                temporal_membership_unknown=True,
                notes=("temporal_membership_unknown",),
            )
        if not matched:
            return AttributeResolverResult(
                status=AttributeResolutionStatus.UNKNOWN,
                dimension_key=dimension_key,
                notes=("no_temporal_match",),
            )
        working = matched
    else:
        working = pool

    if version_policy is FactVersionPolicy.HISTORY:
        return _historical_value_lookup(
            working, dimension_key, notes, sort=sort, limit=limit, had_unknown=had_unknown
        )

    current = [a for a in working if a.is_current]
    if current:
        groups = _group_by_value(current)
        if len(groups) == 1:
            return AttributeResolverResult(
                status=AttributeResolutionStatus.KNOWN_SINGLE,
                dimension_key=dimension_key,
                groups=tuple(groups),
                candidate_assertions=tuple(current),
                temporal_membership_unknown=had_unknown,
                notes=tuple(notes),
            )
        # Competing current values — never pick by created_at
        notes.append("multiple_current_values")
        return AttributeResolverResult(
            status=AttributeResolutionStatus.AMBIGUOUS,
            dimension_key=dimension_key,
            groups=tuple(groups),
            candidate_assertions=tuple(current),
            temporal_membership_unknown=had_unknown,
            notes=tuple(notes),
        )

    # No is_current bookkeeping among candidates — do not invent current via created_at
    notes.append("no_current_bookkeeping")
    return AttributeResolverResult(
        status=AttributeResolutionStatus.TEMPORALLY_UNKNOWN,
        dimension_key=dimension_key,
        candidate_assertions=tuple(working),
        temporal_membership_unknown=True,
        notes=tuple(notes),
    )


def _historical_value_lookup(
    working: list[EntityAttribute],
    dimension_key: str,
    notes: list[str],
    *,
    sort: SortKey | None,
    limit: int | None,
    had_unknown: bool,
) -> AttributeResolverResult:
    """Previous/first values from closed assertions — temporal order, not created_at."""
    from pke.temporal.membership import sort_key as temporal_sort_key

    historical = [a for a in working if not a.is_current]
    if not historical:
        return AttributeResolverResult(
            status=AttributeResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            notes=("no_previous_value",),
        )
    reverse = sort is not SortKey.EVENT_TIME_ASC
    ranked = sorted(historical, key=lambda a: (temporal_sort_key(a.temporal), a.id), reverse=reverse)
    selected = ranked[: limit or len(ranked)]
    groups = _group_by_value(selected)
    notes.append("historical_value_lookup")
    status = (
        AttributeResolutionStatus.KNOWN_SINGLE
        if len(groups) == 1
        else AttributeResolutionStatus.KNOWN_MULTIPLE
    )
    return AttributeResolverResult(
        status=status,
        dimension_key=dimension_key,
        groups=tuple(groups),
        candidate_assertions=tuple(selected),
        temporal_membership_unknown=had_unknown,
        notes=tuple(notes),
    )


def _historical_existence(
    pool: list[EntityAttribute],
    dimension_key: str,
    value_filter: AttributeValueFilter | None,
    time_range: TimeRange | None,
    notes: list[str],
) -> AttributeResolverResult:
    if value_filter is None:
        return AttributeResolverResult(
            status=AttributeResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            notes=("historical_existence_requires_value_filter",),
            proposition_answer="unknown",
        )
    matching = [a for a in pool if filter_matches(a, value_filter)]
    if not matching:
        return AttributeResolverResult(
            status=AttributeResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            notes=("no_matching_value",),
            proposition_answer="unknown",
        )

    if time_range is not None:
        matched, unknown, had_unknown = _partition_temporal(matching, time_range)
        if matched:
            groups = _group_by_value(matched)
            return AttributeResolverResult(
                status=AttributeResolutionStatus.KNOWN_SINGLE
                if len(groups) == 1
                else AttributeResolutionStatus.KNOWN_MULTIPLE,
                dimension_key=dimension_key,
                groups=tuple(groups),
                candidate_assertions=tuple(matched),
                proposition_answer="yes",
                notes=("historical_existence_calendar_match",),
            )
        if had_unknown:
            return AttributeResolverResult(
                status=AttributeResolutionStatus.TEMPORALLY_UNKNOWN,
                dimension_key=dimension_key,
                candidate_assertions=tuple(unknown),
                temporal_membership_unknown=True,
                proposition_answer="temporally_unknown",
                notes=("historical_existence_calendar_unknown",),
            )
        return AttributeResolverResult(
            status=AttributeResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            proposition_answer="unknown",
            notes=("historical_existence_no_match",),
        )

    # No calendar constraint: historical/any evidence of the value is enough for existence
    groups = _group_by_value(matching)
    return AttributeResolverResult(
        status=AttributeResolutionStatus.KNOWN_SINGLE
        if len(groups) == 1
        else AttributeResolutionStatus.KNOWN_MULTIPLE,
        dimension_key=dimension_key,
        groups=tuple(groups),
        candidate_assertions=tuple(matching),
        proposition_answer="yes",
        notes=("historical_existence_without_calendar",),
    )


def _proposition(
    pool: list[EntityAttribute],
    dimension_key: str,
    value_filter: AttributeValueFilter | None,
    time_range: TimeRange | None,
    notes: list[str],
) -> AttributeResolverResult:
    if value_filter is None:
        return AttributeResolverResult(
            status=AttributeResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            proposition_answer="unknown",
            notes=("proposition_requires_value_filter",),
        )

    lookup = _value_lookup(pool, dimension_key, time_range, notes)
    if lookup.status is AttributeResolutionStatus.UNKNOWN:
        return AttributeResolverResult(
            status=AttributeResolutionStatus.UNKNOWN,
            dimension_key=dimension_key,
            proposition_answer="unknown",
            notes=lookup.notes + ("proposition_no_knowledge",),
        )
    if lookup.status is AttributeResolutionStatus.TEMPORALLY_UNKNOWN:
        return AttributeResolverResult(
            status=AttributeResolutionStatus.TEMPORALLY_UNKNOWN,
            dimension_key=dimension_key,
            candidate_assertions=lookup.candidate_assertions,
            temporal_membership_unknown=True,
            proposition_answer="temporally_unknown",
            notes=lookup.notes,
        )
    if lookup.status is AttributeResolutionStatus.AMBIGUOUS:
        matching_groups = [g for g in lookup.groups if _group_matches_filter(g, value_filter)]
        if matching_groups and len(lookup.groups) > 1:
            return AttributeResolverResult(
                status=AttributeResolutionStatus.AMBIGUOUS,
                dimension_key=dimension_key,
                groups=lookup.groups,
                candidate_assertions=lookup.candidate_assertions,
                proposition_answer="ambiguous",
                notes=lookup.notes + ("proposition_amid_ambiguity",),
            )
        if matching_groups:
            return AttributeResolverResult(
                status=AttributeResolutionStatus.AMBIGUOUS,
                dimension_key=dimension_key,
                groups=lookup.groups,
                candidate_assertions=lookup.candidate_assertions,
                proposition_answer="yes",
                notes=lookup.notes + ("proposition_match_under_ambiguity",),
            )
        # Different known values — without functional cardinality, do NOT infer NO
        return AttributeResolverResult(
            status=AttributeResolutionStatus.AMBIGUOUS,
            dimension_key=dimension_key,
            groups=lookup.groups,
            candidate_assertions=lookup.candidate_assertions,
            proposition_answer="unknown",
            notes=lookup.notes + ("no_functional_cardinality_no_inferred",),
        )

    # KNOWN_SINGLE or KNOWN_MULTIPLE
    matching_groups = [g for g in lookup.groups if _group_matches_filter(g, value_filter)]
    if matching_groups:
        return AttributeResolverResult(
            status=lookup.status,
            dimension_key=dimension_key,
            groups=lookup.groups,
            candidate_assertions=lookup.candidate_assertions,
            proposition_answer="yes",
            notes=lookup.notes + ("proposition_match",),
        )
    # Known different value(s) — NO only if dimension proven functional (not available)
    notes.append("no_functional_cardinality_no_inferred")
    return AttributeResolverResult(
        status=lookup.status,
        dimension_key=dimension_key,
        groups=lookup.groups,
        candidate_assertions=lookup.candidate_assertions,
        proposition_answer="unknown",
        notes=tuple(notes),
    )


def _group_matches_filter(
    group: ResolvedAttributeValueGroup, filt: AttributeValueFilter
) -> bool:
    identity = group.identity
    if identity.value_kind is not filt.value_kind:
        return False
    if filt.value_kind is AttributeValueKind.TEXT:
        return identity.text_value == filt.text_value
    if filt.value_kind is AttributeValueKind.NUMBER:
        if identity.numeric_value != filt.numeric_value:
            return False
        if filt.unit is not None and identity.unit is not None and identity.unit != filt.unit:
            return False
        return True
    if filt.value_kind is AttributeValueKind.YEAR:
        return identity.year_value == filt.year_value
    if filt.value_kind is AttributeValueKind.DATE:
        return identity.date_value == filt.date_value
    if filt.value_kind is AttributeValueKind.CONCEPT:
        return identity.concept_value_id == filt.concept_value_id
    return False
