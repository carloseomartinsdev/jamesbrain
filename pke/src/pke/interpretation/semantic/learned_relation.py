"""Learn a relation type from a complete semantic link — not Attribute invention."""

from __future__ import annotations

import re

from pke.interpretation.semantic.aliases import normalize_expression
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology.learned import (
    LEARNED_PREFIX,
    ensure_if_learned,
    is_learned_relation_key,
)
from pke.ontology.registry import OntologyRegistry

_SLUG_MAX = 48
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def publish_relation_type(key: str) -> None:
    ConceptCatalog.relation_types.add(key)


def slug_from_expression(expression: str) -> str | None:
    norm = normalize_expression(expression)
    cleaned = _NON_SLUG.sub("_", norm).strip("_")
    if not cleaned:
        return None
    if cleaned[0].isdigit():
        cleaned = f"r_{cleaned}"
    if len(cleaned) > _SLUG_MAX:
        cleaned = cleaned[:_SLUG_MAX].rstrip("_")
    if not cleaned or not cleaned[0].isalpha():
        return None
    return cleaned


def learned_key_from_expression(expression: str) -> str | None:
    slug = slug_from_expression(expression)
    if slug is None:
        return None
    key = f"{LEARNED_PREFIX}{slug}"
    if not is_learned_relation_key(key):
        return None
    return key


def bind_learned_relation_types(ontology: OntologyRegistry, ir: object) -> None:
    """Register EXTENDED types on the runtime ontology before validate/query."""
    relation = getattr(ir, "relation", None)
    if relation is not None:
        key = getattr(getattr(relation, "type", None), "key", None)
        _bind_one(ontology, key)
        return
    query = getattr(ir, "query", None)
    if query is None:
        return
    for ref in getattr(query, "relation_types", []) or []:
        _bind_one(ontology, getattr(ref, "key", None))


def _bind_one(ontology: OntologyRegistry, key: str | None) -> None:
    if not key:
        return
    if ensure_if_learned(ontology, key):
        publish_relation_type(key)
        return
    from pke.ontology.trained import ensure_if_trained

    if ensure_if_trained(ontology, key):
        publish_relation_type(key)
