"""Principal Binding service — lazy ensure (E1.1). Persistence lives in persist/."""

from __future__ import annotations

import datetime as dt

from pke.domain.entities import Entity
from pke.domain.ids import new_ulid
from pke.domain.principal import (
    PRINCIPAL_CANONICAL_NAME,
    PRINCIPAL_ENTITY_TYPE_KEY,
    PrincipalBinding,
)
from pke.ontology.seeds import core_concept_id
from pke.persist.contracts import UnitOfWork
from pke.persist.errors import StorageIntegrityError


class PrincipalBindingService:
    """Lazy, idempotent AuthPrincipal → Entity binding (Knowledge-owned)."""

    def __init__(self, ontology_type_id: str | None = None) -> None:
        self._type_id = ontology_type_id or core_concept_id(PRINCIPAL_ENTITY_TYPE_KEY)

    def get_entity_id(self, uow: UnitOfWork, user_id: str) -> str | None:
        binding = uow.principal_bindings.get(user_id)
        return binding.entity_id if binding is not None else None

    def ensure_principal_entity(
        self,
        uow: UnitOfWork,
        user_id: str,
        *,
        now: dt.datetime,
    ) -> str:
        """Return principal Entity id; create Entity+binding once if missing.

        Does not write spoken attributes from the triggering utterance (D-E1-04).
        Requires operational `now` — no wall-clock fallback (Clock authority).
        """
        if not user_id:
            raise ValueError("user_id required for principal binding")
        if now.tzinfo is None:
            raise ValueError("now exige timezone")
        existing = uow.principal_bindings.get(user_id)
        if existing is not None:
            entity = uow.entities.get(user_id, existing.entity_id)
            if entity is None:
                raise StorageIntegrityError("principal binding points to missing entity")
            if entity.id == user_id:
                raise StorageIntegrityError("principal Entity.id must not equal AuthUser.id")
            return existing.entity_id

        entity_id = new_ulid()
        if entity_id == user_id:
            # Astronomically unlikely with ULID; defend invariant explicitly.
            entity_id = new_ulid()
        entity = Entity(
            id=entity_id,
            user_id=user_id,
            type_id=self._type_id,
            canonical_name=PRINCIPAL_CANONICAL_NAME,
            aliases=[],
            created_at=now,
        )
        uow.entities.add(entity)
        binding = PrincipalBinding(
            user_id=user_id,
            entity_id=entity.id,
            created_at=now,
            updated_at=now,
        )
        uow.principal_bindings.put(binding)
        return entity.id
