from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pke.domain import (
    ConceptKind,
    ConceptRef,
    ConceptScope,
    OntologyConcept,
    new_ulid,
)
from pke.ontology import (
    CORE_SCHEMA_VERSION,
    CORE_SEEDS,
    ConceptConflictError,
    ConceptKindError,
    ConceptNotFoundError,
    CoreMutationError,
    OntologyRegistry,
    core_concept_id,
)


def _personal(key: str, owner: str) -> OntologyConcept:
    return OntologyConcept(
        id=new_ulid(),
        key=key,
        kind=ConceptKind.ENTITY_TYPE,
        scope=ConceptScope.PERSONAL,
        owner_user_id=owner,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def _extended(key: str) -> OntologyConcept:
    return OntologyConcept(
        id=new_ulid(),
        key=key,
        kind=ConceptKind.ENTITY_TYPE,
        scope=ConceptScope.EXTENDED,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def test_lookup_by_key() -> None:
    registry = OntologyRegistry.with_core_seeds()
    vehicle = registry.get_by_key("entity.vehicle")
    assert vehicle is not None
    assert vehicle.kind is ConceptKind.ENTITY_TYPE
    assert vehicle.scope is ConceptScope.CORE


def test_lookup_by_id() -> None:
    registry = OntologyRegistry.with_core_seeds()
    expected = core_concept_id("entity.vehicle")
    found = registry.get_by_id(expected)
    assert found is not None
    assert found.key == "entity.vehicle"


def test_seed_is_idempotent() -> None:
    registry = OntologyRegistry.with_core_seeds()
    first = registry.concepts(scope=ConceptScope.CORE)
    registry.load_core_seeds()
    second = registry.concepts(scope=ConceptScope.CORE)
    assert [c.id for c in first] == [c.id for c in second]
    assert len(first) == len(CORE_SEEDS)


def test_core_ids_are_stable_across_registries() -> None:
    a = OntologyRegistry.with_core_seeds()
    b = OntologyRegistry.with_core_seeds()
    assert a.get_by_key("entity.automobile").id == b.get_by_key("entity.automobile").id
    assert a.get_by_key("entity.automobile").id == core_concept_id("entity.automobile")
    assert a.core_schema_version == CORE_SCHEMA_VERSION == "1"


def test_duplicate_key_rejected() -> None:
    registry = OntologyRegistry.with_core_seeds()
    with pytest.raises(ConceptConflictError, match="CORE já existe"):
        registry.register(_extended("entity.vehicle"))
    registry.register(_extended("entity.toll_tag"))
    with pytest.raises(ConceptConflictError, match="key duplicada"):
        registry.register(_extended("entity.toll_tag"))


def test_hierarchy_automobile_is_child_of_vehicle() -> None:
    registry = OntologyRegistry.with_core_seeds()
    assert registry.is_child_of("entity.automobile", "entity.vehicle")
    assert not registry.is_child_of("entity.vehicle", "entity.automobile")


def test_is_descendant_of() -> None:
    registry = OntologyRegistry.with_core_seeds()
    assert registry.is_descendant_of("entity.automobile", "entity.vehicle")
    assert registry.is_descendant_of("event.vehicle_maintenance", "event.maintenance")
    assert registry.is_descendant_of("action.oil_change", "action.maintain")
    assert not registry.is_descendant_of("entity.vehicle", "entity.automobile")
    assert not registry.is_descendant_of("entity.vehicle", "entity.vehicle")


def test_resolve_concept_ref_fills_id() -> None:
    registry = OntologyRegistry.with_core_seeds()
    resolved = registry.resolve_ref(ConceptRef(key="attribute.amount"))
    assert resolved.concept_id == core_concept_id("attribute.amount")
    again = registry.resolve_ref(resolved)
    assert again == resolved


def test_concept_ref_key_id_conflict() -> None:
    registry = OntologyRegistry.with_core_seeds()
    with pytest.raises(ConceptConflictError, match="divergência"):
        registry.resolve_ref(
            ConceptRef(
                key="entity.vehicle",
                concept_id=core_concept_id("entity.person"),
            )
        )


def test_incompatible_kind_rejected() -> None:
    registry = OntologyRegistry.with_core_seeds()
    with pytest.raises(ConceptKindError):
        registry.resolve_ref(
            ConceptRef(key="entity.vehicle"),
            expected_kind=ConceptKind.EVENT_TYPE,
        )
    with pytest.raises(ConceptKindError):
        registry.require("action.pay", kind=ConceptKind.ATTRIBUTE)


def test_missing_concept_rejected() -> None:
    registry = OntologyRegistry.with_core_seeds()
    assert registry.exists("entity.unicorn") is False
    with pytest.raises(ConceptNotFoundError):
        registry.resolve_ref(ConceptRef(key="entity.unicorn"))
    with pytest.raises(ConceptNotFoundError):
        registry.require("entity.unicorn")


def test_core_mutation_rejected() -> None:
    registry = OntologyRegistry.with_core_seeds()
    with pytest.raises(CoreMutationError):
        registry.register(
            OntologyConcept(
                id=core_concept_id("entity.spaceship"),
                key="entity.spaceship",
                kind=ConceptKind.ENTITY_TYPE,
                scope=ConceptScope.CORE,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
    mutated = registry.require("entity.vehicle").model_copy(
        update={"kind": ConceptKind.EVENT_TYPE}
    )
    with pytest.raises(CoreMutationError):
        registry.register(mutated)


def test_personal_is_isolated_from_core_lookup() -> None:
    registry = OntologyRegistry.with_core_seeds()
    garage = _personal("entity.my_garage", "u1")
    registry.register(garage)
    assert registry.get_by_key("entity.my_garage") is None
    assert registry.get_by_key("entity.my_garage", owner_user_id="u1") is not None
    assert registry.get_by_key("entity.my_garage", owner_user_id="u2") is None
    assert registry.get_by_key("entity.vehicle", owner_user_id="u1").scope is ConceptScope.CORE
    with pytest.raises(ConceptConflictError, match="colidir"):
        registry.register(_personal("entity.vehicle", "u1"))


def test_presentation_is_not_identity() -> None:
    registry = OntologyRegistry.with_core_seeds()
    vehicle = registry.require("entity.vehicle")
    assert vehicle.key == "entity.vehicle"
    assert vehicle.presentation is not None
    assert vehicle.presentation.label != vehicle.key
    assert registry.get_by_key("Veículo") is None
