"""Metadados conceituais de Relation — direção, inversos, simetria; não duplicam storage.

Inverse keys are metadata only (not CORE concepts). Query/materializer rewrite
to the stored key and swap endpoints. Learned relations may register optional
metadata; nothing is auto-inferred. See ADR 0093.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RelationDirectionality(StrEnum):
    DIRECTED = "directed"
    SYMMETRIC = "symmetric"
    UNDIRECTED = "undirected"


@dataclass(frozen=True)
class RelationConceptMetadata:
    meaning: str
    direction: str
    inverse: str | None = None
    symmetric: bool = False
    why_core: str = ""
    directionality: RelationDirectionality = RelationDirectionality.DIRECTED


RELATION_METADATA: dict[str, RelationConceptMetadata] = {
    "relation.employed_by": RelationConceptMetadata(
        meaning="Pessoa empregada por organização",
        direction="person → organization",
        inverse="relation.employs",
        why_core="R1 employment; PEOPLE_001",
        directionality=RelationDirectionality.DIRECTED,
    ),
    "relation.resides_at": RelationConceptMetadata(
        meaning="Pessoa reside em local",
        direction="person → place",
        why_core="R2 residence",
        directionality=RelationDirectionality.DIRECTED,
    ),
    "relation.owns": RelationConceptMetadata(
        meaning="Pessoa possui bem",
        direction="person → thing",
        inverse="relation.owned_by",
        why_core="R3 ownership — direção canônica person owns thing",
        directionality=RelationDirectionality.DIRECTED,
    ),
    "relation.likes": RelationConceptMetadata(
        meaning="Pessoa gosta de entidade ou coisa",
        direction="person → thing",
        why_core="R7 preference / like — not an Attribute dimension",
        directionality=RelationDirectionality.DIRECTED,
    ),
    "relation.married_to": RelationConceptMetadata(
        meaning="Casamento entre pessoas",
        direction="person ↔ person",
        symmetric=True,
        why_core="R4 marriage",
        directionality=RelationDirectionality.SYMMETRIC,
    ),
    "relation.parent_of": RelationConceptMetadata(
        meaning="Pessoa é progenitora de outra",
        direction="parent → child",
        inverse="relation.child_of",
        why_core="R5 parent relation",
        directionality=RelationDirectionality.DIRECTED,
    ),
    "relation.provider_for": RelationConceptMetadata(
        meaning="Prestador de serviço/profissional para pessoa",
        direction="provider → person",
        inverse="relation.client_of",
        why_core="R6 provider relation",
        directionality=RelationDirectionality.DIRECTED,
    ),
}

_LEARNED_RELATION_METADATA: dict[str, RelationConceptMetadata] = {}

SYMMETRIC_RELATION_KEYS = frozenset(
    key for key, meta in RELATION_METADATA.items() if meta.symmetric
)


def metadata_for(key: str) -> RelationConceptMetadata | None:
    if key in RELATION_METADATA:
        return RELATION_METADATA[key]
    return _LEARNED_RELATION_METADATA.get(key)


def register_learned_relation_metadata(key: str, meta: RelationConceptMetadata) -> None:
    """Optional metadata for a learned relation. Never infers inverse/direction."""
    if not key.startswith("relation.learned."):
        raise ValueError(f"learned relation metadata requires relation.learned.*: {key}")
    _LEARNED_RELATION_METADATA[key] = meta


def clear_learned_relation_metadata() -> None:
    _LEARNED_RELATION_METADATA.clear()


def _metadata_table() -> dict[str, RelationConceptMetadata]:
    if not _LEARNED_RELATION_METADATA:
        return RELATION_METADATA
    return {**RELATION_METADATA, **_LEARNED_RELATION_METADATA}


def _key_candidates(key: str) -> tuple[str, ...]:
    if key.startswith("relation."):
        return (key,)
    return (key, f"relation.{key}")


def stored_relation_query(key: str) -> tuple[str, bool]:
    """Map a query/assert key to the persisted relation key.

    Returns (stored_key, endpoints_swapped). Inverse keys are not stored;
    callers swap subject/object and use the forward key.
    """
    table = _metadata_table()
    candidates = _key_candidates(key)
    for cand in candidates:
        if cand in table:
            return cand, False
    key_suffix = key.rsplit(".", 1)[-1]
    for stored, meta in table.items():
        if not meta.inverse:
            continue
        if meta.inverse in candidates:
            return stored, True
        if meta.inverse.rsplit(".", 1)[-1] == key_suffix:
            return stored, True
    return key, False


def is_order_insensitive(relation_key: str) -> bool:
    meta = metadata_for(relation_key)
    if meta is None:
        return relation_key in SYMMETRIC_RELATION_KEYS
    if meta.symmetric:
        return True
    return meta.directionality in {
        RelationDirectionality.SYMMETRIC,
        RelationDirectionality.UNDIRECTED,
    }


def canonical_endpoints(
    subject_id: str,
    object_id: str,
    relation_key: str,
) -> tuple[str, str]:
    """Ordem canônica para relações simétricas/não direcionadas — evita duplicação."""
    if is_order_insensitive(relation_key) and subject_id > object_id:
        return object_id, subject_id
    return subject_id, object_id


def canonicalize_relation_assertion(
    subject_id: str,
    object_id: str,
    relation_key: str,
) -> tuple[str, str, str]:
    """Stored key + endpoints. Inverse lemmas swap; undirected/symmetric sort ids."""
    stored, inverted = stored_relation_query(relation_key)
    if inverted:
        subject_id, object_id = object_id, subject_id
    from_id, to_id = canonical_endpoints(subject_id, object_id, stored)
    return from_id, to_id, stored
