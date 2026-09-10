"""Correction semantic target resolution — deterministic, no insertion-order authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pke.domain.attributes import EntityAttribute
from pke.domain.corrections import (
    AssertionEffectiveness,
    KnowledgePrimitiveKind,
    KnowledgeReference,
)
from pke.domain.events import Event
from pke.domain.measurements import Measurement
from pke.domain.relations import Relation
from pke.domain.states import State
from pke.persist.contracts import UnitOfWork
from pke.query.effectiveness import AssertionEffectivenessResolver


class CorrectionTargetStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class CorrectionTargetDescription:
    """Semantic target description from SemanticProposal / IR — not a DB id authority."""

    kind: KnowledgePrimitiveKind | None = None
    entity_text: str | None = None
    object_text: str | None = None
    dimension_key: str | None = None
    value_text: str | None = None
    numeric_value: str | None = None
    year: int | None = None
    relation_concept_key: str | None = None
    state_value_key: str | None = None
    action_key: str | None = None
    explicit_assertion_id: str | None = None
    """Only trusted after membership+ownership+effectiveness validation."""
    conversation_assertion_id: str | None = None
    """Explicit conversation-bound assertion id supplied by application context — not DB order."""


@dataclass(frozen=True)
class CorrectionTargetResolution:
    status: CorrectionTargetStatus
    reference: KnowledgeReference | None = None
    candidates: tuple[KnowledgeReference, ...] = ()
    reason: str | None = None


@dataclass
class _Candidate:
    kind: KnowledgePrimitiveKind
    assertion_id: str
    entity_ids: set[str] = field(default_factory=set)
    entity_names: set[str] = field(default_factory=set)
    dimension_key: str | None = None
    value_text: str | None = None
    numeric_value: str | None = None
    year: int | None = None
    relation_key: str | None = None
    state_value_key: str | None = None
    action_id: str | None = None
    object_names: set[str] = field(default_factory=set)
    object_ids: set[str] = field(default_factory=set)
    temporal_year: int | None = None


class CorrectionTargetResolver:
    """Maps semantic target description → RESOLVED / AMBIGUOUS / UNRESOLVED.

    Never uses created_at, insertion-order identifiers, or last-event compatibility as authority.
    Highest match score alone cannot resolve ambiguity.
    """

    def resolve(
        self,
        *,
        user_id: str,
        description: CorrectionTargetDescription,
        uow: UnitOfWork,
        corrections: list[Any] | None = None,
        controlled_candidate_ids: frozenset[str] | None = None,
    ) -> CorrectionTargetResolution:
        if description.kind is None and description.explicit_assertion_id is None:
            return CorrectionTargetResolution(
                status=CorrectionTargetStatus.UNRESOLVED,
                reason="target_kind_missing",
            )

        # Explicit / conversation-bound id — still validated
        direct_id = description.explicit_assertion_id or description.conversation_assertion_id
        if direct_id is not None:
            if (
                description.explicit_assertion_id is not None
                and controlled_candidate_ids is not None
                and description.explicit_assertion_id not in controlled_candidate_ids
            ):
                return CorrectionTargetResolution(
                    status=CorrectionTargetStatus.UNRESOLVED,
                    reason="llm_invented_assertion_id_rejected",
                )
            kind = description.kind
            if kind is None:
                return CorrectionTargetResolution(
                    status=CorrectionTargetStatus.UNRESOLVED,
                    reason="explicit_id_requires_kind",
                )
            return self._resolve_direct(user_id, kind, direct_id, uow, corrections)

        if description.kind is None:
            return CorrectionTargetResolution(
                status=CorrectionTargetStatus.UNRESOLVED,
                reason="target_kind_missing",
            )

        candidates = self._collect_candidates(user_id, description.kind, uow)
        matched = [c for c in candidates if self._matches(c, description, uow, user_id)]
        # Effectiveness filter — only EFFECTIVE may be selected
        eff = AssertionEffectivenessResolver.from_corrections(
            corrections if corrections is not None else uow.corrections.for_user(user_id)
        )
        eligible: list[_Candidate] = []
        refs: list[KnowledgeReference] = []
        for c in matched:
            ref = KnowledgeReference(
                kind=c.kind, assertion_id=c.assertion_id, user_id=user_id
            )
            if eff.resolve(ref) is AssertionEffectiveness.EFFECTIVE:
                eligible.append(c)
                refs.append(ref)

        if not eligible:
            return CorrectionTargetResolution(
                status=CorrectionTargetStatus.UNRESOLVED,
                candidates=tuple(refs),
                reason="no_effective_semantic_match",
            )
        if len(eligible) > 1:
            return CorrectionTargetResolution(
                status=CorrectionTargetStatus.AMBIGUOUS,
                candidates=tuple(refs),
                reason="multiple_plausible_targets",
            )
        only = eligible[0]
        return CorrectionTargetResolution(
            status=CorrectionTargetStatus.RESOLVED,
            reference=KnowledgeReference(
                kind=only.kind, assertion_id=only.assertion_id, user_id=user_id
            ),
            candidates=tuple(refs),
            reason="unique_effective_match",
        )

    def _resolve_direct(
        self,
        user_id: str,
        kind: KnowledgePrimitiveKind,
        assertion_id: str,
        uow: UnitOfWork,
        corrections: list[Any] | None,
    ) -> CorrectionTargetResolution:
        from pke.application.knowledge_reference import (
            KnowledgeReferenceError,
            KnowledgeReferenceResolver,
        )

        try:
            ref = KnowledgeReferenceResolver(uow).resolve(user_id, kind, assertion_id)
        except KnowledgeReferenceError:
            return CorrectionTargetResolution(
                status=CorrectionTargetStatus.UNRESOLVED,
                reason="explicit_reference_invalid",
            )
        eff = AssertionEffectivenessResolver.from_corrections(
            corrections if corrections is not None else uow.corrections.for_user(user_id)
        )
        if eff.resolve(ref) is not AssertionEffectiveness.EFFECTIVE:
            return CorrectionTargetResolution(
                status=CorrectionTargetStatus.UNRESOLVED,
                reference=ref,
                reason="target_not_effective",
            )
        return CorrectionTargetResolution(
            status=CorrectionTargetStatus.RESOLVED,
            reference=ref,
            candidates=(ref,),
            reason="explicit_validated_reference",
        )

    def _collect_candidates(
        self, user_id: str, kind: KnowledgePrimitiveKind, uow: UnitOfWork
    ) -> list[_Candidate]:
        entities = {e.id: e for e in uow.entities.all_for_user(user_id)}
        out: list[_Candidate] = []
        if kind is KnowledgePrimitiveKind.ATTRIBUTE:
            for ent in entities.values():
                for a in uow.attributes.for_entity(user_id, ent.id):
                    out.append(self._from_attribute(a, entities))
        elif kind is KnowledgePrimitiveKind.MEASUREMENT:
            for m in uow.measurements.for_user(user_id):
                out.append(self._from_measurement(m, entities))
        elif kind is KnowledgePrimitiveKind.RELATION:
            for ent in entities.values():
                for r in uow.relations.for_entity(user_id, ent.id):
                    out.append(self._from_relation(r, entities))
        elif kind is KnowledgePrimitiveKind.STATE:
            for ent in entities.values():
                for s in uow.states.for_entity(user_id, ent.id):
                    out.append(self._from_state(s, entities))
        elif kind is KnowledgePrimitiveKind.EVENT:
            for ev in self._events_for_user(uow, user_id):
                out.append(self._from_event(ev, entities))
        return out

    def _events_for_user(self, uow: UnitOfWork, user_id: str) -> list[Event]:
        session = getattr(uow, "session", None)
        if session is None:
            return []
        from sqlalchemy import select

        from pke.persist.sqlite.mappers import event_from_row
        from pke.persist.sqlite.tables import EventRow

        rows = session.scalars(select(EventRow).where(EventRow.user_id == user_id)).all()
        return [event_from_row(r) for r in rows]

    def _from_attribute(self, a: EntityAttribute, entities: dict) -> _Candidate:
        ent = entities.get(a.entity_id)
        names = {ent.canonical_name.lower()} if ent else set()
        return _Candidate(
            kind=KnowledgePrimitiveKind.ATTRIBUTE,
            assertion_id=a.id,
            entity_ids={a.entity_id},
            entity_names=names,
            dimension_key=a.dimension_key,
            value_text=(a.text_value or "").lower() or None,
            numeric_value=str(a.numeric_value) if a.numeric_value is not None else None,
            year=a.year_value,
        )

    def _from_measurement(self, m: Measurement, entities: dict) -> _Candidate:
        ent = entities.get(m.entity_id)
        names = {ent.canonical_name.lower()} if ent else set()
        return _Candidate(
            kind=KnowledgePrimitiveKind.MEASUREMENT,
            assertion_id=m.id,
            entity_ids={m.entity_id},
            entity_names=names,
            dimension_key=m.dimension_key,
            numeric_value=format(m.numeric_value, "f"),
            temporal_year=m.temporal.calendar.date.year if m.temporal.calendar and m.temporal.calendar.date else None,
        )

    def _from_relation(self, r: Relation, entities: dict) -> _Candidate:
        left = entities.get(r.from_id)
        right = entities.get(r.to_id)
        return _Candidate(
            kind=KnowledgePrimitiveKind.RELATION,
            assertion_id=r.id,
            entity_ids={r.from_id, r.to_id},
            entity_names={x.canonical_name.lower() for x in (left, right) if x},
            relation_key=r.key,
            object_ids={r.to_id},
            object_names={right.canonical_name.lower()} if right else set(),
        )

    def _from_state(self, s: State, entities: dict) -> _Candidate:
        ent = entities.get(s.entity_id)
        return _Candidate(
            kind=KnowledgePrimitiveKind.STATE,
            assertion_id=s.id,
            entity_ids={s.entity_id},
            entity_names={ent.canonical_name.lower()} if ent else set(),
            dimension_key=s.dimension_key,
            state_value_key=s.value_key,
        )

    def _from_event(self, e: Event, entities: dict) -> _Candidate:
        eids = e.participant_entity_ids()
        names = {
            entities[i].canonical_name.lower()
            for i in eids
            if i in entities
        }
        year = None
        if e.temporal.calendar and e.temporal.calendar.date:
            year = e.temporal.calendar.date.year
        elif e.temporal.partial_year:
            year = e.temporal.partial_year
        return _Candidate(
            kind=KnowledgePrimitiveKind.EVENT,
            assertion_id=e.id,
            entity_ids=set(eids),
            entity_names=names,
            action_id=e.action_id,
            temporal_year=year,
        )

    def _matches(
        self,
        c: _Candidate,
        d: CorrectionTargetDescription,
        uow: UnitOfWork,
        user_id: str,
    ) -> bool:
        if d.kind is not None and c.kind is not d.kind:
            return False
        if d.entity_text:
            needle = d.entity_text.strip().lower()
            if needle not in c.entity_names and not any(needle in n for n in c.entity_names):
                return False
        if d.object_text:
            needle = d.object_text.strip().lower()
            if needle not in c.object_names and not any(needle in n for n in c.object_names):
                return False
        if d.dimension_key and c.dimension_key != d.dimension_key:
            return False
        if d.value_text is not None and c.value_text is not None:
            if d.value_text.strip().lower() != c.value_text:
                return False
        if d.numeric_value is not None and c.numeric_value is not None:
            try:
                if float(d.numeric_value) != float(c.numeric_value):
                    return False
            except ValueError:
                if d.numeric_value != c.numeric_value:
                    return False
        if d.year is not None:
            if c.year is not None and c.year != d.year:
                return False
            if c.temporal_year is not None and c.temporal_year != d.year:
                return False
            if c.year is None and c.temporal_year is None:
                return False
        if d.relation_concept_key and c.relation_key != d.relation_concept_key:
            return False
        if d.state_value_key and c.state_value_key != d.state_value_key:
            return False
        if d.action_key:
            from pke.ontology.seeds import core_concept_id

            try:
                wanted = core_concept_id(d.action_key) if not d.action_key.startswith("c_") else d.action_key
            except Exception:  # noqa: BLE001
                wanted = d.action_key
            if c.action_id and c.action_id != wanted and d.action_key not in (c.action_id or ""):
                # also allow key suffix match via ontology lookup later — require action if provided
                if c.action_id != d.action_key:
                    from pke.ontology import OntologyRegistry

                    reg = OntologyRegistry.with_core_seeds()
                    concept = reg.get_by_id(c.action_id) if c.action_id else None
                    if concept is None or concept.key != d.action_key:
                        return False
        return True
