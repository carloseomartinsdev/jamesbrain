"""Consulta determinística. Recupera conhecimento; não completa."""

from pke.persist.snapshot import UserKnowledgeSnapshot
from pke.query.engine import QueryEngine
from pke.query.errors import (
    MultiCurrencyAggregateError,
    QueryError,
    QueryIsolationError,
    QuerySpecError,
)
from pke.query.results import AggregateResult, QueryItem, QueryPlan, QueryResult
from pke.query.spec import (
    AggregateKind,
    EntityAssociation,
    FactVersionPolicy,
    HierarchyMode,
    ResolvedQuerySpec,
    SortKey,
    TimeRange,
)
from pke.query.store import KnowledgeReadStore

__all__ = [
    "AggregateKind",
    "AggregateResult",
    "EntityAssociation",
    "FactVersionPolicy",
    "HierarchyMode",
    "KnowledgeReadStore",
    "MultiCurrencyAggregateError",
    "QueryEngine",
    "QueryError",
    "QueryIsolationError",
    "QueryItem",
    "QueryPlan",
    "QueryResult",
    "QuerySpecError",
    "ResolvedQuerySpec",
    "SortKey",
    "TimeRange",
    "UserKnowledgeSnapshot",
]
