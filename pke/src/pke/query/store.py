"""Projeção de leitura. Independente de SQLAlchemy."""

from __future__ import annotations

from typing import Protocol

from pke.persist.snapshot import UserKnowledgeSnapshot


class KnowledgeReadStore(Protocol):
    def load_user_graph(self, user_id: str) -> UserKnowledgeSnapshot: ...
