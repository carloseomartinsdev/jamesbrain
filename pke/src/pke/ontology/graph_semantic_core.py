"""Graph Semantic Core — domain-general primitives over existing PKE kinds.

This is a mapping, not a second engine. Atomic Claims / IngestIR / QueryIR remain
the contract. Domain examples (house, cat, accountant) are fixtures, not branches.

See ADR 0093.
"""

from __future__ import annotations

from enum import StrEnum

from pke.interpretation.semantic.models import PrimitiveKind, SemanticClaimKind


class GraphPrimitive(StrEnum):
    ENTITY = "entity"
    CLASSIFICATION = "classification"
    PROPERTY = "property"
    RELATION = "relation"
    EVENT = "event"
    MEASUREMENT = "measurement"


class GraphCrossCut(StrEnum):
    TEMPORALITY = "temporality"
    CONFIDENCE = "confidence"
    PROVENANCE = "provenance"


# STATE remains a PKE condition primitive; it is not folded into PROPERTY.
_CLAIM_TO_GRAPH: dict[SemanticClaimKind, GraphPrimitive] = {
    SemanticClaimKind.ENTITY: GraphPrimitive.ENTITY,
    SemanticClaimKind.CLASSIFICATION: GraphPrimitive.CLASSIFICATION,
    SemanticClaimKind.ATTRIBUTE: GraphPrimitive.PROPERTY,
    SemanticClaimKind.INTRINSIC_PROPERTY: GraphPrimitive.PROPERTY,
    SemanticClaimKind.RELATION: GraphPrimitive.RELATION,
    SemanticClaimKind.EVENT: GraphPrimitive.EVENT,
    SemanticClaimKind.MEASUREMENT: GraphPrimitive.MEASUREMENT,
}

_ROUTE_TO_GRAPH: dict[PrimitiveKind, GraphPrimitive | None] = {
    PrimitiveKind.EVENT: GraphPrimitive.EVENT,
    PrimitiveKind.RELATION: GraphPrimitive.RELATION,
    PrimitiveKind.ATTRIBUTE: GraphPrimitive.PROPERTY,
    PrimitiveKind.TYPE: GraphPrimitive.CLASSIFICATION,
    PrimitiveKind.MEASUREMENT: GraphPrimitive.MEASUREMENT,
    PrimitiveKind.STATE: None,
    PrimitiveKind.UNKNOWN: None,
}


def graph_primitive_for_claim(kind: SemanticClaimKind) -> GraphPrimitive | None:
    """Map an Atomic Claim onto a Graph Semantic Core primitive."""
    return _CLAIM_TO_GRAPH.get(kind)


def graph_primitive_for_route(kind: PrimitiveKind) -> GraphPrimitive | None:
    """Map router PrimitiveKind onto a Graph Semantic Core primitive."""
    return _ROUTE_TO_GRAPH.get(kind)
