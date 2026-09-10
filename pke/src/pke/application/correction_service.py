"""CorrectionService — atomic RETRACT / REPLACE orchestration."""

from __future__ import annotations

import datetime as dt

from pke.application.clock import Clock
from pke.application.knowledge_reference import KnowledgeReferenceResolver
from pke.domain.corrections import (
    AssertionEffectiveness,
    Correction,
    CorrectionOperation,
    KnowledgePrimitiveKind,
    KnowledgeReference,
)
from pke.domain.ids import new_ulid
from pke.persist.contracts import UnitOfWork
from pke.persist.errors import StorageIntegrityError
from pke.query.effectiveness import AssertionEffectivenessResolver


class CorrectionRejected(StorageIntegrityError):
    """Correction cannot commit under bounded v10 policy."""


class CorrectionService:
    """Owns correction transaction semantics. Repositories remain retrieval/persist only."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def retract(
        self,
        uow: UnitOfWork,
        *,
        user_id: str,
        target_kind: KnowledgePrimitiveKind | str,
        target_id: str,
        raw_input_id: str | None = None,
        source_id: str | None = None,
        commit: bool = True,
    ) -> Correction:
        target = KnowledgeReferenceResolver(uow).resolve(user_id, target_kind, target_id)
        self._assert_effective(uow, target)
        self._assert_raw_source(uow, user_id, raw_input_id, source_id)
        correction = Correction(
            id=new_ulid(),
            user_id=user_id,
            operation=CorrectionOperation.RETRACT,
            target=target,
            replacement=None,
            raw_input_id=raw_input_id,
            source_id=source_id,
            recorded_at=self._now(),
        )
        uow.corrections.add(correction)
        if commit:
            uow.commit()
        return correction

    def replace(
        self,
        uow: UnitOfWork,
        *,
        user_id: str,
        target_kind: KnowledgePrimitiveKind | str,
        target_id: str,
        replacement_kind: KnowledgePrimitiveKind | str,
        replacement_id: str,
        raw_input_id: str | None = None,
        source_id: str | None = None,
        commit: bool = True,
    ) -> Correction:
        resolver = KnowledgeReferenceResolver(uow)
        target = resolver.resolve(user_id, target_kind, target_id)
        replacement = resolver.resolve(user_id, replacement_kind, replacement_id)
        if target.identity_key() == replacement.identity_key():
            raise CorrectionRejected("CORRECTION_SELF_REPLACEMENT")
        self._assert_effective(uow, target)
        self._assert_raw_source(uow, user_id, raw_input_id, source_id)
        correction = Correction(
            id=new_ulid(),
            user_id=user_id,
            operation=CorrectionOperation.REPLACE,
            target=target,
            replacement=replacement,
            raw_input_id=raw_input_id,
            source_id=source_id,
            recorded_at=self._now(),
        )
        uow.corrections.add(correction)
        if commit:
            uow.commit()
        return correction

    def _now(self) -> dt.datetime:
        return self._clock.now()

    def _assert_effective(self, uow: UnitOfWork, target: KnowledgeReference) -> None:
        existing = uow.corrections.find_by_target(
            target.user_id, target.kind, target.assertion_id
        )
        if existing is not None:
            raise CorrectionRejected("CORRECTION_INEFFECTIVE_TARGET_RECORRECTED")
        corrections = uow.corrections.for_user(target.user_id)
        status = AssertionEffectivenessResolver.from_corrections(corrections).resolve(target)
        if status is AssertionEffectiveness.UNKNOWN:
            raise CorrectionRejected("CORRECTION_LEDGER_ORPHAN_REFERENCE")
        if status is not AssertionEffectiveness.EFFECTIVE:
            raise CorrectionRejected("target assertion is not EFFECTIVE")

    def _assert_raw_source(
        self,
        uow: UnitOfWork,
        user_id: str,
        raw_input_id: str | None,
        source_id: str | None,
    ) -> None:
        if raw_input_id is not None:
            raw = uow.raw_inputs.get(user_id, raw_input_id)
            if raw is None:
                raise CorrectionRejected("raw_input missing or cross-user")
        if source_id is not None:
            src = uow.sources.get(user_id, source_id)
            if src is None:
                raise CorrectionRejected("source missing or cross-user")
