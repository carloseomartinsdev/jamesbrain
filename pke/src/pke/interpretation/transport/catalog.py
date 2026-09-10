"""Catálogo de keys permitidas por kind — derivado do Registry, sem ontologia paralela."""

from __future__ import annotations

from pke.domain.ontology import ConceptKind
from pke.ontology.registry import OntologyRegistry


class ConceptCatalog:
    entity_types: set[str] = set()
    event_types: set[str] = set()
    actions: set[str] = set()
    attributes: set[str] = set()
    domains: set[str] = set()
    state_dimensions: set[str] = set()
    state_values: set[str] = set()
    relation_types: set[str] = set()
    roles: set[str] = set()

    @classmethod
    def load(cls, registry: OntologyRegistry) -> None:
        cls.entity_types = {
            c.key for c in registry.concepts() if c.kind is ConceptKind.ENTITY_TYPE
        }
        cls.event_types = {
            c.key for c in registry.concepts() if c.kind is ConceptKind.EVENT_TYPE
        }
        cls.state_dimensions = {
            c.key for c in registry.concepts() if c.kind is ConceptKind.STATE_DIMENSION
        }
        cls.state_values = {
            c.key for c in registry.concepts() if c.kind is ConceptKind.STATE_VALUE
        }
        cls.relation_types = {
            c.key for c in registry.concepts() if c.kind is ConceptKind.RELATION_TYPE
        }
        cls.actions = {c.key for c in registry.concepts() if c.kind is ConceptKind.ACTION}
        cls.attributes = {
            c.key for c in registry.concepts() if c.kind is ConceptKind.ATTRIBUTE
        }
        cls.domains = {c.key for c in registry.concepts() if c.kind is ConceptKind.DOMAIN}
        cls.roles = {c.key for c in registry.concepts() if c.kind is ConceptKind.ROLE}

    @classmethod
    def load_from_view(cls, view: object) -> None:
        kind_map = {
            "entity_type": "entity_types",
            "event_type": "event_types",
            "state_dimension": "state_dimensions",
            "state_value": "state_values",
            "relation_type": "relation_types",
            "action": "actions",
            "attribute": "attributes",
            "domain": "domains",
            "role": "roles",
        }
        buckets = {name: set() for name in kind_map.values()}
        for item in view.concepts:  # type: ignore[attr-defined]
            bucket = kind_map.get(item.kind)
            if bucket:
                buckets[bucket].add(item.key)
        cls.entity_types = buckets["entity_types"]
        cls.event_types = buckets["event_types"]
        cls.state_dimensions = buckets["state_dimensions"]
        cls.state_values = buckets["state_values"]
        cls.relation_types = buckets["relation_types"]
        cls.actions = buckets["actions"]
        cls.attributes = buckets["attributes"]
        cls.domains = buckets["domains"]
        cls.roles = buckets["roles"]
