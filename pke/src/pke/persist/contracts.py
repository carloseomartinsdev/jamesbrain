"""Contratos de repositório — sem SQLAlchemy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pke.domain.attributes import EntityAttribute
from pke.domain.corrections import Correction, KnowledgePrimitiveKind
from pke.domain.entities import Entity
from pke.domain.events import Event
from pke.domain.facts import Fact
from pke.domain.measurements import Measurement
from pke.domain.principal import PrincipalBinding
from pke.domain.relations import Relation, RelationTerminationEvidence
from pke.domain.states import State
from pke.domain.value_objects import RawInput, Source


class RawInputRepository(Protocol):
    def add(self, raw: RawInput) -> RawInput: ...

    def get(self, user_id: str, raw_id: str) -> RawInput | None: ...


class EntityRepository(Protocol):
    def add(self, entity: Entity) -> Entity: ...

    def get(self, user_id: str, entity_id: str) -> Entity | None: ...

    def all_for_user(self, user_id: str) -> list[Entity]: ...


class EventRepository(Protocol):
    def add(self, event: Event) -> Event: ...

    def get(self, user_id: str, event_id: str) -> Event | None: ...


class FactRepository(Protocol):
    def add(self, fact: Fact) -> Fact: ...

    def save(self, fact: Fact) -> Fact: ...

    def get(self, user_id: str, fact_id: str) -> Fact | None: ...

    def history(self, user_id: str, about_id: str, concept_id: str) -> list[Fact]: ...


class RelationRepository(Protocol):
    def add(self, relation: Relation) -> Relation: ...

    def get(self, user_id: str, relation_id: str) -> Relation | None: ...

    def find_instance(
        self,
        user_id: str,
        from_id: str,
        concept_id: str,
        to_id: str,
        *,
        current_only: bool = False,
    ) -> Relation | None: ...

    def for_entity(self, user_id: str, entity_id: str) -> list[Relation]: ...

    def save(self, relation: Relation) -> Relation: ...

    def terminate(
        self, relation: Relation, evidence: RelationTerminationEvidence
    ) -> Relation: ...


class StateRepository(Protocol):
    def add(self, state: State) -> State: ...

    def get(self, user_id: str, state_id: str) -> State | None: ...

    def for_entity(self, user_id: str, entity_id: str) -> list[State]: ...

    def save(self, state: State) -> State: ...


class AttributeRepository(Protocol):
    def add(self, attr: EntityAttribute) -> EntityAttribute: ...

    def get(self, user_id: str, attribute_id: str) -> EntityAttribute | None: ...

    def for_entity(self, user_id: str, entity_id: str) -> list[EntityAttribute]: ...

    def for_entity_dimension(
        self, user_id: str, entity_id: str, dimension_key: str
    ) -> list[EntityAttribute]: ...

    def list_by_entity_dimension(
        self, user_id: str, entity_id: str, dimension_key: str
    ) -> list[EntityAttribute]: ...

    def save(self, attr: EntityAttribute) -> EntityAttribute: ...


class MeasurementRepository(Protocol):
    def add(self, measurement: Measurement) -> Measurement: ...

    def get(self, user_id: str, measurement_id: str) -> Measurement | None: ...

    def for_user(self, user_id: str) -> list[Measurement]: ...

    def for_entity(self, user_id: str, entity_id: str) -> list[Measurement]: ...

    def for_entity_dimension(
        self, user_id: str, entity_id: str, dimension_key: str
    ) -> list[Measurement]: ...


class CorrectionRepository(Protocol):
    def add(self, correction: Correction) -> Correction: ...

    def get(self, user_id: str, correction_id: str) -> Correction | None: ...

    def find_by_target(
        self,
        user_id: str,
        kind: KnowledgePrimitiveKind | str,
        assertion_id: str,
    ) -> Correction | None: ...

    def find_by_targets(
        self,
        user_id: str,
        refs: Sequence[tuple[KnowledgePrimitiveKind | str, str]],
    ) -> list[Correction]: ...

    def find_by_replacement(
        self,
        user_id: str,
        kind: KnowledgePrimitiveKind | str,
        assertion_id: str,
    ) -> list[Correction]: ...

    def for_user(self, user_id: str) -> list[Correction]: ...


class SourceRepository(Protocol):
    def add(self, source: Source) -> Source: ...

    def get(self, user_id: str, source_id: str) -> Source | None: ...


class PrincipalBindingRepository(Protocol):
    def get(self, user_id: str) -> PrincipalBinding | None: ...

    def put(self, binding: PrincipalBinding) -> PrincipalBinding: ...


class UnitOfWork(Protocol):
    raw_inputs: RawInputRepository
    entities: EntityRepository
    events: EventRepository
    facts: FactRepository
    relations: RelationRepository
    states: StateRepository
    attributes: AttributeRepository
    measurements: MeasurementRepository
    corrections: CorrectionRepository
    sources: SourceRepository
    principal_bindings: PrincipalBindingRepository

    def begin(self) -> UnitOfWork: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
