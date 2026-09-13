"""EntityResolver — menção → EntityResolution. Não persiste e não chama Interpreter."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pke.domain.entities import Entity
from pke.domain.ontology import ConceptKind, ConceptRef
from pke.interpretation.models import EntityMention, MentionReferenceKind
from pke.ontology.registry import OntologyRegistry
from pke.resolution.context import ResolutionContext, ResolutionPurpose
from pke.resolution.errors import ContextIsolationError, ForeignEntityError
from pke.resolution.lookup import EntityLookup
from pke.resolution.normalize import normalize_lexical
from pke.resolution.self_ref import is_self_entity_mention, is_self_lexeme

_VEHICLE_CONTEXT_LEXEMES = frozenset(
    {
        "carro",
        "car",
        "veiculo",
        "veículo",
        "auto",
        "automovel",
        "automóvel",
        "moto",
        "motocicleta",
    }
)


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    CREATE_CANDIDATE = "create_candidate"


class EvidenceKind(StrEnum):
    EXPLICIT_ID = "explicit_id"
    EXACT_CANONICAL_NAME = "exact_canonical_name"
    EXACT_ALIAS = "exact_alias"
    TYPE_MATCH = "type_match"
    TYPE_DESCENDANT_MATCH = "type_descendant_match"
    RECENT_ENTITY = "recent_entity"
    ROLE_MATCH = "role_match"
    UNIQUE_CANDIDATE = "unique_candidate"
    CONFIRMED_PERSONAL_ALIAS = "confirmed_personal_alias"
    CONTEXTUAL_REFERENCE = "contextual_reference"
    PRINCIPAL_BINDING = "principal_binding"
    OWNED_BY_PRINCIPAL = "owned_by_principal"


class ResolutionConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class ResolutionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    evidence: list[EvidenceKind] = Field(default_factory=list)


class EntityResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResolutionStatus
    original_text: str
    entity_id: str | None = None
    candidates: list[ResolutionCandidate] = Field(default_factory=list)
    confidence: ResolutionConfidence = ResolutionConfidence.NONE
    evidence: list[EvidenceKind] = Field(default_factory=list)
    requires_clarification: bool = False
    clarification_reason: str | None = None
    suggested_alias: str | None = None
    create_type_id: str | None = None
    create_canonical_name: str | None = None
    notes: list[str] = Field(default_factory=list)


class EntityResolver:
    def __init__(self, lookup: EntityLookup, ontology: OntologyRegistry) -> None:
        self._lookup = lookup
        self._ontology = ontology

    def resolve(self, mention: EntityMention, context: ResolutionContext) -> EntityResolution:
        resolution = self._resolve(mention, context)
        try:
            from pke.debug.semantic_trace import record_entity_resolution

            record_entity_resolution(
                mention, resolution, self._lookup, self._ontology, context
            )
        except Exception:
            pass
        return resolution

    def _resolve(self, mention: EntityMention, context: ResolutionContext) -> EntityResolution:
        if context.personal.user_id != context.user_id:
            raise ContextIsolationError("contexto pessoal isolado por usuário")

        if mention.known_entity_id:
            return self._from_explicit_id(mention, context)

        hint_id = self._hint_type_id(mention.type_hint)

        if mention.reference_kind is MentionReferenceKind.CLASS:
            return EntityResolution(
                status=ResolutionStatus.UNRESOLVED,
                original_text=mention.text,
                requires_clarification=False,
                clarification_reason="class_is_type_constraint",
            )

        if mention.reference_kind is MentionReferenceKind.POSSESSIVE:
            return self._from_possessive(mention, context, hint_id)

        if mention.reference_kind is MentionReferenceKind.CONTEXTUAL:
            return self._from_context(mention, context, hint_id)

        return self._from_named(mention, context, hint_id)

    def _from_explicit_id(
        self,
        mention: EntityMention,
        context: ResolutionContext,
    ) -> EntityResolution:
        entity_id = mention.known_entity_id
        assert entity_id is not None
        entity = self._lookup.get_by_id(entity_id, context.user_id)
        if entity is None:
            raise ForeignEntityError(f"entidade não visível para {context.user_id}")
        evidence = [EvidenceKind.EXPLICIT_ID]
        type_ev = self._type_evidence(entity, self._hint_type_id(mention.type_hint), context)
        if type_ev:
            evidence.append(type_ev)
        # Explicit id is identity (discourse binding / known_entity_id).
        # Coarse kind_hint must not veto a listed id (thing vs entity.learned.cat).
        return EntityResolution(
            status=ResolutionStatus.RESOLVED,
            original_text=mention.text,
            entity_id=entity.id,
            candidates=[ResolutionCandidate(entity_id=entity.id, evidence=evidence)],
            confidence=ResolutionConfidence.HIGH,
            evidence=evidence,
        )

    def _from_named(
        self,
        mention: EntityMention,
        context: ResolutionContext,
        hint_id: str | None,
    ) -> EntityResolution:
        """Name is the identity key. type_hint ranks/disambiguates; it is not a hard filter."""
        scored = self._lexical_candidates(mention, context, hint_id)
        if len(scored) == 1:
            return self._resolved_unique(
                mention,
                scored[0],
                notes=_named_unique_notes(scored[0], hint_id),
            )
        if len(scored) > 1:
            compatible = [c for c in scored if _has_type_match(c)] if hint_id else []
            if hint_id and len(compatible) == 1:
                return self._resolved_unique(
                    mention,
                    compatible[0],
                    notes=["named_disambiguated_by_type"],
                )
            return EntityResolution(
                status=ResolutionStatus.AMBIGUOUS,
                original_text=mention.text,
                candidates=scored,
                confidence=ResolutionConfidence.LOW,
                evidence=_merge_evidence(scored),
                requires_clarification=True,
                clarification_reason="multiple_equivalent_candidates",
                notes=["named_multiple_candidates"],
            )
        if hint_id is not None and context.purpose is ResolutionPurpose.INGEST:
            return EntityResolution(
                status=ResolutionStatus.CREATE_CANDIDATE,
                original_text=mention.text,
                confidence=ResolutionConfidence.MEDIUM,
                create_type_id=hint_id,
                create_canonical_name=mention.text,
                clarification_reason=None,
            )
        if hint_id is not None and context.purpose is ResolutionPurpose.QUERY:
            return EntityResolution(
                status=ResolutionStatus.UNRESOLVED,
                original_text=mention.text,
                requires_clarification=False,
                clarification_reason="query_entity_not_found",
            )
        return EntityResolution(
            status=ResolutionStatus.UNRESOLVED,
            original_text=mention.text,
            requires_clarification=True,
            clarification_reason="no_candidate_without_type",
        )

    def _from_context(
        self,
        mention: EntityMention,
        context: ResolutionContext,
        hint_id: str | None,
    ) -> EntityResolution:
        if is_self_entity_mention(mention) or (
            mention.reference_kind is MentionReferenceKind.CONTEXTUAL
            and is_self_lexeme(mention.text)
        ):
            return self._from_principal(mention, context)

        if (
            hint_id is not None
            and self._is_vehicle_hint(hint_id)
            and (
                mention.reference_kind is MentionReferenceKind.POSSESSIVE
                or normalize_lexical(mention.text) in _VEHICLE_CONTEXT_LEXEMES
            )
        ):
            owned = self._owned_vehicle_resolution(mention, context, hint_id)
            if owned is not None:
                return owned

        if hint_id is None:
            return EntityResolution(
                status=ResolutionStatus.UNRESOLVED,
                original_text=mention.text,
                requires_clarification=True,
                clarification_reason="contextual_reference_needs_type",
            )
        recent = self._recent_compatible(context, hint_id)
        if len(recent) == 1:
            entity, extra = recent[0]
            evidence = [
                EvidenceKind.CONTEXTUAL_REFERENCE,
                EvidenceKind.RECENT_ENTITY,
                EvidenceKind.UNIQUE_CANDIDATE,
                extra,
            ]
            return EntityResolution(
                status=ResolutionStatus.RESOLVED,
                original_text=mention.text,
                entity_id=entity.id,
                candidates=[ResolutionCandidate(entity_id=entity.id, evidence=evidence)],
                confidence=ResolutionConfidence.MEDIUM,
                evidence=evidence,
                suggested_alias=None,
            )
        if len(recent) > 1:
            candidates = [
                ResolutionCandidate(
                    entity_id=entity.id,
                    evidence=[EvidenceKind.CONTEXTUAL_REFERENCE, EvidenceKind.RECENT_ENTITY, ev],
                )
                for entity, ev in recent
            ]
            return EntityResolution(
                status=ResolutionStatus.AMBIGUOUS,
                original_text=mention.text,
                candidates=candidates,
                confidence=ResolutionConfidence.LOW,
                evidence=[EvidenceKind.CONTEXTUAL_REFERENCE],
                requires_clarification=True,
                clarification_reason="contextual_reference_ambiguous",
                suggested_alias=None,
            )
        return EntityResolution(
            status=ResolutionStatus.UNRESOLVED,
            original_text=mention.text,
            requires_clarification=True,
            clarification_reason="no_contextual_candidate",
            suggested_alias=None,
        )

    def _from_possessive(
        self,
        mention: EntityMention,
        context: ResolutionContext,
        hint_id: str | None,
    ) -> EntityResolution:
        """possessive(type=T) → owns(actor, X) AND type(X)=T. No raw_input."""
        if hint_id is None:
            return EntityResolution(
                status=ResolutionStatus.UNRESOLVED,
                original_text=mention.text,
                requires_clarification=True,
                clarification_reason="possessive_needs_type",
            )
        matching = self._owned_matching_type(context, hint_id)
        if len(matching) == 1:
            entity = matching[0]
            evidence = [
                EvidenceKind.OWNED_BY_PRINCIPAL,
                EvidenceKind.UNIQUE_CANDIDATE,
                EvidenceKind.TYPE_MATCH,
            ]
            return EntityResolution(
                status=ResolutionStatus.RESOLVED,
                original_text=mention.text,
                entity_id=entity.id,
                candidates=[ResolutionCandidate(entity_id=entity.id, evidence=evidence)],
                confidence=ResolutionConfidence.HIGH,
                evidence=evidence,
            )
        if len(matching) > 1:
            candidates = [
                ResolutionCandidate(
                    entity_id=e.id,
                    evidence=[EvidenceKind.OWNED_BY_PRINCIPAL, EvidenceKind.TYPE_MATCH],
                )
                for e in matching
            ]
            return EntityResolution(
                status=ResolutionStatus.AMBIGUOUS,
                original_text=mention.text,
                candidates=candidates,
                confidence=ResolutionConfidence.LOW,
                evidence=[EvidenceKind.OWNED_BY_PRINCIPAL],
                requires_clarification=True,
                clarification_reason="possessive_ambiguous",
            )
        if context.purpose is ResolutionPurpose.INGEST:
            return EntityResolution(
                status=ResolutionStatus.CREATE_CANDIDATE,
                original_text=mention.text,
                confidence=ResolutionConfidence.MEDIUM,
                create_type_id=hint_id,
                create_canonical_name=None,
                clarification_reason=None,
                notes=["possessive_owned_object_create"],
            )
        return EntityResolution(
            status=ResolutionStatus.UNRESOLVED,
            original_text=mention.text,
            requires_clarification=False,
            clarification_reason="possessive_no_match",
        )

    def _principal_owned_ids(self, context: ResolutionContext) -> list[str]:
        seen: list[str] = []
        for eid in [*context.owned_entity_ids, *context.owned_vehicle_entity_ids]:
            if eid not in seen:
                seen.append(eid)
        return seen

    def _owned_matching_type(
        self,
        context: ResolutionContext,
        hint_id: str,
    ) -> list[Entity]:
        matching: list[Entity] = []
        for eid in self._principal_owned_ids(context):
            entity = self._lookup.get_by_id(eid, context.user_id)
            if entity is None:
                continue
            type_ev = self._type_evidence(entity, hint_id, context)
            if type_ev is None:
                continue
            matching.append(entity)
        return matching

    def _is_vehicle_hint(self, hint_id: str) -> bool:
        vehicle_type = self._ontology.resolve_ref(
            ConceptRef(key="entity.vehicle"), expected_kind=ConceptKind.ENTITY_TYPE
        ).concept_id
        if vehicle_type is None:
            return False
        if hint_id == vehicle_type:
            return True
        return self._ontology.is_descendant_of(hint_id, vehicle_type)

    def _owned_vehicle_resolution(
        self,
        mention: EntityMention,
        context: ResolutionContext,
        hint_id: str,
    ) -> EntityResolution | None:
        owned_ids = list(context.owned_vehicle_entity_ids)
        owned_entities: list[Entity] = []
        for eid in owned_ids:
            entity = self._lookup.get_by_id(eid, context.user_id)
            if entity is None:
                continue
            type_ev = self._type_evidence(entity, hint_id, context)
            if type_ev is None:
                continue
            owned_entities.append(entity)

        if len(owned_entities) == 1:
            entity = owned_entities[0]
            evidence = [
                EvidenceKind.CONTEXTUAL_REFERENCE,
                EvidenceKind.OWNED_BY_PRINCIPAL,
                EvidenceKind.UNIQUE_CANDIDATE,
                EvidenceKind.TYPE_MATCH,
            ]
            return EntityResolution(
                status=ResolutionStatus.RESOLVED,
                original_text=mention.text,
                entity_id=entity.id,
                candidates=[ResolutionCandidate(entity_id=entity.id, evidence=evidence)],
                confidence=ResolutionConfidence.HIGH,
                evidence=evidence,
            )

        if len(owned_entities) > 1:
            # Prefer unique recent among owned
            recent_ids = set(context.personal.recent_entity_ids)
            recent_owned = [e for e in owned_entities if e.id in recent_ids]
            last_type = context.personal.last_by_type_id.get(hint_id)
            if last_type and any(e.id == last_type for e in owned_entities):
                entity = next(e for e in owned_entities if e.id == last_type)
                evidence = [
                    EvidenceKind.CONTEXTUAL_REFERENCE,
                    EvidenceKind.OWNED_BY_PRINCIPAL,
                    EvidenceKind.RECENT_ENTITY,
                    EvidenceKind.UNIQUE_CANDIDATE,
                ]
                return EntityResolution(
                    status=ResolutionStatus.RESOLVED,
                    original_text=mention.text,
                    entity_id=entity.id,
                    candidates=[ResolutionCandidate(entity_id=entity.id, evidence=evidence)],
                    confidence=ResolutionConfidence.MEDIUM,
                    evidence=evidence,
                )
            if len(recent_owned) == 1:
                entity = recent_owned[0]
                evidence = [
                    EvidenceKind.CONTEXTUAL_REFERENCE,
                    EvidenceKind.OWNED_BY_PRINCIPAL,
                    EvidenceKind.RECENT_ENTITY,
                    EvidenceKind.UNIQUE_CANDIDATE,
                ]
                return EntityResolution(
                    status=ResolutionStatus.RESOLVED,
                    original_text=mention.text,
                    entity_id=entity.id,
                    candidates=[ResolutionCandidate(entity_id=entity.id, evidence=evidence)],
                    confidence=ResolutionConfidence.MEDIUM,
                    evidence=evidence,
                )
            candidates = [
                ResolutionCandidate(
                    entity_id=e.id,
                    evidence=[EvidenceKind.CONTEXTUAL_REFERENCE, EvidenceKind.OWNED_BY_PRINCIPAL],
                )
                for e in owned_entities
            ]
            return EntityResolution(
                status=ResolutionStatus.AMBIGUOUS,
                original_text=mention.text,
                candidates=candidates,
                confidence=ResolutionConfidence.LOW,
                evidence=[EvidenceKind.CONTEXTUAL_REFERENCE, EvidenceKind.OWNED_BY_PRINCIPAL],
                requires_clarification=True,
                clarification_reason="owned_vehicle_ambiguous",
            )

        if context.purpose is ResolutionPurpose.INGEST:
            return EntityResolution(
                status=ResolutionStatus.CREATE_CANDIDATE,
                original_text=mention.text,
                confidence=ResolutionConfidence.MEDIUM,
                create_type_id=hint_id,
                create_canonical_name=None,
                clarification_reason=None,
            )
        return EntityResolution(
            status=ResolutionStatus.UNRESOLVED,
            original_text=mention.text,
            requires_clarification=False,
            clarification_reason="owned_vehicle_missing",
        )

    def _from_principal(
        self, mention: EntityMention, context: ResolutionContext
    ) -> EntityResolution:
        entity_id = context.principal_entity_id
        if entity_id is None:
            return EntityResolution(
                status=ResolutionStatus.UNRESOLVED,
                original_text=mention.text,
                requires_clarification=False,
                clarification_reason="principal_binding_required",
            )
        if entity_id == context.user_id:
            return EntityResolution(
                status=ResolutionStatus.UNRESOLVED,
                original_text=mention.text,
                clarification_reason="principal_entity_collapses_auth_identity",
            )
        entity = self._lookup.get_by_id(entity_id, context.user_id)
        if entity is None:
            return EntityResolution(
                status=ResolutionStatus.UNRESOLVED,
                original_text=mention.text,
                clarification_reason="principal_entity_missing",
            )
        evidence = [
            EvidenceKind.CONTEXTUAL_REFERENCE,
            EvidenceKind.PRINCIPAL_BINDING,
            EvidenceKind.UNIQUE_CANDIDATE,
        ]
        return EntityResolution(
            status=ResolutionStatus.RESOLVED,
            original_text=mention.text,
            entity_id=entity.id,
            candidates=[ResolutionCandidate(entity_id=entity.id, evidence=evidence)],
            confidence=ResolutionConfidence.HIGH,
            evidence=evidence,
        )

    def _lexical_candidates(
        self,
        mention: EntityMention,
        context: ResolutionContext,
        hint_id: str | None,
    ) -> list[ResolutionCandidate]:
        normalized = normalize_lexical(mention.text)
        by_id: dict[str, list[EvidenceKind]] = {}

        for entity in self._lookup.by_canonical_name(context.user_id, normalized):
            ev = self._type_evidence(entity, hint_id, context)
            by_id.setdefault(entity.id, []).append(EvidenceKind.EXACT_CANONICAL_NAME)
            if ev:
                by_id[entity.id].append(ev)

        for entity in self._lookup.by_alias(context.user_id, normalized):
            ev = self._type_evidence(entity, hint_id, context)
            by_id.setdefault(entity.id, []).append(EvidenceKind.EXACT_ALIAS)
            if ev:
                by_id[entity.id].append(ev)

        confirmed_id = context.personal.confirmed_aliases.get(normalized)
        if confirmed_id:
            entity = self._lookup.get_by_id(confirmed_id, context.user_id)
            if entity is not None:
                ev = self._type_evidence(entity, hint_id, context)
                by_id.setdefault(entity.id, []).append(EvidenceKind.CONFIRMED_PERSONAL_ALIAS)
                if ev:
                    by_id[entity.id].append(ev)

        if mention.role is not None:
            role_entity_id = context.personal.last_by_role_key.get(mention.role.key)
            if role_entity_id in by_id:
                by_id[role_entity_id].append(EvidenceKind.ROLE_MATCH)

        return [
            ResolutionCandidate(entity_id=eid, evidence=_unique(evs))
            for eid, evs in by_id.items()
        ]

    def _recent_compatible(
        self,
        context: ResolutionContext,
        hint_id: str,
    ) -> list[tuple[Entity, EvidenceKind]]:
        found: list[tuple[Entity, EvidenceKind]] = []
        seen: set[str] = set()
        for entity_id in reversed(context.personal.recent_entity_ids):
            entity = self._lookup.get_by_id(entity_id, context.user_id)
            if entity is None or entity.id in seen:
                continue
            ev = self._type_evidence(entity, hint_id, context)
            if ev is None:
                continue
            seen.add(entity.id)
            found.append((entity, ev))
        return found

    def _hint_type_id(self, hint: ConceptRef | None) -> str | None:
        if hint is None:
            return None
        resolved = self._ontology.resolve_ref(hint, expected_kind=ConceptKind.ENTITY_TYPE)
        assert resolved.concept_id is not None
        return resolved.concept_id

    def _type_evidence(
        self,
        entity: Entity,
        hint_id: str | None,
        context: ResolutionContext,
    ) -> EvidenceKind | None:
        if hint_id is None:
            return None
        if entity.type_id == hint_id:
            return EvidenceKind.TYPE_MATCH
        if context.allow_type_descendants and self._ontology.is_descendant_of(
            entity.type_id, hint_id
        ):
            return EvidenceKind.TYPE_DESCENDANT_MATCH
        return None

    def _resolved_unique(
        self,
        mention: EntityMention,
        candidate: ResolutionCandidate,
        *,
        notes: list[str] | None = None,
    ) -> EntityResolution:
        evidence = [*candidate.evidence, EvidenceKind.UNIQUE_CANDIDATE]
        high = (
            EvidenceKind.EXACT_CANONICAL_NAME in evidence
            or EvidenceKind.EXPLICIT_ID in evidence
        )
        return EntityResolution(
            status=ResolutionStatus.RESOLVED,
            original_text=mention.text,
            entity_id=candidate.entity_id,
            candidates=[ResolutionCandidate(entity_id=candidate.entity_id, evidence=evidence)],
            confidence=ResolutionConfidence.HIGH if high else ResolutionConfidence.MEDIUM,
            evidence=evidence,
            suggested_alias=None,
            notes=list(notes or []),
        )


def _has_type_match(candidate: ResolutionCandidate) -> bool:
    return (
        EvidenceKind.TYPE_MATCH in candidate.evidence
        or EvidenceKind.TYPE_DESCENDANT_MATCH in candidate.evidence
    )


def _named_unique_notes(candidate: ResolutionCandidate, hint_id: str | None) -> list[str]:
    if hint_id is None:
        return ["named_exact_match"]
    if _has_type_match(candidate):
        return ["named_exact_match"]
    return ["named_match_with_nonbinding_type_hint", "type_hint_mismatch"]


def _unique(items: list[EvidenceKind]) -> list[EvidenceKind]:
    seen: list[EvidenceKind] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen

def _merge_evidence(candidates: list[ResolutionCandidate]) -> list[EvidenceKind]:
    merged: list[EvidenceKind] = []
    for candidate in candidates:
        for item in candidate.evidence:
            if item not in merged:
                merged.append(item)
    return merged
