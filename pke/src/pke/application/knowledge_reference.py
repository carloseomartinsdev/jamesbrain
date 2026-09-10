"""Canonical KnowledgeReference kind registry + resolver (single mapping authority)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pke.domain.corrections import KnowledgePrimitiveKind, KnowledgeReference
from pke.persist.contracts import UnitOfWork
from pke.persist.errors import StorageIntegrityError

# Sole kind → repository getter mapping. Do not duplicate elsewhere.
_Lookup = Callable[[UnitOfWork, str, str], Any | None]

REFERENCE_KIND_LOOKUP: dict[KnowledgePrimitiveKind, _Lookup] = {
    KnowledgePrimitiveKind.EVENT: lambda uow, uid, aid: uow.events.get(uid, aid),
    KnowledgePrimitiveKind.MEASUREMENT: lambda uow, uid, aid: uow.measurements.get(uid, aid),
    KnowledgePrimitiveKind.RELATION: lambda uow, uid, aid: uow.relations.get(uid, aid),
    KnowledgePrimitiveKind.STATE: lambda uow, uid, aid: uow.states.get(uid, aid),
    KnowledgePrimitiveKind.ATTRIBUTE: lambda uow, uid, aid: uow.attributes.get(uid, aid),
}


class KnowledgeReferenceError(StorageIntegrityError):
    """Invalid typed knowledge reference."""


class KnowledgeReferenceResolver:
    """Validate kind, existence, and user ownership. Never selects by insertion order."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def resolve(
        self,
        user_id: str,
        kind: KnowledgePrimitiveKind | str,
        assertion_id: str,
    ) -> KnowledgeReference:
        try:
            primitive = (
                kind
                if isinstance(kind, KnowledgePrimitiveKind)
                else KnowledgePrimitiveKind(str(kind))
            )
        except ValueError as exc:
            raise KnowledgeReferenceError(f"unsupported knowledge kind: {kind!r}") from exc
        lookup = REFERENCE_KIND_LOOKUP.get(primitive)
        if lookup is None:
            raise KnowledgeReferenceError(f"unsupported knowledge kind: {primitive!r}")
        row = lookup(self._uow, user_id, assertion_id)
        if row is None:
            raise KnowledgeReferenceError(
                f"assertion not found or wrong user: {primitive.value}/{assertion_id}"
            )
        row_user = getattr(row, "user_id", None)
        if row_user is not None and row_user != user_id:
            raise KnowledgeReferenceError("cross-user knowledge reference")
        return KnowledgeReference(
            kind=primitive,
            assertion_id=assertion_id,
            user_id=user_id,
        )
