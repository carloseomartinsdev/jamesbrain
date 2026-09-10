"""TemporalKnowledge — modelo experimental de tempo parcial."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RelationToNow(StrEnum):
    PAST = "past"
    PRESENT = "present"
    FUTURE = "future"
    HABITUAL = "habitual"
    UNSPECIFIED = "unspecified"


class TemporalAspect(StrEnum):
    COMPLETED = "completed"
    ONGOING = "ongoing"
    PROSPECTIVE = "prospective"
    HABITUAL = "habitual"
    UNSPECIFIED = "unspecified"


class TemporalUnknownReason(StrEnum):
    NOT_PROVIDED = "not_provided"
    FORGOTTEN = "forgotten"
    UNRESOLVED = "unresolved"
    INFERRED = "inferred"
    MISSING = "missing"


class TemporalGranularity(StrEnum):
    INSTANT = "instant"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"
    INTERVAL = "interval"
    RECURRING = "recurring"
    UNSPECIFIED = "unspecified"


class TemporalKnowledge(BaseModel):
    """Tempo parcial — evidência gramatical sem data absoluta obrigatória."""

    model_config = ConfigDict(extra="forbid")

    absolute_time: str | None = None
    relative_time: str | None = None
    relation_to_now: RelationToNow = RelationToNow.UNSPECIFIED
    aspect: TemporalAspect = TemporalAspect.UNSPECIFIED
    recurrence: str | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    granularity: TemporalGranularity = TemporalGranularity.UNSPECIFIED
    tense_evidence: str | None = None
    uncertainty: float = Field(default=0.0, ge=0.0, le=1.0)
    unknown_reason: TemporalUnknownReason | None = None
    source: str = "explicit"

    @property
    def has_absolute_calendar_time(self) -> bool:
        return self.absolute_time is not None

    def is_distinct_from(self, other: TemporalKnowledge) -> bool:
        """Esquecido ≠ não fornecido."""
        if self.unknown_reason != other.unknown_reason:
            return True
        return (
            self.relation_to_now != other.relation_to_now
            or self.aspect != other.aspect
            or self.has_absolute_calendar_time != other.has_absolute_calendar_time
        )
