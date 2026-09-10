"""EXTENDED relation types learned from complete link assertions.

CORE stays frozen. Unmatched `relation_expression` + subject + object persist as
`relation.learned.{slug}` with a deterministic id (`ext:{key}`) so restart hydrates
the same concept the stored rows already point at.
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
