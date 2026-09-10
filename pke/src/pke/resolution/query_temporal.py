"""Resolve períodos de consulta → TimeRange [start, end). Não parseia texto."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict

from pke.domain.value_objects import UserContext
from pke.interpretation.models import IrQueryTime, RelativePeriod
from pke.resolution.errors import (
    InsufficientTemporalContextError,
    InvalidTimezoneError,
    TemporalConflictError,
)


class WeekStart(StrEnum):
    """Início da semana civil. Default pt-BR: segunda."""

    MONDAY = "monday"


class AbsoluteRange(BaseModel):
    """Intervalo civil absoluto [start, end). Sem QueryEngine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: dt.datetime
    end: dt.datetime


class QueryTemporalContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user: UserContext
    reference_at: dt.datetime | None = None
    week_start: WeekStart = WeekStart.MONDAY


class QueryTemporalResolver:
    def resolve(self, ir: IrQueryTime | None, ctx: QueryTemporalContext) -> AbsoluteRange | None:
        if ir is None:
            return None
        zone = self._zone(ctx.user.timezone)
        reference = self._reference(ctx, zone)
        explicit = self._explicit(ir, zone)
        relative = self._relative(ir, reference, zone, ctx.week_start)
        if explicit is not None and relative is not None:
            raise TemporalConflictError("período relativo e intervalo explícito juntos")
        chosen = explicit or relative
        if chosen is None:
            raise InsufficientTemporalContextError("IrQueryTime sem período estruturado")
        if chosen.start >= chosen.end:
            raise TemporalConflictError("intervalo [start, end) exige start < end")
        return chosen

    def _zone(self, name: str) -> ZoneInfo:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, KeyError) as exc:
            raise InvalidTimezoneError(name) from exc

    def _reference(self, ctx: QueryTemporalContext, zone: ZoneInfo) -> dt.datetime:
        raw = ctx.reference_at or ctx.user.now
        if raw is None:
            raise InsufficientTemporalContextError("período relativo exige relógio injetado")
        if raw.tzinfo is None:
            return raw.replace(tzinfo=zone)
        return raw.astimezone(zone)

    def _explicit(self, ir: IrQueryTime, zone: ZoneInfo) -> AbsoluteRange | None:
        if ir.start is not None or ir.end is not None:
            if ir.start is None or ir.end is None:
                raise InsufficientTemporalContextError("intervalo explícito exige start e end")
            start = ir.start if ir.start.tzinfo else ir.start.replace(tzinfo=zone)
            end = ir.end if ir.end.tzinfo else ir.end.replace(tzinfo=zone)
            return AbsoluteRange(start=start.astimezone(zone), end=end.astimezone(zone))
        if ir.date_from is not None or ir.date_to is not None:
            if ir.date_from is None or ir.date_to is None:
                raise InsufficientTemporalContextError("date range exige date_from e date_to")
            # date_from inclusivo; date_to = meia-noite exclusiva. Dia de date_to não entra.
            start = dt.datetime.combine(ir.date_from, dt.time.min, tzinfo=zone)
            end = dt.datetime.combine(ir.date_to, dt.time.min, tzinfo=zone)
            return AbsoluteRange(start=start, end=end)
        return None

    def _relative(
        self,
        ir: IrQueryTime,
        reference: dt.datetime,
        zone: ZoneInfo,
        week_start: WeekStart,
    ) -> AbsoluteRange | None:
        if ir.relative_period is None:
            return None
        day = reference.date()
        period = ir.relative_period
        if period is RelativePeriod.THIS_MONTH:
            start_day = day.replace(day=1)
            end_day = _next_month(start_day)
        elif period is RelativePeriod.LAST_MONTH:
            end_day = day.replace(day=1)
            start_day = _previous_month(end_day)
        elif period is RelativePeriod.THIS_WEEK:
            start_day = _week_start(day, week_start)
            end_day = start_day + dt.timedelta(days=7)
        elif period is RelativePeriod.LAST_WEEK:
            this = _week_start(day, week_start)
            start_day = this - dt.timedelta(days=7)
            end_day = this
        elif period is RelativePeriod.TODAY:
            start_day = day
            end_day = day + dt.timedelta(days=1)
        elif period is RelativePeriod.YESTERDAY:
            start_day = day - dt.timedelta(days=1)
            end_day = day
        elif period is RelativePeriod.NOW:
            # Exact reference instant: [reference, reference + 1µs).
            # NOT the calendar day. No freshness / TTL window.
            return AbsoluteRange(
                start=reference,
                end=reference + dt.timedelta(microseconds=1),
            )
        else:
            raise InsufficientTemporalContextError(f"período não suportado: {period}")
        return AbsoluteRange(
            start=dt.datetime.combine(start_day, dt.time.min, tzinfo=zone),
            end=dt.datetime.combine(end_day, dt.time.min, tzinfo=zone),
        )


def _week_start(day: dt.date, week_start: WeekStart) -> dt.date:
    if week_start is WeekStart.MONDAY:
        return day - dt.timedelta(days=day.weekday())
    raise InsufficientTemporalContextError(f"week_start não suportado: {week_start}")


def _next_month(day: dt.date) -> dt.date:
    if day.month == 12:
        return dt.date(day.year + 1, 1, 1)
    return dt.date(day.year, day.month + 1, 1)


def _previous_month(first_of_month: dt.date) -> dt.date:
    if first_of_month.month == 1:
        return dt.date(first_of_month.year - 1, 12, 1)
    return dt.date(first_of_month.year, first_of_month.month - 1, 1)
