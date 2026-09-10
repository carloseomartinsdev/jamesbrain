"""Resolve IrTime estruturado + contexto → TemporalKnowledge."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict

from pke.domain.temporal_knowledge import (
    OccurrenceStatus,
    RelationToReference,
    TemporalKind,
    TemporalKnowledge,
    TemporalSourceKind,
    TemporalUnknownReason,
)
from pke.domain.value_objects import (
    Confidence,
    DayPeriod,
    EventStatus,
    Qualifier,
    Recurrence,
    RelativeDay,
    TimePrecision,
    TimeValue,
    UserContext,
    WeekdayPolicy,
)
from pke.interpretation.models import IrTime
from pke.resolution.errors import (
    ImpossibleTimeError,
    InsufficientTemporalContextError,
    InvalidTimezoneError,
    TemporalConflictError,
)

_FUTURE_STATUSES = frozenset({EventStatus.SCHEDULED, EventStatus.PENDING})
_PAST_STATUSES = frozenset({EventStatus.COMPLETED, EventStatus.CANCELLED})


class TemporalContext(BaseModel):
    """Contexto explícito. O resolver não lê relógio de parede nem infere status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user: UserContext
    event_status: EventStatus | None = None
    reference_at: dt.datetime | None = None


class TemporalResolver:
    def resolve(self, ir: IrTime, ctx: TemporalContext) -> TemporalKnowledge:
        try:
            calendar = self._resolve_calendar(ir, ctx)
            return TemporalKnowledge.from_calendar(calendar)
        except InsufficientTemporalContextError:
            partial = self._try_partial(ir, ctx)
            if partial is not None:
                return partial
            raise

    def _try_partial(self, ir: IrTime, ctx: TemporalContext) -> TemporalKnowledge | None:
        if ir.relation_to_reference is not None or ir.occurrence_status is not None:
            return self._partial_from_ir(ir)
        if ir.unknown_reason is not None:
            return self._partial_from_ir(ir, default_relation=RelationToReference.BEFORE)
        interval = self._try_partial_interval(ir, ctx)
        if interval is not None:
            return interval
        if ir.occurrence_status is OccurrenceStatus.ONGOING and not self._has_structured_calendar(ir):
            return TemporalKnowledge.partial_ongoing(
                ir.original_text,
                tense_evidence=ir.tense_evidence,
            )
        if ctx.event_status in _PAST_STATUSES and not self._has_structured_calendar(ir):
            return TemporalKnowledge.partial_past(
                ir.original_text,
                unknown_reason=ir.unknown_reason or TemporalUnknownReason.NOT_PROVIDED,
                tense_evidence=ir.tense_evidence,
            )
        if ctx.event_status in _FUTURE_STATUSES and not self._has_structured_calendar(ir):
            if ir.occurrence_status is OccurrenceStatus.PLANNED or ir.tense_evidence:
                return TemporalKnowledge.partial_future(
                    ir.original_text,
                    unknown_reason=ir.unknown_reason or TemporalUnknownReason.NOT_PROVIDED,
                    tense_evidence=ir.tense_evidence,
                )
        return None

    def _partial_from_ir(
        self,
        ir: IrTime,
        *,
        default_relation: RelationToReference = RelationToReference.UNSPECIFIED,
    ) -> TemporalKnowledge:
        relation = ir.relation_to_reference or default_relation
        if relation is RelationToReference.UNSPECIFIED:
            if ir.occurrence_status is OccurrenceStatus.PLANNED:
                relation = RelationToReference.AFTER
            else:
                relation = RelationToReference.BEFORE
        occurrence = ir.occurrence_status
        if occurrence is None:
            if relation is RelationToReference.AFTER:
                occurrence = OccurrenceStatus.PLANNED
            else:
                occurrence = OccurrenceStatus.HAPPENED
        source = TemporalSourceKind.GRAMMATICAL_EVIDENCE
        if ir.unknown_reason in {
            TemporalUnknownReason.FORGOTTEN,
            TemporalUnknownReason.UNRESOLVED,
        }:
            source = TemporalSourceKind.USER_UNCERTAINTY
        return TemporalKnowledge(
            kind=TemporalKind.PARTIAL,
            original_text=ir.original_text,
            relation_to_reference=relation,
            occurrence_status=occurrence,
            unknown_reason=ir.unknown_reason or TemporalUnknownReason.NOT_PROVIDED,
            tense_evidence=ir.tense_evidence,
            source_kind=source,
        )

    def _try_partial_interval(self, ir: IrTime, ctx: TemporalContext) -> TemporalKnowledge | None:
        # Year-only → YEAR occurrence window (not TimePrecision.PARTIAL)
        if ir.partial_month is None and ir.partial_year is not None:
            return TemporalKnowledge.occurrence_year(
                ir.partial_year,
                ir.original_text or str(ir.partial_year),
            )
        if ir.partial_month is None:
            return None
        zone = self._zone(ir.timezone or ctx.user.timezone)
        reference = self._reference(ir, ctx, zone)
        year = ir.partial_year
        if year is None and reference is not None:
            year = reference.year
        if year is None:
            # Month without year: relative incomplete — no invented year/day
            return TemporalKnowledge.partial_past(
                ir.original_text,
                unknown_reason=ir.unknown_reason or TemporalUnknownReason.UNRESOLVED,
                tense_evidence=ir.tense_evidence,
            )
        return TemporalKnowledge.occurrence_month(
            year,
            ir.partial_month,
            ir.original_text or f"{year}-{ir.partial_month:02d}",
        )

    def _has_structured_calendar(self, ir: IrTime) -> bool:
        return any(
            [
                ir.relative_day is not None,
                ir.weekday is not None,
                ir.date is not None,
                ir.instant is not None,
                ir.recurrence is not None,
                ir.period_start is not None and ir.period_end is not None,
                ir.partial_month is not None,
                ir.partial_year is not None,
            ]
        )

    def _resolve_calendar(self, ir: IrTime, ctx: TemporalContext) -> TimeValue:
        zone = self._zone(ir.timezone or ctx.user.timezone)
        reference = self._reference(ir, ctx, zone)
        recurrence = self._recurrence(ir)
        resolved_date = self._resolve_date(ir, ctx, reference, zone)
        time_of_day = ir.time_of_day
        instant = self._resolve_instant(ir, resolved_date, time_of_day, zone)
        day_period = ir.day_period
        precision = self._precision(ir, resolved_date, time_of_day, recurrence, day_period)
        self._reject_conflicts(ir, resolved_date, instant, zone)
        if resolved_date is None and instant is None and recurrence is None:
            if ir.period_start is None or ir.period_end is None:
                raise InsufficientTemporalContextError(
                    "IrTime sem expressão estruturada "
                    "(relative_day, weekday, date, instant, recurrence ou período)"
                )
        period_start, period_end = self._periods(ir, zone)
        rule = self._rule(ir, ctx)
        return TimeValue(
            original_text=ir.original_text,
            interpretation=ir.interpretation,
            instant=instant,
            date=resolved_date or (instant.date() if instant else None),
            time_of_day=time_of_day if time_of_day is not None else (
                instant.time() if instant and precision is TimePrecision.MINUTE else None
            ),
            period_start=period_start,
            period_end=period_end,
            timezone=str(zone),
            recurrence=recurrence,
            precision=precision,
            confidence=ir.confidence or self._default_confidence(precision),
            reference_at=reference,
            reference_timezone=str(zone) if reference is not None else None,
            day_period=day_period,
            resolution_rule=rule,
        )

    def _zone(self, name: str) -> ZoneInfo:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, KeyError) as exc:
            raise InvalidTimezoneError(name) from exc

    def _reference(
        self,
        ir: IrTime,
        ctx: TemporalContext,
        zone: ZoneInfo,
    ) -> dt.datetime | None:
        raw = ctx.reference_at or ir.reference_at or ctx.user.now
        if raw is None:
            return None
        return _as_aware(raw, zone)

    def _require_reference(self, reference: dt.datetime | None) -> dt.datetime:
        if reference is None:
            raise InsufficientTemporalContextError(
                "expressão relativa exige reference_at (TemporalContext, IrTime ou UserContext.now)"
            )
        return reference

    def _resolve_date(
        self,
        ir: IrTime,
        ctx: TemporalContext,
        reference: dt.datetime | None,
        zone: ZoneInfo,
    ) -> dt.date | None:
        from_relative = self._from_relative(ir, reference)
        from_weekday = self._from_weekday(ir, ctx, reference)
        from_absolute = ir.date
        if ir.instant is not None and from_absolute is None and from_relative is None:
            from_absolute = _as_aware(ir.instant, zone).date()

        candidates = [d for d in (from_relative, from_weekday, from_absolute) if d is not None]
        unique = set(candidates)
        if len(unique) > 1:
            raise TemporalConflictError(
                f"datas divergentes na IR: {sorted(unique)}"
            )
        return next(iter(unique), None)

    def _from_relative(self, ir: IrTime, reference: dt.datetime | None) -> dt.date | None:
        if ir.relative_day is None:
            return None
        ref = self._require_reference(reference)
        base = ref.date()
        if ir.relative_day is RelativeDay.TODAY:
            return base
        if ir.relative_day is RelativeDay.YESTERDAY:
            return base - dt.timedelta(days=1)
        if ir.relative_day is RelativeDay.TOMORROW:
            return base + dt.timedelta(days=1)
        raise ImpossibleTimeError(f"relative_day desconhecido: {ir.relative_day}")

    def _from_weekday(
        self,
        ir: IrTime,
        ctx: TemporalContext,
        reference: dt.datetime | None,
    ) -> dt.date | None:
        if ir.weekday is None:
            return None
        if not 0 <= ir.weekday <= 6:
            raise ImpossibleTimeError(f"weekday inválido: {ir.weekday}")
        policy = ir.weekday_policy
        if policy is None and ctx.event_status is not None:
            policy = WeekdayPolicy.FROM_EVENT_STATUS
        if policy is None:
            raise InsufficientTemporalContextError(
                "weekday exige weekday_policy ou TemporalContext.event_status"
            )
        ref = self._require_reference(reference)
        effective = self._effective_weekday_policy(policy, ctx.event_status)
        return _shift_weekday(ref.date(), ir.weekday, effective)

    def _effective_weekday_policy(
        self,
        policy: WeekdayPolicy,
        event_status: EventStatus | None,
    ) -> WeekdayPolicy:
        if policy is not WeekdayPolicy.FROM_EVENT_STATUS:
            return policy
        if event_status is None:
            raise InsufficientTemporalContextError(
                "weekday_policy=from_event_status exige event_status"
            )
        if event_status in _FUTURE_STATUSES:
            return WeekdayPolicy.NEXT
        if event_status in _PAST_STATUSES:
            return WeekdayPolicy.PREVIOUS
        raise InsufficientTemporalContextError(
            f"event_status {event_status} não define orientação temporal"
        )

    def _resolve_instant(
        self,
        ir: IrTime,
        resolved_date: dt.date | None,
        time_of_day: dt.time | None,
        zone: ZoneInfo,
    ) -> dt.datetime | None:
        if ir.instant is not None:
            return _as_aware(ir.instant, zone)
        if resolved_date is not None and time_of_day is not None:
            return dt.datetime.combine(resolved_date, time_of_day, tzinfo=zone)
        if time_of_day is not None and resolved_date is None and ir.recurrence is None:
            raise InsufficientTemporalContextError(
                "time_of_day exige date, relative_day, weekday ou instant na IR"
            )
        return None

    def _recurrence(self, ir: IrTime) -> Recurrence | None:
        rec = ir.recurrence
        if rec is None:
            return None
        if rec.freq == "monthly" and rec.by_monthday is None:
            raise InsufficientTemporalContextError(
                "recorrência monthly exige by_monthday"
            )
        return rec

    def _periods(
        self,
        ir: IrTime,
        zone: ZoneInfo,
    ) -> tuple[dt.datetime | None, dt.datetime | None]:
        start = _as_aware(ir.period_start, zone) if ir.period_start else None
        end = _as_aware(ir.period_end, zone) if ir.period_end else None
        if start and end and end < start:
            raise ImpossibleTimeError("period_end anterior a period_start")
        if (start is None) ^ (end is None):
            raise InsufficientTemporalContextError("intervalo exige period_start e period_end")
        return start, end

    def _precision(
        self,
        ir: IrTime,
        resolved_date: dt.date | None,
        time_of_day: dt.time | None,
        recurrence: Recurrence | None,
        day_period: DayPeriod | None,
    ) -> TimePrecision:
        if ir.precision is not None:
            return ir.precision
        if recurrence is not None and resolved_date is None and time_of_day is None:
            return TimePrecision.RECURRING
        if ir.period_start is not None:
            return TimePrecision.PERIOD
        if time_of_day is not None or ir.instant is not None:
            return TimePrecision.MINUTE
        if day_period is not None:
            return TimePrecision.DAY_PERIOD
        if resolved_date is not None:
            return TimePrecision.DAY
        raise InsufficientTemporalContextError("não foi possível determinar precisão")

    def _reject_conflicts(
        self,
        ir: IrTime,
        resolved_date: dt.date | None,
        instant: dt.datetime | None,
        zone: ZoneInfo,
    ) -> None:
        if ir.date is not None and resolved_date is not None and ir.date != resolved_date:
            raise TemporalConflictError(
                f"date absoluta {ir.date} incompatível com expressão ({resolved_date})"
            )
        if instant is not None and resolved_date is not None:
            local = instant.astimezone(zone)
            if local.date() != resolved_date:
                raise TemporalConflictError(
                    f"instant {local.date()} incompatível com date {resolved_date}"
                )
        if ir.weekday is not None and resolved_date is not None:
            if resolved_date.weekday() != ir.weekday:
                raise TemporalConflictError(
                    f"{resolved_date} não cai no weekday {ir.weekday}"
                )

    def _rule(self, ir: IrTime, ctx: TemporalContext) -> str:
        if ir.relative_day is not None:
            return f"relative.{ir.relative_day}"
        if ir.weekday is not None:
            policy = ir.weekday_policy or WeekdayPolicy.FROM_EVENT_STATUS
            if policy is WeekdayPolicy.FROM_EVENT_STATUS and ctx.event_status:
                return f"weekday.from_event_status.{ctx.event_status}"
            return f"weekday.{policy}"
        if ir.recurrence is not None and ir.date is None and ir.instant is None:
            return "recurrence.monthly_by_monthday"
        if ir.period_start is not None:
            return "period.explicit"
        if ir.instant is not None or ir.time_of_day is not None:
            return "absolute.datetime"
        return "absolute.date"

    @staticmethod
    def _default_confidence(precision: TimePrecision) -> Confidence:
        if precision is TimePrecision.APPROX_DAY:
            return Confidence(score=0.6, qualifier=Qualifier.APPROXIMATELY)
        if precision is TimePrecision.DAY_PERIOD:
            return Confidence(score=0.85)
        return Confidence(score=1.0)


def _as_aware(value: dt.datetime, zone: ZoneInfo) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def _shift_weekday(base: dt.date, weekday: int, policy: WeekdayPolicy) -> dt.date:
    if policy is WeekdayPolicy.NEXT:
        delta = (weekday - base.weekday()) % 7
        return base + dt.timedelta(days=delta)
    if policy is WeekdayPolicy.NEXT_STRICT:
        delta = (weekday - base.weekday()) % 7
        if delta == 0:
            delta = 7
        return base + dt.timedelta(days=delta)
    if policy is WeekdayPolicy.PREVIOUS:
        delta = (base.weekday() - weekday) % 7
        return base - dt.timedelta(days=delta)
    if policy is WeekdayPolicy.PREVIOUS_STRICT:
        delta = (base.weekday() - weekday) % 7
        if delta == 0:
            delta = 7
        return base - dt.timedelta(days=delta)
    raise ImpossibleTimeError(f"política de weekday não deslocável: {policy}")
