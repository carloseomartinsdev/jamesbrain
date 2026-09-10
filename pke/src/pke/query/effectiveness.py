"""AssertionEffectivenessResolver — sole effectiveness authority for ordinary reasoning."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import TypeVar

from pke.domain.corrections import (
    AssertionEffectiveness,
    Correction,
    KnowledgePrimitiveKind,
    KnowledgeReference,
)

T = TypeVar("T")


class AssertionEffectivenessResolver:
    """An assertion is EFFECTIVE iff no committed Correction targets its KnowledgeReference."""

    def __init__(
        self,
        corrections: Sequence[Correction],
        *,
        unknown_keys: frozenset[tuple[str, str, str]] | None = None,
    ) -> None:
        self._incoming: dict[tuple[str, str, str], Correction] = {}
        for corr in corrections:
            self._incoming[corr.target.identity_key()] = corr
        self._unknown = unknown_keys or frozenset()

    @classmethod
    def from_corrections(
        cls,
        corrections: Sequence[Correction],
        *,
        unknown_keys: frozenset[tuple[str, str, str]] | None = None,
    ) -> AssertionEffectivenessResolver:
        return cls(corrections, unknown_keys=unknown_keys)

    def resolve(self, reference: KnowledgeReference) -> AssertionEffectiveness:
        key = reference.identity_key()
        if key in self._unknown:
            return AssertionEffectiveness.UNKNOWN
        if key in self._incoming:
            return AssertionEffectiveness.INEFFECTIVE
        return AssertionEffectiveness.EFFECTIVE

    def resolve_many(
        self, references: Iterable[KnowledgeReference]
    ) -> dict[tuple[str, str, str], AssertionEffectiveness]:
        return {ref.identity_key(): self.resolve(ref) for ref in references}

    def explain(self, reference: KnowledgeReference) -> Correction | None:
        return self._incoming.get(reference.identity_key())


def filter_effective(
    items: Sequence[T],
    *,
    kind: KnowledgePrimitiveKind,
    user_id: str,
    resolver: AssertionEffectivenessResolver,
    id_of: Callable[[T], str] | None = None,
) -> tuple[list[T], list[T]]:
    """Return (effective, unknown). Ineffective excluded from both."""

    def _default_id(item: T) -> str:
        return item.id  # type: ignore[attr-defined]

    get_id = id_of or _default_id
    effective: list[T] = []
    unknown: list[T] = []
    for item in items:
        ref = KnowledgeReference(kind=kind, assertion_id=get_id(item), user_id=user_id)
        status = resolver.resolve(ref)
        if status is AssertionEffectiveness.EFFECTIVE:
            effective.append(item)
        elif status is AssertionEffectiveness.UNKNOWN:
            unknown.append(item)
    return effective, unknown
