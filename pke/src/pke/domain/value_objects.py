"""Value objects e enums de sistema (não são ontologia de tipos)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EpistemicStatus(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"
    CONTRADICTED = "contradicted"


class SourceKind(StrEnum):
    USER_STATEMENT = "user_statement"
    DOCUMENT = "document"
    INFERENCE = "inference"
    SYSTEM = "system"
    CORRECTION = "correction"


class Qualifier(StrEnum):
    EXACT = "exact"
    APPROXIMATELY = "approximately"
    UNKNOWN = "unknown"


class TimePrecision(StrEnum):
    """TimeValue / v9 persistence precision — NOT canonical calendar granularity.

    I11.16.1: Calendar resolution authority is TemporalKnowledge.calendar_granularity().
    PARTIAL is LEGACY/COMPATIBILITY ONLY — do not emit as new canonical semantics.
    """

    DAY = "day"
    MINUTE = "minute"
    APPROX_DAY = "approx_day"
    RECURRING = "recurring"
    PERIOD = "period"
    DAY_PERIOD = "day_period"
    PARTIAL = "partial"
    """Deprecated — legacy v9 marker for absent calendar columns. Prefer TemporalKind.PARTIAL / calendar_granularity()=None."""


class RelativeDay(StrEnum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    TOMORROW = "tomorrow"


class WeekdayPolicy(StrEnum):
    """Política explícita — o resolver não escolhe sozinho entre futuro e passado."""

    NEXT = "next"
    PREVIOUS = "previous"
    NEXT_STRICT = "next_strict"
    PREVIOUS_STRICT = "previous_strict"
    FROM_EVENT_STATUS = "from_event_status"


class DayPeriod(StrEnum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class EventStatus(StrEnum):
    """Ciclo de vida do evento — fechado de propósito (não é tipo ontológico)."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    PENDING = "pending"


class AnchorKind(StrEnum):
    ENTITY = "entity"
    EVENT = "event"
    RELATION = "relation"


class UserContext(BaseModel):
    """Contexto operacional do usuário. Locale/timezone vivem aqui, não no domínio temporal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str
    locale: str = "pt-BR"
    timezone: str = "America/Fortaleza"
    now: dt.datetime | None = None


class Confidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: float = Field(ge=0.0, le=1.0)
    qualifier: Qualifier = Qualifier.EXACT


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str
    kind: SourceKind
    raw_input_id: str | None = None
    rule_id: str | None = None
    id: str | None = None


class Recurrence(BaseModel):
    """Recorrência extensível. Onda 1 usa freq=monthly + by_monthday; o resto é reserva."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    freq: str
    interval: int = Field(default=1, ge=1)
    by_monthday: int | None = Field(default=None, ge=1, le=31)
    by_weekday: int | None = Field(default=None, ge=0, le=6)
    until: dt.date | None = None
    count: int | None = Field(default=None, ge=1)
    rrule: str | None = None


class TimeValue(BaseModel):
    """Tempo como valor: texto original nunca some após a resolução absoluta."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    original_text: str
    interpretation: str | None = None
    instant: dt.datetime | None = None
    date: dt.date | None = None
    time_of_day: dt.time | None = None
    period_start: dt.datetime | None = None
    period_end: dt.datetime | None = None
    timezone: str | None = None
    recurrence: Recurrence | None = None
    precision: TimePrecision
    confidence: Confidence | None = None
    reference_at: dt.datetime | None = None
    reference_timezone: str | None = None
    day_period: DayPeriod | None = None
    resolution_rule: str | None = None


class Money(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    amount: Decimal
    currency: str = "BRL"


class RawInput(BaseModel):
    """Mensagem original imutável — auditoria, reprocessamento, correção."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    text: str
    created_at: dt.datetime
