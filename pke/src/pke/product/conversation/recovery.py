"""Product operational recovery — non-semantic reconciliation authority.

RECOVERY_AUTHORITY = ProductRecoveryService
Does not reinterpret user text. Does not decide primitives/query truth.
Does not invoke Engine for ambiguous completion states.

NO DISTRIBUTED ACID CLAIM — Product DB ≠ Knowledge DB.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pke.product.api.v1.dtos import (
    ApiMessage,
    ApiMessageResponse,
    ApiMessageRole,
    ApiMessageStatus,
    ApiOperation,
    ApiOperationKind,
    ApiOperationOutcome,
    ApiResponseType,
)
from pke.product.conversation.idempotency import (
    IdempotencyClaimResult,
    IdempotencyRecord,
    IdempotencyStatus,
)
from pke.product.conversation.store import ProductStore

_LOG = logging.getLogger("pke.product.recovery")

DEFAULT_STALE_SECONDS = 120


class RecoveryAction(StrEnum):
    REPLAY_PRODUCT_RESULT = "replay_product_result"
    SAFE_ENGINE_RETRY = "safe_engine_retry"
    MARK_REQUIRES_RECONCILIATION = "mark_requires_reconciliation"
    IN_FLIGHT = "in_flight"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class BeginOutcome:
    action: RecoveryAction
    response: ApiMessageResponse | None = None
    record: IdempotencyRecord | None = None


class OperationRequiresReconciliation(Exception):
    """Ambiguous completion — Engine may have committed; Product has no durable result."""


class ProductRecoveryService:
    """Operational reconciliation only. Never a semantic authority."""

    def __init__(
        self,
        store: ProductStore,
        *,
        stale_after_seconds: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        if stale_after_seconds is None:
            raw = os.environ.get("PKE_IDEMPOTENCY_STALE_SECONDS", "").strip()
            stale_after_seconds = int(raw) if raw else DEFAULT_STALE_SECONDS
        self._stale_after = max(0, int(stale_after_seconds))
        self._clock = clock or (lambda: datetime.now(UTC))

    def ensure_product_store(self) -> None:
        """Fail closed before semantic execution if Product persistence is unavailable."""
        self._store.ping()

    def begin_or_replay(
        self,
        user_id: str,
        client_request_id: str,
        *,
        request_fingerprint: str,
        conversation_id: str | None = None,
    ) -> BeginOutcome:
        result, record = self._store.claim_idempotent(
            user_id,
            client_request_id,
            request_fingerprint=request_fingerprint,
            conversation_id=conversation_id,
        )
        if result is IdempotencyClaimResult.REPLAY and record and record.response_json:
            _LOG.info(
                "recovery_event=replayed_completed_result user_id=%s client_request_id=%s",
                user_id,
                client_request_id,
            )
            return BeginOutcome(
                RecoveryAction.REPLAY_PRODUCT_RESULT,
                response=ApiMessageResponse.model_validate(record.response_json),
                record=record,
            )
        if result is IdempotencyClaimResult.CONFLICT:
            _LOG.info(
                "recovery_event=fingerprint_conflict user_id=%s client_request_id=%s",
                user_id,
                client_request_id,
            )
            return BeginOutcome(RecoveryAction.CONFLICT, record=record)
        if result is IdempotencyClaimResult.RECOVERY_REQUIRED:
            _LOG.info(
                "recovery_event=retry_blocked_uncertain_completion user_id=%s "
                "client_request_id=%s",
                user_id,
                client_request_id,
            )
            raise OperationRequiresReconciliation()
        if result is IdempotencyClaimResult.IN_PROGRESS and record is not None:
            if self._is_stale(record):
                return self._reconcile_stale(
                    user_id,
                    client_request_id,
                    record,
                    request_fingerprint=request_fingerprint,
                    conversation_id=conversation_id or record.conversation_id,
                )
            return BeginOutcome(RecoveryAction.IN_FLIGHT, record=record)
        return BeginOutcome(RecoveryAction.SAFE_ENGINE_RETRY, record=record)

    def _reconcile_stale(
        self,
        user_id: str,
        client_request_id: str,
        record: IdempotencyRecord,
        *,
        request_fingerprint: str,
        conversation_id: str | None,
    ) -> BeginOutcome:
        _LOG.info(
            "recovery_event=stale_in_progress_detected user_id=%s client_request_id=%s "
            "status=%s",
            user_id,
            client_request_id,
            record.status,
        )
        # Prefer durable Product evidence — never infer from raw text.
        if record.response_json is not None:
            self._store.complete_idempotent(
                user_id,
                client_request_id,
                record.response_json,
                request_fingerprint=request_fingerprint,
                conversation_id=conversation_id,
            )
            _LOG.info(
                "recovery_event=replayed_completed_result user_id=%s client_request_id=%s",
                user_id,
                client_request_id,
            )
            return BeginOutcome(
                RecoveryAction.REPLAY_PRODUCT_RESULT,
                response=ApiMessageResponse.model_validate(record.response_json),
                record=record,
            )

        messages = self._store.find_messages_by_client_request(user_id, client_request_id)
        assistant = [m for m in messages if m.role is ApiMessageRole.ASSISTANT]
        if assistant:
            response = _response_from_assistant_message(assistant[-1], client_request_id)
            self._store.complete_idempotent(
                user_id,
                client_request_id,
                response.model_dump(mode="json"),
                request_fingerprint=request_fingerprint,
                conversation_id=conversation_id or assistant[-1].conversation_id,
            )
            _LOG.info(
                "recovery_event=recovered_from_assistant_message user_id=%s "
                "client_request_id=%s message_id=%s",
                user_id,
                client_request_id,
                assistant[-1].id,
            )
            return BeginOutcome(
                RecoveryAction.REPLAY_PRODUCT_RESULT,
                response=response,
                record=record,
            )

        # Ambiguous: Engine may have committed after Product claimed in_progress.
        self._store.mark_recovery_required(user_id, client_request_id)
        _LOG.info(
            "recovery_event=marked_recovery_required user_id=%s client_request_id=%s",
            user_id,
            client_request_id,
        )
        raise OperationRequiresReconciliation()

    def _is_stale(self, record: IdempotencyRecord) -> bool:
        stamp = record.updated_at or record.created_at
        if not stamp:
            return True
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            return True
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        age = self._clock() - when
        return age >= timedelta(seconds=self._stale_after)


def _response_from_assistant_message(
    message: ApiMessage, client_request_id: str
) -> ApiMessageResponse:
    try:
        resp_type = ApiResponseType(message.type)
    except ValueError:
        resp_type = ApiResponseType.ANSWER
    status = message.status or ApiMessageStatus.COMPLETED
    operation = message.operation
    if operation is None:
        operation = ApiOperation(
            kind=ApiOperationKind.NONE,
            outcome=ApiOperationOutcome.FAILED,
        )
    return ApiMessageResponse(
        conversation_id=message.conversation_id,
        message_id=message.id,
        type=resp_type,
        status=status,
        text=message.text,
        clarification=message.clarification,
        error=message.error,
        data=message.data,
        operation=operation,
        client_request_id=client_request_id,
    )
