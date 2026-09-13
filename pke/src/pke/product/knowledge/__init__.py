"""Read-only knowledge inspect — projection of persisted snapshot, not interpretation."""

from pke.product.knowledge.inspector import (
    KnowledgeInspector,
    KnowledgeInvalidId,
    KnowledgeNotFound,
)

__all__ = ["KnowledgeInspector", "KnowledgeInvalidId", "KnowledgeNotFound"]
