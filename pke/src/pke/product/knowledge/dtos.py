"""DTOs of persisted knowledge for the inspector. No inferred facts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_GRAPH_NODES = 200
MAX_GRAPH_EDGES = 500
MAX_SEARCH_RESULTS = 50
MAX_DEPTH = 3
DEFAULT_DEPTH = 2


class KnowledgeNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["entity", "type"]
    label: str
    type: str | None = None
    type_id: str | None = None
    canonical_name: str | None = None
    visual: str
    role: Literal["principal"] | None = None
    aliases: list[str] = Field(default_factory=list)
    scope: str | None = None
    ontology_kind: str | None = None


class KnowledgeEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    target: str
    type: str
    label: str
    kind: Literal["relation", "classification"]
    is_current: bool | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    confidence: float | None = None
    raw_input_id: str | None = None
    source_kind: str | None = None
    source_id: str | None = None
    created_at: str | None = None
    observed_at: str | None = None


class KnowledgeGraphMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_entity_id: str | None = None
    principal_entity_id: str | None = None
    depth: int
    current_only: bool
    expand_entity_id: str | None = None
    max_nodes: int = MAX_GRAPH_NODES
    max_edges: int = MAX_GRAPH_EDGES
    node_count: int = 0
    edge_count: int = 0


class KnowledgeGraphResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[KnowledgeNode] = Field(default_factory=list)
    edges: list[KnowledgeEdge] = Field(default_factory=list)
    truncated: bool = False
    meta: KnowledgeGraphMeta


class KnowledgeIntrinsic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any


class KnowledgeRelationRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    label: str
    from_id: str
    to_id: str
    from_label: str | None = None
    to_label: str | None = None
    is_current: bool
    valid_from: str | None = None
    valid_to: str | None = None
    confidence: float | None = None
    raw_input_id: str | None = None
    source_kind: str | None = None
    source_id: str | None = None
    created_at: str | None = None
    observed_at: str | None = None


class KnowledgeAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    dimension_key: str
    dimension_concept_id: str | None = None
    dimension_label: str | None = None
    dimension_source: str | None = None
    value: str
    value_kind: str
    unit: str | None = None
    is_current: bool
    valid_from: str | None = None
    valid_to: str | None = None
    confidence: float | None = None
    raw_input_id: str | None = None
    source_kind: str | None = None
    created_at: str | None = None
    observed_at: str | None = None


class KnowledgeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    dimension_key: str
    value_key: str
    is_current: bool
    valid_from: str | None = None
    valid_to: str | None = None
    raw_input_id: str | None = None
    created_at: str | None = None


class KnowledgeMeasurement(BaseModel):
    """Persisted Measurement row. No is_current / valid_to in storage v9."""

    model_config = ConfigDict(extra="forbid")

    id: str
    dimension_key: str
    dimension_concept_id: str | None = None
    numeric_value: str
    unit: str | None = None
    currency_code: str | None = None
    display_value: str
    context_entity_id: str | None = None
    confidence: float | None = None
    raw_input_id: str | None = None
    source_kind: str | None = None
    source_id: str | None = None
    created_at: str | None = None
    observed_at: str | None = None


class KnowledgeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    type_id: str
    action_id: str | None = None
    status: str
    actor_id: str | None = None
    subject_id: str | None = None
    raw_input_id: str | None = None
    created_at: str | None = None


class KnowledgeTypeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    key: str
    scope: str | None = None
    ontology_kind: str | None = None
    source: str | None = None


class KnowledgeEntityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    role: Literal["principal"] | None = None
    type: KnowledgeTypeInfo
    status: str
    created_at: str | None = None
    intrinsic: list[KnowledgeIntrinsic] = Field(default_factory=list)
    relations_outgoing: list[KnowledgeRelationRef] = Field(default_factory=list)
    relations_incoming: list[KnowledgeRelationRef] = Field(default_factory=list)
    attributes: list[KnowledgeAttribute] = Field(default_factory=list)
    measurements: list[KnowledgeMeasurement] = Field(default_factory=list)
    states: list[KnowledgeState] = Field(default_factory=list)
    events: list[KnowledgeEvent] = Field(default_factory=list)
    raw: dict[str, Any]


class KnowledgeSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    canonical_name: str
    label: str
    type: str
    type_id: str
    role: Literal["principal"] | None = None


class KnowledgeSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[KnowledgeSearchHit] = Field(default_factory=list)
    truncated: bool = False
    limit: int = MAX_SEARCH_RESULTS
