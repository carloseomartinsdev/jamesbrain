"""Intrinsic entity properties — identity metadata, not Attribute assertions.

Entity stores a single user-facing name field (`canonical_name`). There is no
separate display_name on the knowledge Entity. Product-facing intrinsic query
key is `name` only; id / type_id / aliases are not exposed as attribute queries.
"""

from __future__ import annotations

from pke.domain.attributes import AttributeValueKind
from pke.domain.entities import Entity
from pke.domain.principal import PRINCIPAL_CANONICAL_NAME
from pke.persist.snapshot import UserKnowledgeSnapshot
from pke.query.attribute_resolver import AttributeResolutionStatus
from pke.query.results import AttributeValueItem, QueryPlan, QueryResult, TemporalCompleteness
from pke.query.spec import AggregateKind, AttributeQueryMode, ResolvedQuerySpec

INTRINSIC_ATTRIBUTE_KEYS = frozenset({"name"})
INTRINSIC_NOTE = "intrinsic_entity_property"


def is_intrinsic_dimension(dimension_key: str) -> bool:
    return dimension_key in INTRINSIC_ATTRIBUTE_KEYS


def intrinsic_text(entity: Entity, dimension_key: str) -> str | None:
    if dimension_key == "name":
        text = (entity.canonical_name or "").strip()
        return text or None
    return None


def try_intrinsic_attribute_result(
    spec: ResolvedQuerySpec,
    graph: UserKnowledgeSnapshot,
) -> QueryResult | None:
    """VALUE_LOOKUP of `name` from Entity.canonical_name when the entity is resolved.

    Other attribute modes (proposition, history, snapshot) keep Attribute rows.
    """
    dimension = spec.attribute_dimension_key
    if dimension is None or not is_intrinsic_dimension(dimension):
        return None
    mode = spec.attribute_query_mode or AttributeQueryMode.VALUE_LOOKUP
    if mode is not AttributeQueryMode.VALUE_LOOKUP:
        return None
    if not spec.entity_ids:
        return None

    texts: list[str] = []
    for eid in spec.entity_ids:
        if graph.principal_entity_id is not None and eid == graph.principal_entity_id:
            # Principal display name is Attribute (E1.2), not Entity.canonical_name.
            continue
        entity = graph.entities.get(eid)
        if entity is None:
            continue
        if entity.canonical_name == PRINCIPAL_CANONICAL_NAME:
            continue
        text = intrinsic_text(entity, dimension)
        if text is None:
            continue
        texts.append(text)
    if not texts:
        return None

    unique = list(dict.fromkeys(texts))
    values = [
        AttributeValueItem(
            value_kind=AttributeValueKind.TEXT.value,
            text_value=text,
            support_count=texts.count(text),
            dimension_key=dimension,
        )
        for text in unique
    ]
    status = (
        AttributeResolutionStatus.KNOWN_SINGLE
        if len(unique) == 1
        else AttributeResolutionStatus.KNOWN_MULTIPLE
    )
    plan = QueryPlan(
        sets=["entities"],
        filters={"attribute_dimension_key": dimension, "source": "entity.canonical_name"},
        expanded_event_type_ids=[],
        expanded_action_ids=[],
        version_policy=spec.fact_version_policy,
        aggregation=AggregateKind.NONE,
        ordering=spec.sort,
        hierarchy=spec.hierarchy,
    )
    return QueryResult(
        matched_count=len(texts),
        applied_filters=plan.filters,
        plan=plan,
        temporal_completeness=TemporalCompleteness.COMPLETE,
        attribute_status=status.value,
        attribute_dimension_key=dimension,
        attribute_values=values,
        warnings=[INTRINSIC_NOTE],
    )
