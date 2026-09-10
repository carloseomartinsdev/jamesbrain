"""State — condição semanticamente significativa de uma entidade."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pke.domain.ontology import CONCEPT_KEY_PATTERN
from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import Confidence, Source


class State(BaseModel):
    """Valor de estado dentro de uma dimensão — distinto de Event."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    entity_id: str
    dimension_id: str
    dimension_key: str = Field(pattern=CONCEPT_KEY_PATTERN)
    value_concept_id: str
    value_key: str = Field(pattern=CONCEPT_KEY_PATTERN)
    payload: Any | None = None
    """Dados associados não-semânticos (ex.: quantidade + unidade)."""
    temporal: TemporalKnowledge
    observed_at: dt.datetime
    """Quando a asserção foi conhecida/registrada — não implica início causal."""
    valid_from: dt.datetime | None = None
    valid_to: dt.datetime | None = None
    supersedes_id: str | None = None
    is_current: bool = True
    caused_by_event_id: str | None = None
    """Nunca preenchido por inferência automática."""
    source: Source | None = None
    raw_input_id: str | None = None
    confidence: Confidence | None = None
    created_at: dt.datetime | None = None
