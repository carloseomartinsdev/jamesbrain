"""Registry ontológico em memória. Resolve conceitos, não entidades do usuário."""

from __future__ import annotations

from pke.domain.ontology import (
    ConceptKind,
    ConceptRef,
    ConceptScope,
    OntologyConcept,
)
from pke.ontology.errors import (
    ConceptConflictError,
    ConceptKindError,
    ConceptNotFoundError,
    CoreMutationError,
)
from pke.ontology.seeds import CORE_SCHEMA_VERSION, CORE_SEEDS

_MAX_ANCESTRY = 32


class OntologyRegistry:
    """Catálogo determinístico. CORE via seeds; EXTENDED/PERSONAL só estrutural."""

    def __init__(self, *, core_schema_version: str = CORE_SCHEMA_VERSION) -> None:
        self._core_schema_version = core_schema_version
        self._by_id: dict[str, OntologyConcept] = {}
        self._global_by_key: dict[str, OntologyConcept] = {}
        self._personal: dict[tuple[str, str], OntologyConcept] = {}
        self._core_frozen = False

    @classmethod
    def with_core_seeds(cls) -> OntologyRegistry:
        registry = cls()
        registry.load_core_seeds()
        return registry

    @property
    def core_schema_version(self) -> str:
        return self._core_schema_version

    @property
    def core_frozen(self) -> bool:
        return self._core_frozen

    def load_core_seeds(self) -> None:
        for seed in CORE_SEEDS:
            self._put_core(seed.to_concept())
        self._core_frozen = True

    def register(self, concept: OntologyConcept) -> OntologyConcept:
        if concept.scope is ConceptScope.CORE:
            raise CoreMutationError("conceitos CORE só entram via seeds")
        if concept.scope is ConceptScope.PERSONAL:
            return self._put_personal(concept)
        return self._put_extended(concept)

    def get_by_id(self, concept_id: str) -> OntologyConcept | None:
        return self._by_id.get(concept_id)

    def get_by_key(
        self,
        key: str,
        *,
        owner_user_id: str | None = None,
    ) -> OntologyConcept | None:
        if owner_user_id is not None:
            personal = self._personal.get((owner_user_id, key))
            if personal is not None:
                return personal
        return self._global_by_key.get(key)

    def exists(self, key: str, *, owner_user_id: str | None = None) -> bool:
        return self.get_by_key(key, owner_user_id=owner_user_id) is not None

    def require(
        self,
        key: str,
        *,
        owner_user_id: str | None = None,
        kind: ConceptKind | None = None,
        scope: ConceptScope | None = None,
    ) -> OntologyConcept:
        concept = self.get_by_key(key, owner_user_id=owner_user_id)
        if concept is None:
            raise ConceptNotFoundError(key)
        self._assert_kind(concept, kind)
        if scope is not None and concept.scope is not scope:
            raise ConceptConflictError(
                f"scope incompatível para {key}: {concept.scope} != {scope}"
            )
        return concept

    def resolve_ref(
        self,
        ref: ConceptRef,
        *,
        expected_kind: ConceptKind | None = None,
        owner_user_id: str | None = None,
    ) -> ConceptRef:
        concept = self.get_by_key(ref.key, owner_user_id=owner_user_id)
        if concept is None:
            raise ConceptNotFoundError(ref.key)
        if ref.concept_id is not None and ref.concept_id != concept.id:
            raise ConceptConflictError(
                f"divergência key×id: {ref.key} != {ref.concept_id}"
            )
        by_id = self.get_by_id(ref.concept_id) if ref.concept_id else None
        if by_id is not None and by_id.key != ref.key:
            raise ConceptConflictError(
                f"divergência key×id: {ref.key} aponta para {by_id.key}"
            )
        self._assert_kind(concept, expected_kind)
        return concept.as_ref()

    def is_child_of(self, concept: str, parent: str) -> bool:
        child = self._resolve_token(concept)
        ancestor = self._resolve_token(parent)
        return child.parent_id == ancestor.id

    def descendant_ids(self, ancestor: str, *, include_self: bool = False) -> list[str]:
        root = self._resolve_token(ancestor)
        ids = [root.id] if include_self else []
        for concept in self.concepts():
            if concept.id == root.id:
                continue
            if self.is_descendant_of(concept.id, root.id):
                ids.append(concept.id)
        return ids

    def is_descendant_of(self, concept: str, ancestor: str) -> bool:
        current = self._resolve_token(concept)
        target = self._resolve_token(ancestor)
        if current.id == target.id:
            return False
        seen: set[str] = set()
        for _ in range(_MAX_ANCESTRY):
            if current.parent_id is None:
                return False
            if current.parent_id in seen:
                return False
            seen.add(current.parent_id)
            parent = self.get_by_id(current.parent_id)
            if parent is None:
                return False
            if parent.id == target.id:
                return True
            current = parent
        return False

    def concepts(
        self,
        *,
        scope: ConceptScope | None = None,
        owner_user_id: str | None = None,
    ) -> tuple[OntologyConcept, ...]:
        if scope is ConceptScope.PERSONAL:
            if owner_user_id is None:
                return tuple(self._personal.values())
            return tuple(
                c
                for (uid, _key), c in self._personal.items()
                if uid == owner_user_id
            )
        values = tuple(self._global_by_key.values())
        if scope is None:
            extras = tuple(self._personal.values())
            return values + extras
        return tuple(c for c in values if c.scope is scope)

    def _put_core(self, concept: OntologyConcept) -> OntologyConcept:
        existing = self._global_by_key.get(concept.key)
        if existing is None:
            if self._core_frozen:
                raise CoreMutationError(f"CORE congelado; recusado: {concept.key}")
            return self._index_global(concept)
        if not self._same_identity(existing, concept):
            raise CoreMutationError(f"mutação de CORE recusada: {concept.key}")
        return existing

    def _put_extended(self, concept: OntologyConcept) -> OntologyConcept:
        if concept.key in self._global_by_key:
            existing = self._global_by_key[concept.key]
            if existing.scope is ConceptScope.CORE:
                raise ConceptConflictError(f"key CORE já existe: {concept.key}")
            if not self._same_identity(existing, concept):
                raise ConceptConflictError(f"key duplicada: {concept.key}")
            return existing
        return self._index_global(concept)

    def _put_personal(self, concept: OntologyConcept) -> OntologyConcept:
        owner = concept.owner_user_id
        if owner is None:
            raise ConceptConflictError("PERSONAL exige owner_user_id")
        if concept.key in self._global_by_key:
            raise ConceptConflictError(
                f"key PERSONAL não pode colidir com CORE/EXTENDED: {concept.key}"
            )
        slot = (owner, concept.key)
        existing = self._personal.get(slot)
        if existing is not None:
            if not self._same_identity(existing, concept):
                raise ConceptConflictError(f"key PERSONAL duplicada: {concept.key}")
            return existing
        self._by_id[concept.id] = concept
        self._personal[slot] = concept
        return concept

    def _index_global(self, concept: OntologyConcept) -> OntologyConcept:
        if concept.id in self._by_id:
            raise ConceptConflictError(f"id duplicado: {concept.id}")
        self._by_id[concept.id] = concept
        self._global_by_key[concept.key] = concept
        return concept

    def _resolve_token(self, token: str) -> OntologyConcept:
        found = self.get_by_id(token) or self.get_by_key(token)
        if found is None:
            raise ConceptNotFoundError(token)
        return found

    @staticmethod
    def _assert_kind(concept: OntologyConcept, kind: ConceptKind | None) -> None:
        if kind is not None and concept.kind is not kind:
            raise ConceptKindError(
                f"kind incompatível para {concept.key}: {concept.kind} != {kind}"
            )

    @staticmethod
    def _same_identity(left: OntologyConcept, right: OntologyConcept) -> bool:
        return (
            left.id == right.id
            and left.key == right.key
            and left.kind == right.kind
            and left.scope == right.scope
            and left.parent_id == right.parent_id
            and left.status == right.status
            and left.owner_user_id == right.owner_user_id
        )
