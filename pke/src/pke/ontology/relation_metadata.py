"""Metadados conceituais de Relation — inversos/simétricos; não duplicam storage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RelationConceptMetadata:
    meaning: str
    direction: str
    inverse: str | None = None
    symmetric: bool = False
    why_core: str = ""


RELATION_METADATA: dict[str, RelationConceptMetadata] = {
    "relation.employed_by": RelationConceptMetadata(
        meaning="Pessoa empregada por organização",
        direction="person → organization",
        inverse="relation.employs",
        why_core="R1 employment; PEOPLE_001",
    ),
    "relation.resides_at": RelationConceptMetadata(
        meaning="Pessoa reside em local",
        direction="person → place",
        why_core="R2 residence",
    ),
    "relation.owns": RelationConceptMetadata(
        meaning="Pessoa possui bem",
        direction="person → thing",
        inverse="relation.owned_by",
        why_core="R3 ownership — direção canônica person owns thing",
    ),
    "relation.likes": RelationConceptMetadata(
        meaning="Pessoa gosta de entidade ou coisa",
        direction="person → thing",
        why_core="R7 preference / like — not an Attribute dimension",
    ),
    "relation.married_to": RelationConceptMetadata(
        meaning="Casamento entre pessoas",
        direction="person ↔ person",
        symmetric=True,
        why_core="R4 marriage",
    ),
    "relation.parent_of": RelationConceptMetadata(
        meaning="Pessoa é progenitora de outra",
        direction="parent → child",
        inverse="relation.child_of",
        why_core="R5 parent relation",
    ),
    "relation.provider_for": RelationConceptMetadata(
        meaning="Prestador de serviço/profissional para pessoa",
        direction="provider → person",
        inverse="relation.client_of",
        why_core="R6 provider relation",
    ),
}

SYMMETRIC_RELATION_KEYS = frozenset(
    key for key, meta in RELATION_METADATA.items() if meta.symmetric
)


def canonical_endpoints(
    subject_id: str,
    object_id: str,
    relation_key: str,
) -> tuple[str, str]:
    """Ordem canônica para relações simétricas — evita duplicação."""
    if relation_key in SYMMETRIC_RELATION_KEYS and subject_id > object_id:
        return object_id, subject_id
    return subject_id, object_id
