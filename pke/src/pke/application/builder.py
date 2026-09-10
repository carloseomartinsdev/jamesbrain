"""IR resolvida + bindings → KnowledgeCandidate. Sem validar nem persistir."""

from __future__ import annotations

from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import SourceKind, TimeValue
from pke.interpretation.models import EntityMention, IngestIR
from pke.reasoning.candidate import KnowledgeCandidate, MentionBinding


class KnowledgeCandidateBuilder:
    def build(
        self,
        *,
        user_id: str,
        ir: IngestIR,
        bindings: list[MentionBinding],
        resolved_temporal: TemporalKnowledge | None = None,
        resolved_due: TimeValue | None = None,
        source_kind: SourceKind = SourceKind.USER_STATEMENT,
    ) -> KnowledgeCandidate:
        return KnowledgeCandidate(
            user_id=user_id,
            ir=ir,
            resolved_temporal=resolved_temporal,
            resolved_due=resolved_due,
            bindings=bindings,
            source_kind=source_kind,
        )

    @staticmethod
    def collect_mentions(ir: IngestIR) -> list[EntityMention]:
        seen: list[EntityMention] = []
        keys: set[tuple[str, str | None]] = set()
        extra = ir.event.participants if ir.event else []
        relation_mentions: list[EntityMention] = []
        if ir.relation is not None:
            relation_mentions = [ir.relation.subject, ir.relation.object]
        attribute_mentions: list[EntityMention] = []
        if ir.attribute is not None:
            attribute_mentions = [ir.attribute.subject]
            attribute_mentions.extend(a.subject for a in ir.additional_attributes)
        measurement_mentions: list[EntityMention] = []
        if ir.measurement is not None:
            measurement_mentions = [ir.measurement.subject]
            if ir.measurement.context is not None:
                measurement_mentions.append(ir.measurement.context)
        for mention in [
            *ir.entities_mentioned,
            *extra,
            *relation_mentions,
            *attribute_mentions,
            *measurement_mentions,
        ]:
            role = mention.role.key if mention.role else None
            key = (mention.text, role)
            if key in keys:
                continue
            keys.add(key)
            seen.append(mention)
        return seen
