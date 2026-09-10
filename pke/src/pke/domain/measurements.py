"""Measurement — observed quantitative value (first-class knowledge primitive)."""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import Confidence, Source

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_FORBIDDEN_DIMENSION_KEYS = frozenset(
    {"percent", "%", "kg", "liters", "l", "value", "reading", "r$", "$", "unit", "km", "count"}
)


class Measurement(BaseModel):
    """Quantitative observation of a measurable dimension — not Attribute/State/Event."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    entity_id: str
    context_entity_id: str | None = None
    dimension_key: str = Field(min_length=1)
    dimension_concept_id: str | None = None
    numeric_value: Decimal
    unit: str | None = None
    currency_code: str | None = None
    temporal: TemporalKnowledge
    observed_at: dt.datetime | None = None
    source: Source | None = None
    raw_input_id: str | None = None
    confidence: Confidence | None = None
    created_at: dt.datetime | None = None

    @model_validator(mode="after")
    def _invariants(self) -> Measurement:
        dim = self.dimension_key.strip()
        if not dim or dim.lower() in _FORBIDDEN_DIMENSION_KEYS:
            raise ValueError("dimension_key must identify measurable meaning, not a unit")
        if self.unit is not None and self.currency_code is not None:
            raise ValueError("unit and currency_code must not coexist")
        if self.currency_code is not None and not _CURRENCY_RE.match(self.currency_code):
            raise ValueError("currency_code must be 3 uppercase letters when set")
        return self
