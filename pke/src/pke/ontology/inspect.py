"""Catálogo inspecionável: CORE + treinado + learned do runtime."""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from pke.domain.ontology import ConceptScope, OntologyConcept
from pke.interpretation.semantic.aliases import SEMANTIC_ALIASES, normalize_expression
from pke.interpretation.semantic_hints import SEMANTIC_HINTS
from pke.ontology.learned import is_learned_relation_key
from pke.ontology.registry import OntologyRegistry
from pke.ontology.trained import is_trained_extended_key, load_trained_catalog, trained_hint

SourceName = Literal["core", "trained", "learned", "extended"]


def _alias_owner(alias) -> str | None:
    return (
        alias.canonical_key
        or alias.action_key
        or alias.value_key
        or alias.event_type_key
        or alias.attribute_key
        or alias.dimension_key
    )


def _lemma_map() -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = {}
    for alias in SEMANTIC_ALIASES:
        owner = _alias_owner(alias)
        if not owner:
            continue
        bucket = grouped.setdefault(owner, set())
        bucket.update(alias.expressions)
    for item in load_trained_catalog().concepts:
        bucket = grouped.setdefault(item.key, set())
        for raw in item.lemmas:
            bucket.add(normalize_expression(raw))
    return {key: sorted(values) for key, values in grouped.items()}


def _source_of(concept: OntologyConcept) -> SourceName:
    if is_learned_relation_key(concept.key):
        return "learned"
    if concept.scope is ConceptScope.CORE:
        return "core"
    if is_trained_extended_key(concept.key):
        return "trained"
    return "extended"


def inspect_catalog(ontology: OntologyRegistry) -> dict[str, Any]:
    lemmas = _lemma_map()
    trained = load_trained_catalog().by_key()
    concepts: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for concept in ontology.concepts():
        source = _source_of(concept)
        counts[source] += 1
        entry = trained.get(concept.key)
        label = concept.presentation.label if concept.presentation else None
        meaning = None
        if entry is not None:
            meaning = entry.meaning
            label = label or entry.label
        meaning = meaning or trained_hint(concept.key) or SEMANTIC_HINTS.get(concept.key)
        concepts.append(
            {
                "key": concept.key,
                "kind": concept.kind.value,
                "scope": concept.scope.value,
                "source": source,
                "label": label,
                "meaning": meaning,
                "lemmas": lemmas.get(concept.key, []),
                "extends_core": bool(entry and entry.extends_core),
            }
        )
    kind_order = {
        "entity_type": 0,
        "relation_type": 1,
        "action": 2,
        "event_type": 3,
        "state_dimension": 4,
        "state_value": 5,
        "attribute": 6,
        "domain": 7,
        "role": 8,
    }
    source_order = {"core": 0, "trained": 1, "learned": 2, "extended": 3}
    concepts.sort(
        key=lambda item: (
            source_order.get(item["source"], 9),
            kind_order.get(item["kind"], 9),
            item["key"],
        )
    )
    return {
        "core_schema_version": ontology.core_schema_version,
        "counts": {
            "total": len(concepts),
            "core": counts["core"],
            "trained": counts["trained"],
            "learned": counts["learned"],
            "extended": counts["extended"],
        },
        "concepts": concepts,
    }
