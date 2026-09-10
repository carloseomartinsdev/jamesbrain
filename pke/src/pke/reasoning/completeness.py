"""Completeness — o que falta de verdade? Sem texto de UI."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pke.interpretation.models import IngestIntent, IrFact
from pke.ontology.errors import ConceptNotFoundError
from pke.ontology.registry import OntologyRegistry
from pke.reasoning.candidate import KnowledgeCandidate, MentionBinding
from pke.reasoning.schemas import (
    CompletenessSchema,
    CompletenessSchemaRegistry,
    Importance,
    Requirement,
    SlotKind,
)
from pke.resolution.entities import ResolutionStatus
from pke.resolution.lookup import EntityLookup


class Presence(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    INVALID = "invalid"


class RequirementEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: str
    concept_key: str
    importance: Importance
    status: Presence
    priority: int


class ClarificationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_key: str
    priority: int
    reason: str
    question_key: str
    blocking: bool


class CompletenessResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluations: list[RequirementEvaluation] = Field(default_factory=list)
    clarification: ClarificationCandidate | None = None
    schema_key: str | None = None

    @property
    def essential_missing(self) -> list[str]:
        return [
            e.slot
            for e in self.evaluations
            if e.importance is Importance.ESSENTIAL and e.status is Presence.MISSING
        ]

    @property
    def useful_missing(self) -> list[str]:
        return [
            e.slot
            for e in self.evaluations
            if e.importance is Importance.USEFUL and e.status is Presence.MISSING
        ]

    @property
    def blocking(self) -> bool:
        return bool(self.essential_missing)


class CompletenessEngine:
    def __init__(
        self,
        ontology: OntologyRegistry,
        lookup: EntityLookup,
        schemas: CompletenessSchemaRegistry | None = None,
    ) -> None:
        self._ontology = ontology
        self._lookup = lookup
        self._schemas = schemas or CompletenessSchemaRegistry.core()

    def evaluate(self, candidate: KnowledgeCandidate) -> CompletenessResult:
        schema = self._schema_for(candidate)
        if schema is None:
            return CompletenessResult()
        evaluations = [
            RequirementEvaluation(
                slot=req.slot,
                concept_key=req.concept_key,
                importance=req.importance,
                status=self._presence(req, candidate),
                priority=req.priority,
            )
            for req in schema.requirements
        ]
        clarification = self._pick_clarification(schema, evaluations)
        return CompletenessResult(
            evaluations=evaluations,
            clarification=clarification,
            schema_key=schema.applies_to_key,
        )

    def _schema_for(self, candidate: KnowledgeCandidate) -> CompletenessSchema | None:
        ir = candidate.ir
        if ir.intent is IngestIntent.CORRECT or ir.correction is not None:
            return self._schemas.get("intent.correct")
        key = None
        if ir.event is not None:
            key = ir.event.type.key
        elif ir.obligation is not None:
            key = ir.obligation.type.key
        if key is None:
            return None
        return self._schemas.resolve_for(key, self._ontology)

    def _presence(self, req: Requirement, candidate: KnowledgeCandidate) -> Presence:
        check = req.check
        if check is SlotKind.TIME:
            return (
                Presence.PRESENT
                if candidate.has_persistable_temporal()
                else Presence.MISSING
            )
        if check is SlotKind.SUBJECT:
            return Presence.PRESENT if candidate.user_id else Presence.MISSING
        if check is SlotKind.EVENT_TYPE:
            has_type = candidate.ir.event or candidate.ir.obligation
            return Presence.PRESENT if has_type else Presence.MISSING
        if check is SlotKind.ACTION:
            action = candidate.ir.event.action if candidate.ir.event else None
            if action is None:
                return Presence.MISSING
            return (
                Presence.PRESENT
                if self._compatible_key(action.key, req.concept_key)
                else Presence.INVALID
            )
        if check is SlotKind.FACT:
            return Presence.PRESENT if _has_fact(candidate, req.concept_key) else Presence.MISSING
        if check is SlotKind.RECURRENCE:
            obl = candidate.ir.obligation
            if obl is None:
                return Presence.NOT_APPLICABLE
            rec = obl.cadence
            if rec.freq == "monthly" and rec.by_monthday is not None:
                return Presence.PRESENT
            return Presence.MISSING
        if check is SlotKind.DUE:
            obl = candidate.ir.obligation
            if obl is None:
                return Presence.NOT_APPLICABLE
            if candidate.resolved_due is not None:
                return Presence.PRESENT
            if obl.cadence.by_monthday is not None:
                return Presence.PRESENT
            if obl.due is not None:
                return Presence.PRESENT
            return Presence.MISSING
        if check is SlotKind.CORRECTION_TARGET:
            corr = candidate.ir.correction
            if corr is None:
                return Presence.NOT_APPLICABLE
            return Presence.PRESENT if (corr.event_id or corr.fact_id) else Presence.MISSING
        if check is SlotKind.CORRECTION_FACT:
            corr = candidate.ir.correction
            if corr is None:
                return Presence.NOT_APPLICABLE
            return Presence.PRESENT if corr.facts else Presence.MISSING
        if check is SlotKind.ENTITY:
            bindings = self._entity_bindings(candidate, req.concept_key)
            if not bindings:
                return Presence.MISSING
            if any(b.resolution.status is ResolutionStatus.AMBIGUOUS for b in bindings):
                return Presence.INVALID
            if any(
                b.resolution.status
                in {ResolutionStatus.RESOLVED, ResolutionStatus.CREATE_CANDIDATE}
                for b in bindings
            ):
                return Presence.PRESENT
            return Presence.MISSING
        return Presence.NOT_APPLICABLE

    def _entity_bindings(
        self,
        candidate: KnowledgeCandidate,
        concept_key: str,
    ) -> list[MentionBinding]:
        if concept_key.startswith("slot."):
            return []
        try:
            hint = self._ontology.require(concept_key)
        except ConceptNotFoundError:
            return []
        matched: list[MentionBinding] = []
        for binding in candidate.bindings:
            type_id = None
            if binding.mention.type_hint is not None:
                try:
                    type_id = self._ontology.resolve_ref(binding.mention.type_hint).concept_id
                except (ConceptNotFoundError, Exception):
                    type_id = None
            if binding.resolution.create_type_id:
                type_id = type_id or binding.resolution.create_type_id
            if binding.resolution.entity_id:
                entity = self._lookup.get_by_id(binding.resolution.entity_id, candidate.user_id)
                if entity is not None:
                    type_id = entity.type_id
            if type_id and self._compatible_id(type_id, hint.id):
                matched.append(binding)
        return matched

    def _compatible_key(self, got_key: str, expected_key: str) -> bool:
        if got_key == expected_key:
            return True
        got = self._ontology.get_by_key(got_key)
        expected = self._ontology.get_by_key(expected_key)
        if got is None or expected is None:
            return False
        return self._ontology.is_descendant_of(got.id, expected.id)

    def _compatible_id(self, got_id: str, expected_id: str) -> bool:
        if got_id == expected_id:
            return True
        return self._ontology.is_descendant_of(got_id, expected_id)

    def _pick_clarification(
        self,
        schema: CompletenessSchema,
        evaluations: list[RequirementEvaluation],
    ) -> ClarificationCandidate | None:
        by_slot = {e.slot: e for e in evaluations}
        essential: list[Requirement] = []
        useful: list[Requirement] = []
        for req in schema.requirements:
            ev = by_slot.get(req.slot)
            if ev is None or ev.status is not Presence.MISSING:
                continue
            if req.importance is Importance.ESSENTIAL:
                essential.append(req)
            elif req.importance is Importance.USEFUL and req.ask_if_missing:
                useful.append(req)
        chosen = None
        blocking = False
        reason = ""
        if essential:
            chosen = min(essential, key=lambda r: r.priority)
            blocking = True
            reason = "essential_missing"
        elif useful:
            chosen = min(useful, key=lambda r: r.priority)
            reason = "useful_high_value"
        if chosen is None or chosen.clarification_key is None:
            return None
        return ClarificationCandidate(
            concept_key=chosen.concept_key,
            priority=chosen.priority,
            reason=reason,
            question_key=chosen.clarification_key,
            blocking=blocking,
        )


def _has_fact(candidate: KnowledgeCandidate, concept_key: str) -> bool:
    facts: list[IrFact] = []
    ir = candidate.ir
    if ir.event:
        facts = list(ir.event.facts)
    elif ir.obligation:
        facts = list(ir.obligation.facts)
    elif ir.correction:
        facts = list(ir.correction.facts)
    return any(fact.attribute.key == concept_key for fact in facts)
