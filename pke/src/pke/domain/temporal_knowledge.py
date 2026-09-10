"""TemporalKnowledge — representação canônica de tempo parcial ou exato.

I11.16.1 canonical authorities:
- TemporalKind           → temporal form (incl. PARTIAL = relative/no-calendar)
- TemporalGranularity    → calendar resolution when known (YEAR/MONTH/DAY/INSTANT/…)
- TimePrecision          → TimeValue / v9 persistence compatibility (PARTIAL = legacy only)
- TemporalCompleteness   → QueryResult completeness (unrelated)

calendar_granularity() is the semantic calendar authority.
legacy_time_precision() emits TimePrecision for v9 columns only.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pke.domain.value_objects import TimePrecision, TimeValue

# Calendar resolution members — not form/recurrence/epistemic markers.
_CALENDAR_RESOLUTION = frozenset(
    {
        "year",
        "month",
        "day",
        "week",
        "instant",
    }
)


class TemporalKind(StrEnum):
    EXACT = "exact"
    """Legacy label: often day/minute calendar; prefer calendar_granularity() for resolution."""
    RELATIVE = "relative"
    INTERVAL = "interval"
    PARTIAL = "partial"
    """Relative / valid temporal knowledge without complete calendar coordinates — NOT calendar granularity."""
    HABITUAL = "habitual"
    UNKNOWN = "unknown"


class RelationToReference(StrEnum):
    BEFORE = "before"
    AFTER = "after"
    DURING = "during"
    HABITUAL = "habitual"
    UNSPECIFIED = "unspecified"


class OccurrenceStatus(StrEnum):
    HAPPENED = "happened"
    ONGOING = "ongoing"
    PLANNED = "planned"
    HABITUAL = "habitual"
    UNSPECIFIED = "unspecified"


class TemporalUnknownReason(StrEnum):
    NOT_PROVIDED = "not_provided"
    FORGOTTEN = "forgotten"
    UNRESOLVED = "unresolved"
    UNKNOWN = "unknown"


class TemporalGranularity(StrEnum):
    """Canonical calendar-resolution vocabulary (I11.16.1).

    YEAR/MONTH/DAY/WEEK/INSTANT = asserted calendar resolution.
    INTERVAL/RECURRING/UNSPECIFIED = non-resolution markers (not calendar granularity).
    """

    INSTANT = "instant"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    INTERVAL = "interval"
    RECURRING = "recurring"
    UNSPECIFIED = "unspecified"


class TemporalSourceKind(StrEnum):
    EXPLICIT_EXPRESSION = "explicit_expression"
    GRAMMATICAL_EVIDENCE = "grammatical_evidence"
    USER_UNCERTAINTY = "user_uncertainty"
    INFERRED = "inferred"
    RESOLVED = "resolved"


def granularity_from_time_precision(precision: TimePrecision) -> TemporalGranularity | None:
    """Map TimeValue.precision → calendar resolution. Never invent from PARTIAL."""
    if precision is TimePrecision.MINUTE:
        return TemporalGranularity.INSTANT
    if precision is TimePrecision.DAY:
        return TemporalGranularity.DAY
    # PERIOD/RECURRING/DAY_PERIOD/APPROX_DAY/PARTIAL are not pure calendar resolution
    return None


class TemporalKnowledge(BaseModel):
    """Tempo canônico — calendário opcional, relação temporal explícita."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: TemporalKind
    original_text: str
    calendar: TimeValue | None = None
    relation_to_reference: RelationToReference | None = None
    occurrence_status: OccurrenceStatus | None = None
    unknown_reason: TemporalUnknownReason | None = None
    interval_start: dt.date | None = None
    interval_end: dt.date | None = None
    granularity: TemporalGranularity = TemporalGranularity.UNSPECIFIED
    tense_evidence: str | None = None
    source_kind: TemporalSourceKind | None = None

    @model_validator(mode="after")
    def _partial_requires_relation(self) -> TemporalKnowledge:
        if self.kind is TemporalKind.PARTIAL:
            if self.relation_to_reference is None or self.relation_to_reference is RelationToReference.UNSPECIFIED:
                raise ValueError("PARTIAL exige relation_to_reference")
        return self

    @classmethod
    def from_calendar(
        cls,
        calendar: TimeValue,
        *,
        kind: TemporalKind = TemporalKind.EXACT,
        source_kind: TemporalSourceKind = TemporalSourceKind.RESOLVED,
        granularity: TemporalGranularity | None = None,
    ) -> TemporalKnowledge:
        resolved_kind = kind
        if calendar.recurrence is not None and kind is TemporalKind.EXACT:
            resolved_kind = TemporalKind.HABITUAL
        if calendar.period_start is not None and calendar.period_end is not None:
            resolved_kind = TemporalKind.INTERVAL
        if calendar.resolution_rule and calendar.resolution_rule.startswith("relative."):
            if resolved_kind is TemporalKind.EXACT:
                resolved_kind = TemporalKind.RELATIVE
        gran = granularity
        if gran is None:
            gran = granularity_from_time_precision(calendar.precision)
        if gran is None:
            gran = TemporalGranularity.UNSPECIFIED
        return cls(
            kind=resolved_kind,
            original_text=calendar.original_text,
            calendar=calendar,
            granularity=gran,
            source_kind=source_kind,
        )

    @classmethod
    def partial_past(
        cls,
        original_text: str,
        *,
        unknown_reason: TemporalUnknownReason = TemporalUnknownReason.NOT_PROVIDED,
        tense_evidence: str | None = None,
        source_kind: TemporalSourceKind = TemporalSourceKind.GRAMMATICAL_EVIDENCE,
    ) -> TemporalKnowledge:
        return cls(
            kind=TemporalKind.PARTIAL,
            original_text=original_text,
            relation_to_reference=RelationToReference.BEFORE,
            occurrence_status=OccurrenceStatus.HAPPENED,
            unknown_reason=unknown_reason,
            tense_evidence=tense_evidence,
            source_kind=source_kind,
            granularity=TemporalGranularity.UNSPECIFIED,
        )

    @classmethod
    def partial_future(
        cls,
        original_text: str,
        *,
        unknown_reason: TemporalUnknownReason = TemporalUnknownReason.NOT_PROVIDED,
        tense_evidence: str | None = None,
    ) -> TemporalKnowledge:
        return cls(
            kind=TemporalKind.PARTIAL,
            original_text=original_text,
            relation_to_reference=RelationToReference.AFTER,
            occurrence_status=OccurrenceStatus.PLANNED,
            unknown_reason=unknown_reason,
            tense_evidence=tense_evidence,
            source_kind=TemporalSourceKind.GRAMMATICAL_EVIDENCE,
            granularity=TemporalGranularity.UNSPECIFIED,
        )

    @classmethod
    def partial_ongoing(
        cls,
        original_text: str = "",
        *,
        tense_evidence: str | None = None,
    ) -> TemporalKnowledge:
        return cls(
            kind=TemporalKind.PARTIAL,
            original_text=original_text,
            relation_to_reference=RelationToReference.DURING,
            occurrence_status=OccurrenceStatus.ONGOING,
            unknown_reason=TemporalUnknownReason.NOT_PROVIDED,
            tense_evidence=tense_evidence,
            source_kind=TemporalSourceKind.GRAMMATICAL_EVIDENCE,
            granularity=TemporalGranularity.UNSPECIFIED,
        )

    @classmethod
    def calendar_occurrence(
        cls,
        original_text: str,
        *,
        interval_start: dt.date,
        interval_end: dt.date,
        granularity: TemporalGranularity,
        relation_to_reference: RelationToReference = RelationToReference.BEFORE,
        occurrence_status: OccurrenceStatus = OccurrenceStatus.HAPPENED,
    ) -> TemporalKnowledge:
        """Coarse calendar occurrence window (YEAR/MONTH/DAY…) — not continuous validity."""
        if granularity.value not in _CALENDAR_RESOLUTION:
            raise ValueError(f"calendar_occurrence requires calendar resolution, got {granularity}")
        return cls(
            kind=TemporalKind.INTERVAL,
            original_text=original_text,
            relation_to_reference=relation_to_reference,
            occurrence_status=occurrence_status,
            interval_start=interval_start,
            interval_end=interval_end,
            granularity=granularity,
            source_kind=TemporalSourceKind.EXPLICIT_EXPRESSION,
        )

    @classmethod
    def occurrence_year(
        cls,
        year: int,
        original_text: str = "",
        *,
        occurrence_status: OccurrenceStatus = OccurrenceStatus.HAPPENED,
    ) -> TemporalKnowledge:
        return cls.calendar_occurrence(
            original_text or str(year),
            interval_start=dt.date(year, 1, 1),
            interval_end=dt.date(year, 12, 31),
            granularity=TemporalGranularity.YEAR,
            occurrence_status=occurrence_status,
        )

    @classmethod
    def occurrence_month(
        cls,
        year: int,
        month: int,
        original_text: str = "",
        *,
        occurrence_status: OccurrenceStatus = OccurrenceStatus.HAPPENED,
    ) -> TemporalKnowledge:
        import calendar as cal

        last = cal.monthrange(year, month)[1]
        return cls.calendar_occurrence(
            original_text or f"{year}-{month:02d}",
            interval_start=dt.date(year, month, 1),
            interval_end=dt.date(year, month, last),
            granularity=TemporalGranularity.MONTH,
            occurrence_status=occurrence_status,
        )

    @classmethod
    def partial_interval(
        cls,
        original_text: str,
        *,
        interval_start: dt.date,
        interval_end: dt.date,
        granularity: TemporalGranularity,
        relation_to_reference: RelationToReference = RelationToReference.BEFORE,
        occurrence_status: OccurrenceStatus = OccurrenceStatus.HAPPENED,
    ) -> TemporalKnowledge:
        """Compatibility alias → calendar_occurrence (not epistemic PARTIAL)."""
        return cls.calendar_occurrence(
            original_text,
            interval_start=interval_start,
            interval_end=interval_end,
            granularity=granularity,
            relation_to_reference=relation_to_reference,
            occurrence_status=occurrence_status,
        )

    def has_calendar_anchor(self) -> bool:
        if self.calendar is None:
            return False
        c = self.calendar
        return any(
            [
                c.instant is not None,
                c.date is not None,
                c.period_start is not None,
                c.recurrence is not None,
            ]
        )

    def is_persistable(self) -> bool:
        if self.has_calendar_anchor():
            return True
        if self.kind is TemporalKind.PARTIAL:
            return self.relation_to_reference is not RelationToReference.UNSPECIFIED
        if self.kind is TemporalKind.INTERVAL and self.interval_start and self.interval_end:
            return True
        return False

    @classmethod
    def unknown(
        cls,
        original_text: str = "",
        *,
        unknown_reason: TemporalUnknownReason = TemporalUnknownReason.NOT_PROVIDED,
        tense_evidence: str | None = None,
    ) -> TemporalKnowledge:
        return cls(
            kind=TemporalKind.UNKNOWN,
            original_text=original_text,
            unknown_reason=unknown_reason,
            tense_evidence=tense_evidence,
            source_kind=TemporalSourceKind.USER_UNCERTAINTY,
            granularity=TemporalGranularity.UNSPECIFIED,
        )

    def calendar_granularity(self) -> TemporalGranularity | None:
        """Canonical calendar resolution. None = no calendar coordinates (not PARTIAL)."""
        if self.granularity.value in _CALENDAR_RESOLUTION:
            return self.granularity
        if self.calendar is not None:
            return granularity_from_time_precision(self.calendar.precision)
        return None

    def legacy_time_precision(self) -> TimePrecision:
        """v9 persistence compatibility only — not canonical semantic authority.

        Emits TimePrecision.PARTIAL only when there is no calendar resolution to store
        (relative/unknown). Year/month use PERIOD (bound-like), never PARTIAL.
        """
        if self.calendar is not None:
            return self.calendar.precision
        gran = self.calendar_granularity()
        if gran is TemporalGranularity.INSTANT:
            return TimePrecision.MINUTE
        if gran is TemporalGranularity.DAY:
            return TimePrecision.DAY
        if gran in {
            TemporalGranularity.MONTH,
            TemporalGranularity.YEAR,
            TemporalGranularity.WEEK,
        }:
            return TimePrecision.PERIOD
        return TimePrecision.PARTIAL

    def calendar_precision(self) -> TimePrecision:
        """Deprecated bridge — use calendar_granularity() / legacy_time_precision().

        Retained for call-site compatibility; does NOT map TemporalKind.PARTIAL →
        epistemic calendar PARTIAL as semantic truth (delegates to legacy_time_precision).
        """
        return self.legacy_time_precision()
