"""Catálogo conceitual derivado do Registry. Sem ontologia paralela."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from pke.interpretation.semantic_hints import SEMANTIC_HINTS
from pke.ontology.registry import OntologyRegistry


class ConceptCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    kind: str
    parent_key: str | None = None
    label: str | None = None


class InterpreterOntologyView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_schema_version: str
    concepts: list[ConceptCatalogItem]

    @classmethod
    def from_registry(cls, registry: OntologyRegistry) -> InterpreterOntologyView:
        items: list[ConceptCatalogItem] = []
        concepts = registry.concepts()
        by_id = {concept.id: concept for concept in concepts}
        for concept in concepts:
            parent_key = None
            if concept.parent_id and concept.parent_id in by_id:
                parent_key = by_id[concept.parent_id].key
            label = concept.presentation.label if concept.presentation else None
            items.append(
                ConceptCatalogItem(
                    key=concept.key,
                    kind=concept.kind.value,
                    parent_key=parent_key,
                    label=label,
                )
            )
        return cls(core_schema_version=registry.core_schema_version, concepts=items)

    def compact_grouped(self) -> dict[str, dict[str, str]]:
        """Ontologia compacta por kind — keys + dica curta. Identity = key."""
        buckets: dict[str, dict[str, str]] = {
            "entity_types": {},
            "event_types": {},
            "actions": {},
            "attributes": {},
            "domains": {},
            "roles": {},
            "relation_types": {},
        }
        kind_bucket = {
            "entity_type": "entity_types",
            "event_type": "event_types",
            "relation_type": "relation_types",
            "action": "actions",
            "attribute": "attributes",
            "domain": "domains",
            "role": "roles",
        }
        for item in self.concepts:
            bucket = kind_bucket.get(item.kind)
            if bucket is None:
                continue
            hint = SEMANTIC_HINTS.get(item.key)
            if not hint:
                from pke.ontology.trained import trained_hint

                hint = trained_hint(item.key) or item.label or item.key
            buckets[bucket][item.key] = hint
        return buckets
