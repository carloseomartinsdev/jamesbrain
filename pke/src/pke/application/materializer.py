"""Candidato aprovado → objetos persistíveis. Não interpreta nem completa."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from pke.application.errors import MaterializationDenied
from pke.application.results import MaterializationResult
from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.domain.entities import Entity
from pke.domain.event_participants import EventParticipant
from pke.domain.events import Event
from pke.domain.facts import Fact
from pke.domain.ids import new_ulid
from pke.domain.measurements import Measurement
from pke.domain.ontology import ConceptKind, ConceptRef
from pke.domain.relation_lifecycle import relation_calendar_start
from pke.domain.relations import Relation, RelationTerminationEvidence
from pke.domain.states import State
from pke.domain.temporal_knowledge import (
    OccurrenceStatus,
    TemporalKnowledge,
    TemporalKind,
    TemporalUnknownReason,
)
from pke.domain.value_objects import (
    AnchorKind,
    Confidence,
    EventStatus,
    Money,
    RawInput,
    Recurrence,
    Source,
    SourceKind,
    TimePrecision,
    TimeValue,
)
from pke.interpretation.models import IngestIntent, IrFact, RelationAssertionMode
from pke.ontology.relation_metadata import canonical_endpoints
from pke.ontology.registry import OntologyRegistry
from pke.ontology.seeds import core_concept_id
from pke.persist.contracts import UnitOfWork
from pke.reasoning.assessment import KnowledgeAssessment
from pke.reasoning.candidate import KnowledgeCandidate, MentionBinding
from pke.resolution.entities import ResolutionStatus


class ApprovedKnowledge:
    """Conhecimento já resolvido e persistível. Única entrada do Materializer."""

    __slots__ = ("candidate", "assessment", "created_at")

    def __init__(
        self,
        candidate: KnowledgeCandidate,
        assessment: KnowledgeAssessment,
        created_at: dt.datetime,
        *,
        _certified: bool = False,
    ) -> None:
        if not _certified:
            raise MaterializationDenied("use ApprovedKnowledge.certify")
        self.candidate = candidate
        self.assessment = assessment
        self.created_at = created_at

    @classmethod
    def certify(
        cls,
        candidate: KnowledgeCandidate,
        assessment: KnowledgeAssessment,
        created_at: dt.datetime,
    ) -> ApprovedKnowledge:
        if not assessment.persistable:
            raise MaterializationDenied("assessment.persistable é False")
        if created_at.tzinfo is None:
            raise ValueError("created_at exige timezone")
        return cls(candidate, assessment, created_at, _certified=True)


ProgressHook = Callable[[str, MaterializationResult], None]


class KnowledgeMaterializer:
    def __init__(
        self,
        ontology: OntologyRegistry,
        *,
        on_progress: ProgressHook | None = None,
    ) -> None:
        self._ontology = ontology
        self._on_progress = on_progress

    def materialize(self, approved: ApprovedKnowledge, uow: UnitOfWork) -> MaterializationResult:
        if not isinstance(approved, ApprovedKnowledge):
            raise MaterializationDenied("materialize exige ApprovedKnowledge")
        candidate = approved.candidate
        at = approved.created_at.astimezone(dt.UTC)
        result = MaterializationResult()
        entity_ids = self._entities(candidate, uow, at, result)
        raw = RawInput(
            id=new_ulid(),
            user_id=candidate.user_id,
            text=candidate.ir.raw_input,
            created_at=at,
        )
        uow.raw_inputs.add(raw)
        result.raw_input_id = raw.id
        source_kind = (
            SourceKind.CORRECTION
            if candidate.ir.intent is IngestIntent.CORRECT
            else candidate.source_kind
        )
        source = Source(
            id=new_ulid(),
            user_id=candidate.user_id,
            kind=source_kind,
            raw_input_id=raw.id,
        )
        stored_source = uow.sources.add(source)
        assert stored_source.id is not None
        result.source_ids.append(stored_source.id)
        ir = candidate.ir
        if ir.correction is not None:
            self._correction(candidate, stored_source, entity_ids, uow, at, result)
            return result
        # COMMIT_VALID_INDEPENDENTLY: Event and Measurement may both persist.
        # Process without exclusive early-return between them.
        if ir.event is not None:
            self._event(candidate, stored_source, raw.id, entity_ids, uow, at, result)
        if ir.measurement is not None:
            self._measurement(candidate, stored_source, raw.id, entity_ids, uow, at, result)
        if ir.event is not None or ir.measurement is not None:
            return result
        if ir.obligation is not None:
            self._obligation(candidate, stored_source, raw.id, entity_ids, uow, at, result)
            return result
        if ir.state is not None:
            self._state(candidate, stored_source, raw.id, entity_ids, uow, at, result)
            return result
        if ir.attribute is not None:
            self._attribute(candidate, stored_source, raw.id, entity_ids, uow, at, result)
            for extra in ir.additional_attributes:
                self._attribute_record(
                    candidate,
                    stored_source,
                    raw.id,
                    entity_ids,
                    uow,
                    at,
                    result,
                    extra,
                )
            self._ensure_vehicle_ownership(
                candidate, stored_source, raw.id, entity_ids, uow, at, result
            )
            return result
        if ir.relation is not None:
            self._relation(candidate, stored_source, raw.id, entity_ids, uow, at, result)
            return result
        return result

    def _entities(
        self,
        candidate: KnowledgeCandidate,
        uow: UnitOfWork,
        at: dt.datetime,
        result: MaterializationResult,
    ) -> dict[str, str]:
        mapped: dict[str, str] = {}
        for binding in candidate.bindings:
            res = binding.resolution
            if res.status is ResolutionStatus.RESOLVED and res.entity_id:
                mapped[binding.mention.text] = res.entity_id
                if res.entity_id not in result.reused_entity_ids:
                    result.reused_entity_ids.append(res.entity_id)
                continue
            if res.status is ResolutionStatus.CREATE_CANDIDATE:
                type_id = res.create_type_id
                if type_id is None and binding.mention.type_hint is not None:
                    type_id = self._concept_id(binding.mention.type_hint)
                if type_id is None:
                    raise MaterializationDenied("create_candidate sem type_id")
                entity = Entity(
                    id=new_ulid(),
                    user_id=candidate.user_id,
                    type_id=type_id,
                    canonical_name=res.create_canonical_name or binding.mention.text,
                    aliases=list(binding.mention.suggested_aliases),
                    created_at=at,
                )
                uow.entities.add(entity)
                mapped[binding.mention.text] = entity.id
                result.created_entity_ids.append(entity.id)
        return mapped

    def _event(
        self,
        candidate: KnowledgeCandidate,
        source: Source,
        raw_id: str,
        entity_ids: dict[str, str],
        uow: UnitOfWork,
        at: dt.datetime,
        result: MaterializationResult,
    ) -> None:
        ir_event = candidate.ir.event
        assert ir_event is not None
        if candidate.resolved_temporal is None or not candidate.has_persistable_temporal():
            raise MaterializationDenied("evento sem tempo persistível")
        participants = self._participants(candidate.bindings, entity_ids, event_id=None)
        actor_id, subject_id = self._legacy_slots(participants)
        event_id = new_ulid()
        participants = [
            p.model_copy(update={"event_id": event_id}) for p in participants
        ]
        event = Event(
            id=event_id,
            user_id=candidate.user_id,
            type_id=self._concept_id(ir_event.type),
            action_id=self._concept_id(ir_event.action) if ir_event.action else None,
            actor_id=actor_id,
            subject_id=subject_id,
            participants=participants,
            temporal=candidate.resolved_temporal,
            status=ir_event.status,
            domain_ids=[self._concept_id(ref) for ref in candidate.ir.domains],
            raw_input_id=raw_id,
            created_at=at,
        )
        uow.events.add(event)
        result.event_ids.append(event.id)
        self._facts(candidate.user_id, event.id, ir_event.facts, source, uow, at, result)

    def _obligation(
        self,
        candidate: KnowledgeCandidate,
        source: Source,
        raw_id: str,
        entity_ids: dict[str, str],
        uow: UnitOfWork,
        at: dt.datetime,
        result: MaterializationResult,
    ) -> None:
        obl = candidate.ir.obligation
        assert obl is not None
        participants = self._participants(candidate.bindings, entity_ids, event_id=None)
        actor_id, subject_id = self._legacy_slots(participants)
        time = candidate.resolved_due or candidate.resolved_time or _recurrence_time(obl.cadence)
        temporal = (
            candidate.resolved_temporal
            if candidate.resolved_temporal is not None
            else TemporalKnowledge.from_calendar(time)
        )
        event_id = new_ulid()
        participants = [
            p.model_copy(update={"event_id": event_id}) for p in participants
        ]
        event = Event(
            id=event_id,
            user_id=candidate.user_id,
            type_id=self._concept_id(obl.type),
            action_id=None,
            actor_id=actor_id,
            subject_id=subject_id,
            participants=participants,
            temporal=temporal,
            status=EventStatus.SCHEDULED,
            domain_ids=[self._concept_id(ref) for ref in candidate.ir.domains],
            raw_input_id=raw_id,
            created_at=at,
        )
        uow.events.add(event)
        result.event_ids.append(event.id)
        self._facts(candidate.user_id, event.id, obl.facts, source, uow, at, result)

    def _state(
        self,
        candidate: KnowledgeCandidate,
        source: Source,
        raw_id: str,
        entity_ids: dict[str, str],
        uow: UnitOfWork,
        at: dt.datetime,
        result: MaterializationResult,
    ) -> None:
        ir_state = candidate.ir.state
        assert ir_state is not None
        if candidate.resolved_temporal is None or not candidate.has_persistable_temporal():
            raise MaterializationDenied("state sem tempo persistível")
        subject_id = self._subject_id(candidate.bindings, entity_ids)
        if subject_id is None:
            raise MaterializationDenied("state sem entidade sujeito")
        value_resolved = self._ontology.resolve_ref(ir_state.value)
        value_concept = self._ontology.get_by_id(value_resolved.concept_id or "")
        if value_concept is None or value_concept.kind is not ConceptKind.STATE_VALUE:
            raise MaterializationDenied("state value inválido")
        if ir_state.dimension is not None:
            dim_resolved = self._ontology.resolve_ref(ir_state.dimension)
            dim_concept = self._ontology.get_by_id(dim_resolved.concept_id or "")
        else:
            if value_concept.parent_id is None:
                raise MaterializationDenied("state sem dimensão")
            dim_concept = self._ontology.get_by_id(value_concept.parent_id)
        if dim_concept is None or dim_concept.kind is not ConceptKind.STATE_DIMENSION:
            raise MaterializationDenied("state dimension inválida")
        if value_concept.parent_id != dim_concept.id:
            raise MaterializationDenied("state value incompatível com dimensão")
        supersedes_id: str | None = None
        for old in uow.states.for_entity(candidate.user_id, subject_id):
            if old.dimension_key == dim_concept.key and old.is_current:
                closed = old.model_copy(update={"valid_to": at, "is_current": False})
                uow.states.save(closed)
                supersedes_id = old.id
        state = State(
            id=new_ulid(),
            user_id=candidate.user_id,
            entity_id=subject_id,
            dimension_id=dim_concept.id,
            dimension_key=dim_concept.key,
            value_concept_id=value_concept.id,
            value_key=value_concept.key,
            payload=ir_state.payload,
            temporal=candidate.resolved_temporal,
            observed_at=at,
            valid_from=None,
            supersedes_id=supersedes_id,
            is_current=True,
            source=source,
            raw_input_id=raw_id,
            confidence=Confidence(score=1.0),
            created_at=at,
        )
        uow.states.add(state)
        result.state_ids.append(state.id)

    def _attribute(
        self,
        candidate: KnowledgeCandidate,
        source: Source,
        raw_id: str,
        entity_ids: dict[str, str],
        uow: UnitOfWork,
        at: dt.datetime,
        result: MaterializationResult,
    ) -> None:
        ir_attr = candidate.ir.attribute
        assert ir_attr is not None
        self._attribute_record(
            candidate, source, raw_id, entity_ids, uow, at, result, ir_attr
        )

    def _attribute_record(
        self,
        candidate: KnowledgeCandidate,
        source: Source,
        raw_id: str,
        entity_ids: dict[str, str],
        uow: UnitOfWork,
        at: dt.datetime,
        result: MaterializationResult,
        ir_attr: Any,
    ) -> None:
        from pke.interpretation.models import IrAttribute
        from pke.interpretation.semantic.attribute_registry import get_dimension

        assert isinstance(ir_attr, IrAttribute)
        subject_id = entity_ids.get(ir_attr.subject.text)
        if subject_id is None:
            subject_id = self._subject_id(candidate.bindings, entity_ids)
        if subject_id is None:
            raise MaterializationDenied("attribute sem entidade sujeito")
        temporal = candidate.resolved_temporal
        if temporal is None:
            temporal = TemporalKnowledge.unknown(
                ir_attr.time.original_text or "",
                unknown_reason=TemporalUnknownReason.NOT_PROVIDED,
                tense_evidence=ir_attr.time.tense_evidence,
            )
        # Attribute allows UNKNOWN temporal — do not require is_persistable()
        if temporal.kind is TemporalKind.UNKNOWN and temporal.unknown_reason is None:
            temporal = temporal.model_copy(
                update={"unknown_reason": TemporalUnknownReason.NOT_PROVIDED}
            )
        numeric: Decimal | None = None
        if ir_attr.numeric_value is not None:
            try:
                numeric = Decimal(ir_attr.numeric_value)
            except (InvalidOperation, ValueError) as exc:
                raise MaterializationDenied("attribute numeric_value inválido") from exc

        supersedes_id: str | None = None
        dim_spec = get_dimension(ir_attr.dimension_key)
        if ir_attr.is_current and dim_spec is not None and dim_spec.singleton_current:
            for old in uow.attributes.for_entity_dimension(
                candidate.user_id, subject_id, ir_attr.dimension_key
            ):
                if old.is_current:
                    closed = old.model_copy(update={"is_current": False, "valid_to": at})
                    uow.attributes.save(closed)
                    supersedes_id = old.id

        attr = EntityAttribute(
            id=new_ulid(),
            user_id=candidate.user_id,
            entity_id=subject_id,
            dimension_key=ir_attr.dimension_key,
            dimension_concept_id=None,
            value_kind=AttributeValueKind(ir_attr.value_kind),
            concept_value_id=ir_attr.concept_value_id,
            text_value=ir_attr.text_value,
            numeric_value=numeric,
            unit=ir_attr.unit,
            date_value=ir_attr.date_value,
            year_value=ir_attr.year_value,
            temporal=temporal,
            observed_at=at,
            valid_from=None,
            valid_to=None,
            is_current=ir_attr.is_current,
            supersedes_id=supersedes_id,
            source=source,
            raw_input_id=raw_id,
            confidence=Confidence(score=1.0),
            created_at=at,
        )
        uow.attributes.add(attr)
        result.attribute_ids.append(attr.id)

    def _ensure_vehicle_ownership(
        self,
        candidate: KnowledgeCandidate,
        source: Source,
        raw_id: str,
        entity_ids: dict[str, str],
        uow: UnitOfWork,
        at: dt.datetime,
        result: MaterializationResult,
    ) -> None:
        """Link principal → relation.owns → vehicle when attribute subject is a vehicle Entity."""
        from pke.application.ownership import is_vehicle_entity
        from pke.domain.temporal_knowledge import TemporalUnknownReason

        ir_attr = candidate.ir.attribute
        if ir_attr is None:
            return
        vehicle_id = entity_ids.get(ir_attr.subject.text)
        if vehicle_id is None:
            return
        vehicle = uow.entities.get(candidate.user_id, vehicle_id)
        if vehicle is None or not is_vehicle_entity(vehicle, self._ontology):
            return
        binding = uow.principal_bindings.get(candidate.user_id)
        if binding is None:
            return
        principal_id = binding.entity_id
        if principal_id == vehicle_id:
            return
        owns_key = "relation.owns"
        owns_id = core_concept_id(owns_key)
        existing = uow.relations.find_instance(
            candidate.user_id, principal_id, owns_id, vehicle_id, current_only=True
        )
        if existing is not None:
            return
        relation = Relation(
            id=new_ulid(),
            user_id=candidate.user_id,
            from_id=principal_id,
            to_id=vehicle_id,
            concept_id=owns_id,
            key=owns_key,
            temporal=TemporalKnowledge.unknown(
                "",
                unknown_reason=TemporalUnknownReason.NOT_PROVIDED,
            ),
            observed_at=at,
            valid_from=None,
            valid_to=None,
            is_current=True,
            supersedes_id=None,
            source=source,
            raw_input_id=raw_id,
            confidence=Confidence(score=1.0),
            created_at=at,
        )
        uow.relations.add(relation)
        result.relation_ids.append(relation.id)

    def _measurement(
        self,
        candidate: KnowledgeCandidate,
        source: Source,
        raw_id: str,
        entity_ids: dict[str, str],
        uow: UnitOfWork,
        at: dt.datetime,
        result: MaterializationResult,
    ) -> None:
        ir_m = candidate.ir.measurement
        assert ir_m is not None
        entity_id = entity_ids.get(ir_m.subject.text)
        if entity_id is None:
            # Soft skip when co-materializing with Event — do not roll back Event
            if candidate.ir.event is not None:
                return
            raise MaterializationDenied("measurement sem entidade medida")
        context_id = None
        if ir_m.context is not None:
            context_id = entity_ids.get(ir_m.context.text)
            if context_id is None and candidate.ir.event is None:
                raise MaterializationDenied("measurement context entity unresolved")
        temporal = candidate.resolved_temporal
        if temporal is None:
            temporal = TemporalKnowledge.unknown(
                ir_m.time.original_text or "",
                unknown_reason=TemporalUnknownReason.NOT_PROVIDED,
                tense_evidence=ir_m.time.tense_evidence,
            )
        if temporal.kind is TemporalKind.UNKNOWN and temporal.unknown_reason is None:
            temporal = temporal.model_copy(
                update={"unknown_reason": TemporalUnknownReason.NOT_PROVIDED}
            )
        try:
            numeric = Decimal(ir_m.numeric_value)
        except (InvalidOperation, ValueError) as exc:
            if candidate.ir.event is not None:
                return
            raise MaterializationDenied("measurement numeric_value inválido") from exc
        # observed_at only when exact observation instant is known — never created_at
        observed_at = None
        if (
            temporal.kind is TemporalKind.EXACT
            and temporal.calendar is not None
            and temporal.calendar.instant is not None
        ):
            observed_at = temporal.calendar.instant
        measurement = Measurement(
            id=new_ulid(),
            user_id=candidate.user_id,
            entity_id=entity_id,
            context_entity_id=context_id,
            dimension_key=ir_m.dimension_key,
            dimension_concept_id=None,
            numeric_value=numeric,
            unit=ir_m.unit,
            currency_code=ir_m.currency_code,
            temporal=temporal,
            observed_at=observed_at,
            source=source,
            raw_input_id=raw_id,
            confidence=Confidence(score=1.0),
            created_at=at,
        )
        uow.measurements.add(measurement)
        result.measurement_ids.append(measurement.id)

    def _relation(
        self,
        candidate: KnowledgeCandidate,
        source: Source,
        raw_id: str,
        entity_ids: dict[str, str],
        uow: UnitOfWork,
        at: dt.datetime,
        result: MaterializationResult,
    ) -> None:
        ir_rel = candidate.ir.relation
        assert ir_rel is not None
        if candidate.resolved_temporal is None or not candidate.has_persistable_temporal():
            raise MaterializationDenied("relation sem tempo persistível")
        subject_id = entity_ids.get(ir_rel.subject.text)
        object_id = entity_ids.get(ir_rel.object.text)
        if subject_id is None or object_id is None:
            raise MaterializationDenied("relation sem endpoints resolvidos")
        from pke.interpretation.semantic.learned_relation import bind_learned_relation_types

        bind_learned_relation_types(self._ontology, candidate.ir)
        concept = self._ontology.resolve_ref(ir_rel.type)
        if concept.concept_id is None:
            raise MaterializationDenied("relation concept inválido")
        concept_entity = self._ontology.get_by_id(concept.concept_id)
        if concept_entity is None or concept_entity.kind is not ConceptKind.RELATION_TYPE:
            raise MaterializationDenied("relation type inválido")
        from_id, to_id = canonical_endpoints(subject_id, object_id, concept_entity.key)
        concept_id = concept_entity.id
        mode = ir_rel.mode
        if mode is RelationAssertionMode.TERMINATE:
            existing = uow.relations.find_instance(
                candidate.user_id, from_id, concept_id, to_id, current_only=True
            )
            if existing is None:
                existing = uow.relations.find_instance(
                    candidate.user_id, from_id, concept_id, to_id, current_only=False
                )
            if existing is not None:
                evidence = RelationTerminationEvidence(
                    temporal=candidate.resolved_temporal,
                    observed_at=at,
                    source=source,
                    raw_input_id=raw_id,
                    confidence=Confidence(score=1.0),
                )
                terminated = uow.relations.terminate(existing, evidence)
                result.relation_ids.append(terminated.id)
            return
        if mode is RelationAssertionMode.DENY_CURRENT:
            existing = uow.relations.find_instance(
                candidate.user_id, from_id, concept_id, to_id, current_only=True
            )
            if existing is not None:
                closed = existing.model_copy(update={"is_current": False})
                uow.relations.save(closed)
                result.relation_ids.append(existing.id)
            return
        is_current = _relation_is_current(mode, candidate.resolved_temporal)
        existing_current = uow.relations.find_instance(
            candidate.user_id, from_id, concept_id, to_id, current_only=True
        )
        if existing_current is not None and mode is RelationAssertionMode.ASSERT and is_current:
            refreshed = existing_current.model_copy(update={"observed_at": at})
            uow.relations.save(refreshed)
            result.relation_ids.append(existing_current.id)
            return
        valid_from = relation_calendar_start(candidate.resolved_temporal)
        relation = Relation(
            id=new_ulid(),
            user_id=candidate.user_id,
            from_id=from_id,
            to_id=to_id,
            concept_id=concept_id,
            key=concept_entity.key,
            temporal=candidate.resolved_temporal,
            observed_at=at,
            valid_from=valid_from,
            is_current=is_current,
            source=source,
            raw_input_id=raw_id,
            confidence=Confidence(score=1.0),
            created_at=at,
        )
        uow.relations.add(relation)
        result.relation_ids.append(relation.id)

    def _subject_id(
        self,
        bindings: list[MentionBinding],
        entity_ids: dict[str, str],
    ) -> str | None:
        for binding in bindings:
            eid = entity_ids.get(binding.mention.text)
            if eid is None:
                continue
            role = binding.mention.role.key if binding.mention.role else None
            if role in {None, "role.subject"}:
                return eid
        return next(iter(entity_ids.values()), None)

    def _correction(
        self,
        candidate: KnowledgeCandidate,
        source: Source,
        entity_ids: dict[str, str],
        uow: UnitOfWork,
        at: dt.datetime,
        result: MaterializationResult,
    ) -> None:
        del entity_ids
        corr = candidate.ir.correction
        assert corr is not None
        if not (corr.event_id or corr.fact_id):
            raise MaterializationDenied("last_event não é referência persistente")
        previous = None
        about_id = corr.event_id
        about_kind = AnchorKind.EVENT
        if corr.fact_id:
            previous = uow.facts.get(candidate.user_id, corr.fact_id)
            if previous is None:
                raise MaterializationDenied("fato a corrigir inexistente")
            about_id = previous.about_id
            about_kind = previous.about_kind
        elif corr.event_id:
            hist = uow.facts.history(
                candidate.user_id,
                corr.event_id,
                core_concept_id("attribute.amount"),
            )
            previous = next((fact for fact in reversed(hist) if fact.is_current), None)
        if previous is not None:
            uow.facts.save(previous.mark_superseded(at))
        if about_id is None:
            raise MaterializationDenied("correção sem âncora")
        self._facts(
            candidate.user_id,
            about_id,
            corr.facts,
            source,
            uow,
            at,
            result,
            about_kind=about_kind,
            supersedes_id=previous.id if previous else None,
        )

    def _facts(
        self,
        user_id: str,
        about_id: str,
        ir_facts: list[IrFact],
        source: Source,
        uow: UnitOfWork,
        at: dt.datetime,
        result: MaterializationResult,
        *,
        about_kind: AnchorKind = AnchorKind.EVENT,
        supersedes_id: str | None = None,
    ) -> None:
        first = True
        for ir_fact in ir_facts:
            concept = self._ontology.resolve_ref(ir_fact.attribute)
            assert concept.concept_id is not None
            fact = Fact(
                id=new_ulid(),
                user_id=user_id,
                about_kind=about_kind,
                about_id=about_id,
                concept_id=concept.concept_id,
                key=concept.key,
                value=_fact_value(ir_fact),
                qualifier=ir_fact.qualifier,
                epistemic_status=ir_fact.epistemic_status,
                source=source,
                confidence=Confidence(score=ir_fact.confidence, qualifier=ir_fact.qualifier),
                supersedes_id=supersedes_id,
                created_at=at,
            )
            uow.facts.add(fact)
            result.fact_ids.append(fact.id)
            if first:
                first = False
                if self._on_progress is not None:
                    self._on_progress("first_fact", result)

    def _participants(
        self,
        bindings: list[MentionBinding],
        entity_ids: dict[str, str],
        *,
        event_id: str | None,
    ) -> list[EventParticipant]:
        """Build canonical EventParticipant rows from resolved mention roles."""
        eid_placeholder = event_id or "pending"
        out: list[EventParticipant] = []
        seen: set[tuple[str, str]] = set()
        for binding in bindings:
            eid = entity_ids.get(binding.mention.text)
            if eid is None or binding.mention.role is None:
                continue
            role = binding.mention.role.key
            if role == "role.provider":
                role = "role.actor"
            elif role == "role.subject":
                role = "role.object"
            if role not in {
                "role.actor",
                "role.object",
                "role.patient",
                "role.context",
                "role.unspecified",
            }:
                continue
            key = (eid, role)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                EventParticipant(
                    id=new_ulid(),
                    event_id=eid_placeholder,
                    entity_id=eid,
                    role=role,
                )
            )
        return out

    def _legacy_slots(
        self, participants: list[EventParticipant]
    ) -> tuple[str | None, str | None]:
        """Compatibility projection only — never store context as actor_id."""
        actor: str | None = None
        subject: str | None = None
        for p in participants:
            if p.role == "role.actor" and actor is None:
                actor = p.entity_id
            if p.role in {"role.object", "role.patient"} and subject is None:
                subject = p.entity_id
        return actor, subject

    def _roles(
        self,
        bindings: list[MentionBinding],
        entity_ids: dict[str, str],
    ) -> tuple[str | None, str | None]:
        return self._legacy_slots(self._participants(bindings, entity_ids, event_id=None))

    def _concept_id(self, ref: ConceptRef) -> str:
        resolved = self._ontology.resolve_ref(ref)
        assert resolved.concept_id is not None
        return resolved.concept_id


def _relation_is_current(mode: RelationAssertionMode, temporal: TemporalKnowledge) -> bool:
    if mode is RelationAssertionMode.HISTORICAL:
        return False
    if mode is RelationAssertionMode.TERMINATE or mode is RelationAssertionMode.DENY_CURRENT:
        return False
    occ = temporal.occurrence_status
    if occ is OccurrenceStatus.HAPPENED:
        return False
    if occ is OccurrenceStatus.PLANNED:
        return False
    return True


def _recurrence_time(cadence: Recurrence) -> TimeValue:
    return TimeValue(
        original_text=f"todo dia {cadence.by_monthday}" if cadence.by_monthday else cadence.freq,
        precision=TimePrecision.RECURRING,
        recurrence=cadence,
        resolution_rule="recurrence.as_stated",
    )


def _fact_value(ir_fact: IrFact) -> Any:
    value = ir_fact.value
    if ir_fact.attribute.key == "attribute.amount":
        amount, currency = _money_parts(value)
        return Money(amount=amount, currency=currency)
    return value


def _money_parts(value: object) -> tuple[Decimal, str]:
    if isinstance(value, Money):
        return value.amount, value.currency
    if isinstance(value, dict):
        raw = value.get("amount")
        currency = value.get("currency") or "BRL"
        return Decimal(str(raw)), str(currency)
    try:
        return Decimal(str(value)), "BRL"
    except InvalidOperation as exc:
        raise MaterializationDenied("valor monetário inválido") from exc
