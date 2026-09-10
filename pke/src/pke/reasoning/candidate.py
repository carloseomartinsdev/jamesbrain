"""Candidato de conhecimento pós-resolução — ainda não persistido."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import SourceKind, TimeValue
from pke.interpretation.models import EntityMention, IngestIR
from pke.resolution.entities import EntityResolution


class MentionBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention: EntityMention
    resolution: EntityResolution


class KnowledgeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    ir: IngestIR
    resolved_temporal: TemporalKnowledge | None = None
    resolved_due: TimeValue | None = None
    bindings: list[MentionBinding] = Field(default_factory=list)
    source_kind: SourceKind = SourceKind.USER_STATEMENT

    @property
    def resolved_time(self) -> TimeValue | None:
        if self.resolved_temporal is None or not self.resolved_temporal.has_calendar_anchor():
            return None
        return self.resolved_temporal.calendar

    def has_persistable_temporal(self) -> bool:
        return self.resolved_temporal is not None and self.resolved_temporal.is_persistable()
