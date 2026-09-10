"""Camada ontológica do PKE — registry, não interpretação."""

from pke.ontology.errors import (
    ConceptConflictError,
    ConceptKindError,
    ConceptNotFoundError,
    CoreMutationError,
    OntologyError,
)
from pke.ontology.registry import OntologyRegistry
from pke.ontology.seeds import CORE_SCHEMA_VERSION, CORE_SEEDS, core_concept_id

__all__ = [
    "CORE_SCHEMA_VERSION",
    "CORE_SEEDS",
    "ConceptConflictError",
    "ConceptKindError",
    "ConceptNotFoundError",
    "CoreMutationError",
    "OntologyError",
    "OntologyRegistry",
    "core_concept_id",
]
