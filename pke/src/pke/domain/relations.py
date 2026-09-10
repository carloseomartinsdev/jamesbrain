"""Relation — vínculo tipado entre entidades, distinto de State/Event/Attribute."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from pke.domain.ontology import CONCEPT_KEY_PATTERN
from pke.domain.relation_lifecycle import relation_calendar_start
from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import Confidence, Source


class RelationTerminationEvidence(BaseModel):
    """Evidência de que a relação deixou de valer — distinta da asserção original."""

    model_config = ConfigDict(extra="forbid")

    temporal: TemporalKnowledge
    observed_at: dt.datetime
    source: Source
    raw_input_id: str
    confidence: Confidence | None = None
    caused_by_event_id: str | None = None


class Relation(BaseModel):
    """Instância temporal de um conceito relacional subject → object."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    from_id: str
    """Sujeito da relação (subject_entity_id)."""
    to_id: str
    """Objeto da relação (object_entity_id)."""
    concept_id: str
    key: str = Field(pattern=CONCEPT_KEY_PATTERN)
    temporal: TemporalKnowledge
    observed_at: dt.datetime
    """Quando a asserção foi conhecida — não implica início causal."""
    valid_from: dt.datetime | None = None
    valid_to: dt.datetime | None = None
    is_current: bool = True
    supersedes_id: str | None = None
    caused_by_event_id: str | None = None
    source: Source | None = None
    raw_input_id: str | None = None
    confidence: Confidence | None = None
    created_at: dt.datetime | None = None
    termination_temporal: TemporalKnowledge | None = None
    termination_observed_at: dt.datetime | None = None
    termination_raw_input_id: str | None = None
    termination_source: Source | None = None
    termination_confidence: Confidence | None = None

    @property
    def termination_known(self) -> bool:
        return self.termination_observed_at is not None

    def apply_termination(self, evidence: RelationTerminationEvidence) -> Relation:
        from pke.domain.relation_lifecycle import relation_calendar_endpoint

        if evidence.observed_at.tzinfo is None:
            raise ValueError("termination observed_at exige timezone")
        return self.model_copy(
            update={
                "termination_temporal": evidence.temporal,
                "termination_observed_at": evidence.observed_at,
                "termination_raw_input_id": evidence.raw_input_id,
                "termination_source": evidence.source,
                "termination_confidence": evidence.confidence or Confidence(score=1.0),
                "valid_to": relation_calendar_endpoint(evidence.temporal),
                "is_current": False,
                "caused_by_event_id": evidence.caused_by_event_id or self.caused_by_event_id,
            }
        )

    @property
    def type_id(self) -> str:
        """Alias legado — concept_id."""
        return self.concept_id

    @property
    def subject_entity_id(self) -> str:
        return self.from_id

    @property
    def object_entity_id(self) -> str:
        return self.to_id

    def identity_key(self) -> tuple[str, str, str]:
        return (self.from_id, self.concept_id, self.to_id)
