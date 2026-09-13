"""EXTENDED types learned at runtime without growing CORE.

CORE stays frozen. Unmatched relation expressions persist as
`relation.learned.{slug}`. Interpreter class lemmas persist as
`entity.learned.{slug}`. Both use deterministic ids (`ext:{key}`) so restart
hydrates the same concept the stored rows already point at.
"""

from __future__ import annotations

from pke.domain.ontology import (
    CONCEPT_KEY_PATTERN,
    ConceptKind,
    ConceptPresentation,
    ConceptScope,
    OntologyConcept,
)
from pke.ontology.registry import OntologyRegistry
from pke.ontology.seeds import CORE_CREATED_AT

import re

LEARNED_PREFIX = "relation.learned."
LEARNED_ENTITY_PREFIX = "entity.learned."
LEARNED_ATTRIBUTE_PREFIX = "attribute.learned."
EXTENDED_ID_PREFIX = "ext:"
_KEY_RE = re.compile(CONCEPT_KEY_PATTERN)


def is_learned_relation_key(key: str) -> bool:
    return bool(key) and key.startswith(LEARNED_PREFIX) and _KEY_RE.fullmatch(key) is not None


def learned_concept_id(key: str) -> str:
    return f"{EXTENDED_ID_PREFIX}{key}"


def ensure_learned_relation_type(
    ontology: OntologyRegistry,
    key: str,
    *,
    label: str | None = None,
) -> OntologyConcept:
    existing = ontology.get_by_key(key)
    if existing is not None:
        return existing
    if not is_learned_relation_key(key):
        raise ValueError(f"not a learned relation key: {key}")
    slug = key.rsplit(".", 1)[-1]
    concept = OntologyConcept(
        id=learned_concept_id(key),
        key=key,
        kind=ConceptKind.RELATION_TYPE,
        scope=ConceptScope.EXTENDED,
        created_at=CORE_CREATED_AT,
        presentation=ConceptPresentation(label=label or slug.replace("_", " ")),
    )
    return ontology.register(concept)


def ensure_if_learned(ontology: OntologyRegistry, key: str) -> bool:
    if not is_learned_relation_key(key):
        return False
    ensure_learned_relation_type(ontology, key)
    return True


def hydrate_learned_relation_types(ontology: OntologyRegistry, engine) -> int:
    """Re-register EXTENDED types from persisted relation keys after process restart."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT key FROM relations WHERE key LIKE :pfx"),
                {"pfx": f"{LEARNED_PREFIX}%"},
            ).fetchall()
    except OperationalError:
        return 0
    count = 0
    for (key,) in rows:
        if not key or not is_learned_relation_key(key):
            continue
        ensure_learned_relation_type(ontology, key)
        count += 1
    return count


def is_learned_entity_key(key: str) -> bool:
    return (
        bool(key)
        and key.startswith(LEARNED_ENTITY_PREFIX)
        and _KEY_RE.fullmatch(key) is not None
    )


def ensure_learned_entity_type(
    ontology: OntologyRegistry,
    key: str,
    *,
    label: str | None = None,
) -> OntologyConcept:
    existing = ontology.get_by_key(key)
    if existing is not None:
        return existing
    if not is_learned_entity_key(key):
        raise ValueError(f"not a learned entity key: {key}")
    slug = key.rsplit(".", 1)[-1]
    concept = OntologyConcept(
        id=learned_concept_id(key),
        key=key,
        kind=ConceptKind.ENTITY_TYPE,
        scope=ConceptScope.EXTENDED,
        created_at=CORE_CREATED_AT,
        presentation=ConceptPresentation(label=label or slug.replace("_", " ")),
    )
    return ontology.register(concept)


def ensure_if_learned_entity(ontology: OntologyRegistry, key: str) -> bool:
    if not is_learned_entity_key(key):
        return False
    ensure_learned_entity_type(ontology, key)
    return True


def is_learned_attribute_key(key: str) -> bool:
    return (
        bool(key)
        and key.startswith(LEARNED_ATTRIBUTE_PREFIX)
        and _KEY_RE.fullmatch(key) is not None
    )


def ensure_learned_attribute_dimension(
    ontology: OntologyRegistry,
    key: str,
    *,
    label: str | None = None,
) -> OntologyConcept:
    existing = ontology.get_by_key(key)
    if existing is not None:
        return existing
    if not is_learned_attribute_key(key):
        raise ValueError(f"not a learned attribute key: {key}")
    slug = key.rsplit(".", 1)[-1]
    concept = OntologyConcept(
        id=learned_concept_id(key),
        key=key,
        kind=ConceptKind.ATTRIBUTE,
        scope=ConceptScope.EXTENDED,
        created_at=CORE_CREATED_AT,
        presentation=ConceptPresentation(label=label or slug.replace("_", " ")),
    )
    return ontology.register(concept)


def ensure_if_learned_attribute(ontology: OntologyRegistry, key: str) -> bool:
    if not is_learned_attribute_key(key):
        return False
    ensure_learned_attribute_dimension(ontology, key)
    return True


def hydrate_learned_attribute_dimensions(ontology: OntologyRegistry, engine) -> int:
    """Re-register EXTENDED attribute dimensions from persisted rows after restart."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT DISTINCT dimension_key FROM entity_attributes "
                    "WHERE dimension_key LIKE :pfx"
                ),
                {"pfx": f"{LEARNED_ATTRIBUTE_PREFIX}%"},
            ).fetchall()
    except OperationalError:
        return 0
    count = 0
    for (key,) in rows:
        if not key or not is_learned_attribute_key(key):
            continue
        ensure_learned_attribute_dimension(ontology, key)
        count += 1
    return count


def hydrate_learned_entity_types(ontology: OntologyRegistry, engine) -> int:
    """Re-register EXTENDED entity types from persisted entity.type_id after restart."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT type_id FROM entities WHERE type_id LIKE :pfx"),
                {"pfx": f"{EXTENDED_ID_PREFIX}{LEARNED_ENTITY_PREFIX}%"},
            ).fetchall()
    except OperationalError:
        return 0
    count = 0
    for (type_id,) in rows:
        if not type_id or not str(type_id).startswith(EXTENDED_ID_PREFIX):
            continue
        key = str(type_id)[len(EXTENDED_ID_PREFIX) :]
        if not is_learned_entity_key(key):
            continue
        ensure_learned_entity_type(ontology, key)
        count += 1
    return count
