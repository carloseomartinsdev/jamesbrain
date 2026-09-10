"""EntityAttribute — descriptive property assertion (first-class Attribute primitive)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import Confidence, Source


class AttributeValueKind(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    YEAR = "year"
    DATE = "date"
    CONCEPT = "concept"


class EntityAttribute(BaseModel):
    """Descriptive property of an entity in a named dimension — not State/Fact."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    entity_id: str
    dimension_key: str = Field(min_length=1)
    dimension_concept_id: str | None = None
    value_kind: AttributeValueKind
    concept_value_id: str | None = None
    text_value: str | None = None
    numeric_value: Decimal | None = None
    unit: str | None = None
    date_value: dt.date | None = None
    year_value: int | None = None
    temporal: TemporalKnowledge
    observed_at: dt.datetime
    valid_from: dt.datetime | None = None
    valid_to: dt.datetime | None = None
    is_current: bool = True
    supersedes_id: str | None = None
    source: Source | None = None
    raw_input_id: str | None = None
    confidence: Confidence | None = None
    created_at: dt.datetime | None = None

    @model_validator(mode="after")
    def _exactly_one_value(self) -> EntityAttribute:
        kind = self.value_kind
        slots = {
            "concept": self.concept_value_id is not None,
            "text": self.text_value is not None,
            "number": self.numeric_value is not None,
            "date": self.date_value is not None,
            "year": self.year_value is not None,
        }
        if kind is AttributeValueKind.TEXT:
            if not slots["text"] or any(slots[k] for k in ("concept", "number", "date", "year")):
                raise ValueError("value_kind=text requires only text_value")
        elif kind is AttributeValueKind.NUMBER:
            if not slots["number"] or any(slots[k] for k in ("concept", "text", "date", "year")):
                raise ValueError("value_kind=number requires only numeric_value (+ optional unit)")
        elif kind is AttributeValueKind.YEAR:
            if not slots["year"] or any(slots[k] for k in ("concept", "text", "number", "date")):
                raise ValueError("value_kind=year requires only year_value")
            if self.year_value is not None and not (1000 <= self.year_value <= 9999):
                raise ValueError("year_value out of range")
        elif kind is AttributeValueKind.DATE:
            if not slots["date"] or any(slots[k] for k in ("concept", "text", "number", "year")):
                raise ValueError("value_kind=date requires only date_value")
        elif kind is AttributeValueKind.CONCEPT:
            if not slots["concept"] or any(slots[k] for k in ("text", "number", "date", "year")):
                raise ValueError("value_kind=concept requires only concept_value_id")
        if kind is not AttributeValueKind.NUMBER and self.unit is not None:
            raise ValueError("unit only allowed with value_kind=number")
        return self
