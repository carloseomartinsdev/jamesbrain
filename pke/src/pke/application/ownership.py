"""Principal ownership via relation.owns — language-independent graph walk."""

from __future__ import annotations

from pke.domain.entities import Entity
from pke.domain.relations import Relation
from pke.ontology.registry import OntologyRegistry
from pke.ontology.seeds import core_concept_id


def is_vehicle_entity(entity: Entity, ontology: OntologyRegistry) -> bool:
    vehicle_type = core_concept_id("entity.vehicle")
    if entity.type_id == vehicle_type:
        return True
    return ontology.is_descendant_of(entity.type_id, vehicle_type)


def owned_entity_ids(
    *,
    principal_entity_id: str,
    relations: list[Relation],
    entities: dict[str, Entity],
) -> list[str]:
    """Current relation.owns targets of the actor (any entity type).

    Maps reference_kind=possessive onto the graph. Does not inspect raw_input.
    """
    owns_id = core_concept_id("relation.owns")
    out: list[str] = []
    seen: set[str] = set()
    for rel in relations:
        if not rel.is_current:
            continue
        if rel.concept_id != owns_id and rel.key != "relation.owns":
            continue
        if rel.from_id != principal_entity_id:
            continue
        if rel.to_id in seen:
            continue
        if entities.get(rel.to_id) is None:
            continue
        seen.add(rel.to_id)
        out.append(rel.to_id)
    return out


def owned_vehicle_entity_ids(
    *,
    principal_entity_id: str,
    relations: list[Relation],
    entities: dict[str, Entity],
    ontology: OntologyRegistry,
) -> list[str]:
    """Current relation.owns targets that are vehicle (or vehicle descendant) entities."""
    return [
        eid
        for eid in owned_entity_ids(
            principal_entity_id=principal_entity_id,
            relations=relations,
            entities=entities,
        )
        if is_vehicle_entity(entities[eid], ontology)
    ]
