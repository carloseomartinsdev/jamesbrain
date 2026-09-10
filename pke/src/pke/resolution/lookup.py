"""Lookup de entidades do usuário. Contrato para o Storage futuro; v0 é memória."""

from __future__ import annotations

from typing import Protocol

from pke.domain.entities import Entity
from pke.resolution.normalize import normalize_lexical


class EntityLookup(Protocol):
    def get_by_id(self, entity_id: str, user_id: str) -> Entity | None: ...

    def by_canonical_name(self, user_id: str, normalized: str) -> list[Entity]: ...

    def by_alias(self, user_id: str, normalized: str) -> list[Entity]: ...

    def by_type(self, user_id: str, type_id: str) -> list[Entity]: ...

    def all_for_user(self, user_id: str) -> list[Entity]: ...


class InMemoryEntityLookup:
    """Repositório de teste/resolução. add() é setup — o resolver não chama."""

    def __init__(self) -> None:
        self._by_id: dict[str, Entity] = {}

    def __len__(self) -> int:
        return len(self._by_id)

    def add(self, entity: Entity) -> None:
        self._by_id[entity.id] = entity

    def get_by_id(self, entity_id: str, user_id: str) -> Entity | None:
        entity = self._by_id.get(entity_id)
        if entity is None or entity.user_id != user_id:
            return None
        return entity

    def all_for_user(self, user_id: str) -> list[Entity]:
        return [e for e in self._by_id.values() if e.user_id == user_id]

    def by_canonical_name(self, user_id: str, normalized: str) -> list[Entity]:
        return [
            e
            for e in self.all_for_user(user_id)
            if normalize_lexical(e.canonical_name) == normalized
        ]

    def by_alias(self, user_id: str, normalized: str) -> list[Entity]:
        return [
            e
            for e in self.all_for_user(user_id)
            if any(normalize_lexical(alias) == normalized for alias in e.aliases)
        ]

    def by_type(self, user_id: str, type_id: str) -> list[Entity]:
        return [e for e in self.all_for_user(user_id) if e.type_id == type_id]
