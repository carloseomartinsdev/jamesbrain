"""Learn an entity type from an Interpreter class lemma — not a linguistic glossary."""

from __future__ import annotations

from pke.interpretation.semantic.learned_relation import slug_from_expression
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology.learned import (
    LEARNED_ENTITY_PREFIX,
    ensure_if_learned_entity,
    is_learned_entity_key,
)
from pke.ontology.registry import OntologyRegistry


def publish_entity_type(key: str) -> None:
    if key:
        ConceptCatalog.entity_types.add(key)


def learned_entity_key_from_class_hint(class_hint: str) -> str | None:
    slug = slug_from_expression(class_hint)
    if slug is None:
        return None
    key = f"{LEARNED_ENTITY_PREFIX}{slug}"
    if not is_learned_entity_key(key):
        return None
    return key


def bind_learned_entity_types(ontology: OntologyRegistry, ir: object) -> None:
    """Register EXTENDED entity types from IR type hints before resolve/query."""
    for key in _type_hint_keys(ir):
        _bind_one(ontology, key)


def _type_hint_keys(ir: object) -> list[str]:
    keys: list[str] = []
    for mention in _mentions(ir):
        hint = getattr(mention, "type_hint", None)
        key = getattr(hint, "key", None) if hint is not None else None
        if key:
            keys.append(key)
        entity_type = getattr(mention, "entity_type", None)
        if isinstance(entity_type, str) and entity_type:
            keys.append(entity_type)
    return keys


def _mentions(ir: object) -> list[object]:
    found: list[object] = []
    for attr in ("entities_mentioned",):
        found.extend(list(getattr(ir, attr, None) or []))
    relation = getattr(ir, "relation", None)
    if relation is not None:
        found.append(getattr(relation, "subject", None))
        found.append(getattr(relation, "object", None))
    for extra in getattr(ir, "additional_relations", None) or []:
        found.append(getattr(extra, "subject", None))
        found.append(getattr(extra, "object", None))
    for attr in ("attribute", "measurement"):
        slot = getattr(ir, attr, None)
        if slot is not None:
            found.append(getattr(slot, "subject", None))
            found.append(getattr(slot, "context", None))
    for extra in getattr(ir, "additional_attributes", None) or []:
        found.append(getattr(extra, "subject", None))
    for extra in getattr(ir, "additional_measurements", None) or []:
        found.append(getattr(extra, "subject", None))
        found.append(getattr(extra, "context", None))
    query = getattr(ir, "query", None)
    if query is not None:
        found.extend(list(getattr(query, "entities", None) or []))
    return [m for m in found if m is not None]


def _bind_one(ontology: OntologyRegistry, key: str | None) -> None:
    if not key:
        return
    if ensure_if_learned_entity(ontology, key):
        publish_entity_type(key)
        return
    from pke.ontology.trained import ensure_if_trained

    if ensure_if_trained(ontology, key):
        publish_entity_type(key)
