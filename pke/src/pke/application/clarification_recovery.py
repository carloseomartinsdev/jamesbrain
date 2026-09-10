"""Bounded clarification recovery — I12.13 / I12.14.

CLARIFICATION_RECOVERY_AUTHORITY = ClarificationRecoveryService
CLARIFICATION_RECOVERY_RESUME_STAGE = resolve_proposal → execution_readiness → ingest_from_ir

Does not call Interpreter.interpret.
Does not reinterpret original raw utterance.
Slot registry routes to specialized handlers — not a generic semantic filler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pke.application.ingest import IngestService
from pke.application.pending_operation import (
    MAX_CLARIFICATION_ROUNDS_PER_PENDING_OPERATION,
    PendingOperationStatus,
    PendingSemanticOperation,
    SUPPORTED_DIMENSION_SLOTS,
    SUPPORTED_ENTITY_SLOTS,
    SUPPORTED_VALUE_SLOTS,
)
from pke.application.results import IngestResult, IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation.models import EntityMention, IngestIR
from pke.interpretation.semantic.aliases import resolve_state_value_key_from_answer
from pke.interpretation.semantic.attribute_resolution import (
    resolve_attribute_dimension_key_from_answer,
)
from pke.interpretation.semantic.capability_strategy import (
    CapabilityOutcome,
    ClarificationRequest,
    apply_clarification_evidence,
    decide_capability,
)
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.measurement_resolution import (
    resolve_measurement_dimension_key_from_answer,
)
from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.router import collect_assertions
from pke.resolution.context import PersonalContext, ResolutionContext, ResolutionPurpose
from pke.resolution.entities import EntityResolver, ResolutionStatus
from pke.resolution.lookup import EntityLookup

_TEMPORAL_ONLY = re.compile(
    r"^(ontem|hoje|amanh[aã]|foi\s+ontem|foi\s+hoje|agora|mais\s+tarde|"
    r"de\s+manh[aã]|à\s*noite|as?\s+\d+|hrs?\.?)$",
    re.IGNORECASE,
)


class RecoveryStatus(StrEnum):
    RESOLVED_COMMITTED = "resolved_committed"
    REMAINS_UNRESOLVED = "remains_unresolved"
    UNSUPPORTED_SLOT = "unsupported_slot"
    REJECTED = "rejected"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    CLOSED = "closed"
    INVALID_ANSWER = "invalid_answer"
    ALREADY_RESOLVED = "already_resolved"


@dataclass
class RecoveryTrace:
    """Safety instrumentation for tests — not a second authority."""

    interpreter_called: bool = False
    original_raw_reinterpreted: bool = False
    provider_calls: int = 0
    non_target_slot_mutated: bool = False
    unrelated_primitive_added: bool = False
    unrelated_primitive_removed: bool = False
    missing_information_invented: bool = False
    wrong_dimension_accepted: bool = False
    wrong_value_type_accepted: bool = False
    invalid_correction_target_accepted: bool = False
    duplicate_target_commit: bool = False
    duplicate_sibling_commit: bool = False
    unrelated_mutation: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class ClarificationRecoveryResult:
    status: RecoveryStatus
    ingest: IngestResult | None = None
    pending: PendingSemanticOperation | None = None
    filled_proposal: SemanticProposal | None = None
    trace: RecoveryTrace = field(default_factory=RecoveryTrace)
    message: str = ""


def _primitive_kind(name: str) -> PrimitiveKind:
    try:
        return PrimitiveKind(name)
    except ValueError:
        return PrimitiveKind.UNKNOWN


def _entity_surface(answer: str) -> str | None:
    text = " ".join((answer or "").strip().split())
    if not text:
        return None
    head = text.split(",")[0].strip()
    if _TEMPORAL_ONLY.match(head) or _TEMPORAL_ONLY.match(text):
        return None
    lowered = head
    for prefix in ("o ", "a ", "os ", "as ", "um ", "uma "):
        if lowered.casefold().startswith(prefix):
            lowered = lowered[len(prefix) :]
            break
    if len(lowered.strip()) < 2:
        return None
    return lowered.strip()


def _assertion_fingerprint(proposal: SemanticProposal) -> frozenset[str]:
    return frozenset(f.primitive.value for f in collect_assertions(proposal))


def _slot_snapshot(proposal: SemanticProposal) -> dict[str, Any]:
    return {
        "subject": proposal.subject.model_dump() if proposal.subject else None,
        "object": proposal.object.model_dump() if proposal.object else None,
        "measurable_dimension_key": proposal.measurable_dimension_key,
        "measurement_numeric_value": proposal.measurement_numeric_value,
        "measurement_unit": proposal.measurement_unit,
        "action_expression": proposal.action_expression,
        "relation_expression": proposal.relation_expression,
        "state_expression": proposal.state_expression,
        "attribute_expression": proposal.attribute_expression,
        "event_expression": proposal.event_expression,
        "measurement_expression": proposal.measurement_expression,
        "utterance_kind": proposal.utterance_kind,
        "primitive_hint": proposal.primitive_hint,
        "measurement_semantics": proposal.measurement_semantics,
        "change_semantics": proposal.change_semantics,
        "link_semantics": proposal.link_semantics,
        "condition_semantics": proposal.condition_semantics,
        "stable_property_semantics": proposal.stable_property_semantics,
        "raw_input": proposal.raw_input,
    }


class ClarificationRecoveryService:
    """Canonical write-path clarification recovery authority (I12.13 / I12.14)."""

    def __init__(
        self,
        ingest: IngestService,
        *,
        entity_resolver: EntityResolver | None = None,
        entity_lookup: EntityLookup | None = None,
    ) -> None:
        self._ingest = ingest
        self._entity_resolver = entity_resolver
        self._entity_lookup = entity_lookup

    def recover(
        self,
        pending: PendingSemanticOperation,
        answer_text: str,
        user: UserContext,
        session: SessionContext,
        *,
        replay_allowed: bool = True,
    ) -> ClarificationRecoveryResult:
        trace = RecoveryTrace()
        if session.user_id != user.user_id:
            trace.notes.append("user_isolation")
            return ClarificationRecoveryResult(
                status=RecoveryStatus.REJECTED,
                pending=pending,
                trace=trace,
                message="user_isolation",
            )

        if pending.status in {
            PendingOperationStatus.RESOLVED,
            PendingOperationStatus.CANCELLED,
        }:
            if (
                replay_allowed
                and pending.status is PendingOperationStatus.RESOLVED
                and pending.answer_text
                and pending.answer_text.strip() == answer_text.strip()
            ):
                return ClarificationRecoveryResult(
                    status=RecoveryStatus.IDEMPOTENT_REPLAY,
                    pending=pending,
                    trace=trace,
                    message="idempotent_replay",
                )
            return ClarificationRecoveryResult(
                status=RecoveryStatus.CLOSED,
                pending=pending,
                trace=trace,
                message="clarification_closed",
            )

        if pending.rounds_used >= MAX_CLARIFICATION_ROUNDS_PER_PENDING_OPERATION:
            return ClarificationRecoveryResult(
                status=RecoveryStatus.CLOSED,
                pending=pending,
                trace=trace,
                message="clarification_budget_exhausted",
            )

        if not pending.is_supported():
            return ClarificationRecoveryResult(
                status=RecoveryStatus.UNSUPPORTED_SLOT,
                pending=pending,
                trace=trace,
                message="RECOVERY_UNSUPPORTED_SLOT",
            )

        kind = pending.expected_answer_kind
        if kind == "entity_reference":
            return self._recover_entity_reference(pending, answer_text, user, session, trace)
        if kind == "dimension":
            return self._recover_dimension(pending, answer_text, user, session, trace)
        if kind == "value":
            return self._recover_value(pending, answer_text, user, session, trace)
        return ClarificationRecoveryResult(
            status=RecoveryStatus.UNSUPPORTED_SLOT,
            pending=pending,
            trace=trace,
            message="RECOVERY_UNSUPPORTED_SLOT",
        )

    def _recover_entity_reference(
        self,
        pending: PendingSemanticOperation,
        answer_text: str,
        user: UserContext,
        session: SessionContext,
        trace: RecoveryTrace,
    ) -> ClarificationRecoveryResult:
        if pending.missing_slot not in SUPPORTED_ENTITY_SLOTS:
            return ClarificationRecoveryResult(
                status=RecoveryStatus.UNSUPPORTED_SLOT,
                pending=pending,
                trace=trace,
                message="RECOVERY_UNSUPPORTED_SLOT",
            )
        surface = _entity_surface(answer_text)
        if surface is None:
            return ClarificationRecoveryResult(
                status=RecoveryStatus.REMAINS_UNRESOLVED,
                pending=pending,
                trace=trace,
                message="answer_not_entity_reference",
            )
        if self._entity_resolver is not None and self._entity_lookup is not None:
            if self._check_ambiguous(surface, user) is True:
                return ClarificationRecoveryResult(
                    status=RecoveryStatus.REMAINS_UNRESOLVED,
                    pending=pending,
                    trace=trace,
                    message="entity_ambiguous",
                )
        request = ClarificationRequest(
            primitive=_primitive_kind(pending.primitive),
            missing_slot=pending.missing_slot,
            expected_answer_kind="entity_reference",
            reason=pending.reason,
            question_key=pending.question_key,
            information_value="high",
        )
        original = SemanticProposal.model_validate(pending.proposal_dump)
        filled = apply_clarification_evidence(original, request, entity_text=surface)
        return self._finalize(pending, answer_text, user, session, original, filled, trace)

    def _recover_dimension(
        self,
        pending: PendingSemanticOperation,
        answer_text: str,
        user: UserContext,
        session: SessionContext,
        trace: RecoveryTrace,
    ) -> ClarificationRecoveryResult:
        if pending.missing_slot not in SUPPORTED_DIMENSION_SLOTS:
            return ClarificationRecoveryResult(
                status=RecoveryStatus.UNSUPPORTED_SLOT,
                pending=pending,
                trace=trace,
                message="RECOVERY_UNSUPPORTED_SLOT",
            )
        original = SemanticProposal.model_validate(pending.proposal_dump)
        slot = pending.missing_slot
        if slot == "measurement_dimension":
            if original.measurable_dimension_key:
                return ClarificationRecoveryResult(
                    status=RecoveryStatus.ALREADY_RESOLVED,
                    pending=pending,
                    trace=trace,
                    message="measurement_dimension_already_present",
                )
            dim = resolve_measurement_dimension_key_from_answer(answer_text)
            if dim is None:
                return ClarificationRecoveryResult(
                    status=RecoveryStatus.REMAINS_UNRESOLVED,
                    pending=self._fail_round(pending, answer_text),
                    trace=trace,
                    message="measurement_dimension_unresolved",
                )
            attr_hit = resolve_attribute_dimension_key_from_answer(answer_text)
            if attr_hit in {"color", "model_year"} and dim not in {"weight", "height"}:
                trace.wrong_dimension_accepted = True
                return ClarificationRecoveryResult(
                    status=RecoveryStatus.INVALID_ANSWER,
                    pending=self._fail_round(pending, answer_text),
                    trace=trace,
                    message="wrong_dimension_family",
                )
        else:
            from pke.interpretation.semantic.attribute_resolution import (
                resolve_attribute_dimension_key,
                resolve_attribute_value,
            )

            if resolve_attribute_value(original) is not None or resolve_attribute_dimension_key(
                original
            ):
                return ClarificationRecoveryResult(
                    status=RecoveryStatus.ALREADY_RESOLVED,
                    pending=pending,
                    trace=trace,
                    message="attribute_dimension_already_present",
                )
            meas_hit = resolve_measurement_dimension_key_from_answer(answer_text)
            dim = resolve_attribute_dimension_key_from_answer(answer_text)
            if meas_hit in {"temperature", "balance", "pressure", "volume", "distance"} and (
                dim is None or dim not in {"weight", "height", "area", "capacity"}
            ):
                trace.wrong_dimension_accepted = True
                return ClarificationRecoveryResult(
                    status=RecoveryStatus.INVALID_ANSWER,
                    pending=self._fail_round(pending, answer_text),
                    trace=trace,
                    message="wrong_dimension_family",
                )
            if dim is None:
                return ClarificationRecoveryResult(
                    status=RecoveryStatus.REMAINS_UNRESOLVED,
                    pending=self._fail_round(pending, answer_text),
                    trace=trace,
                    message="attribute_dimension_unresolved",
                )
            # Prefer answer surface token (alias) so attribute_resolution stays authority.
            answer_token = " ".join((answer_text or "").strip().split()).split(",")[0].strip()
            dim = answer_token or dim

        request = ClarificationRequest(
            primitive=_primitive_kind(pending.primitive),
            missing_slot=slot,
            expected_answer_kind="dimension",
            reason=pending.reason,
            question_key=pending.question_key,
            information_value="high",
        )
        filled = apply_clarification_evidence(original, request, dimension_key=dim)
        return self._finalize(pending, answer_text, user, session, original, filled, trace)

    def _recover_value(
        self,
        pending: PendingSemanticOperation,
        answer_text: str,
        user: UserContext,
        session: SessionContext,
        trace: RecoveryTrace,
    ) -> ClarificationRecoveryResult:
        if pending.missing_slot not in SUPPORTED_VALUE_SLOTS:
            return ClarificationRecoveryResult(
                status=RecoveryStatus.UNSUPPORTED_SLOT,
                pending=pending,
                trace=trace,
                message="RECOVERY_UNSUPPORTED_SLOT",
            )
        original = SemanticProposal.model_validate(pending.proposal_dump)
        if pending.missing_slot != "state_value":
            return ClarificationRecoveryResult(
                status=RecoveryStatus.UNSUPPORTED_SLOT,
                pending=pending,
                trace=trace,
                message="RECOVERY_UNSUPPORTED_SLOT",
            )
        if not original.condition_semantics:
            return ClarificationRecoveryResult(
                status=RecoveryStatus.REMAINS_UNRESOLVED,
                pending=self._fail_round(pending, answer_text),
                trace=trace,
                message="state_value_requires_condition_semantics",
            )
        value_key = resolve_state_value_key_from_answer(answer_text)
        if value_key is None:
            return ClarificationRecoveryResult(
                status=RecoveryStatus.REMAINS_UNRESOLVED,
                pending=self._fail_round(pending, answer_text),
                trace=trace,
                message="state_value_unresolved",
            )
        surface = " ".join((answer_text or "").strip().split()).split(",")[0].strip()
        request = ClarificationRequest(
            primitive=_primitive_kind(pending.primitive),
            missing_slot="state_value",
            expected_answer_kind="value",
            reason=pending.reason,
            question_key=pending.question_key,
            information_value="medium",
        )
        filled = apply_clarification_evidence(original, request, value=surface)
        return self._finalize(pending, answer_text, user, session, original, filled, trace)

    def _finalize(
        self,
        pending: PendingSemanticOperation,
        answer_text: str,
        user: UserContext,
        session: SessionContext,
        original: SemanticProposal,
        filled: SemanticProposal,
        trace: RecoveryTrace,
    ) -> ClarificationRecoveryResult:
        before_slots = _slot_snapshot(original)
        before_prims = _assertion_fingerprint(original)
        after_slots = _slot_snapshot(filled)
        after_prims = _assertion_fingerprint(filled)
        target_keys = self._mutable_keys_for_slot(pending.missing_slot)
        for key, before_val in before_slots.items():
            if key in target_keys or key == "raw_input":
                continue
            if after_slots.get(key) != before_val:
                trace.non_target_slot_mutated = True
                trace.unrelated_mutation = True
        if after_prims - before_prims:
            trace.unrelated_primitive_added = True
            trace.unrelated_mutation = True
        if before_prims - after_prims:
            trace.unrelated_primitive_removed = True
            trace.unrelated_mutation = True
        if filled.raw_input != original.raw_input:
            trace.original_raw_reinterpreted = True

        if trace.non_target_slot_mutated or trace.unrelated_primitive_added:
            return ClarificationRecoveryResult(
                status=RecoveryStatus.REJECTED,
                pending=pending,
                filled_proposal=filled,
                trace=trace,
                message="unsafe_mutation",
            )

        readiness = assess_execution_readiness(resolve_proposal(filled))
        decision = decide_capability(readiness)
        if decision.outcome not in {
            CapabilityOutcome.AUTO_EXECUTE,
            CapabilityOutcome.PARTIAL_EXECUTE,
        }:
            return ClarificationRecoveryResult(
                status=RecoveryStatus.REMAINS_UNRESOLVED,
                pending=self._fail_round(pending, answer_text),
                filled_proposal=filled,
                trace=trace,
                message=f"still_{decision.outcome.value}",
            )

        outcome = proposal_to_canonical_ir(filled)
        if outcome.ir is None or not isinstance(outcome.ir, IngestIR):
            return ClarificationRecoveryResult(
                status=RecoveryStatus.REMAINS_UNRESOLVED,
                pending=self._fail_round(pending, answer_text),
                filled_proposal=filled,
                trace=trace,
                message="no_materializable_ir",
            )

        ir = outcome.ir.model_copy(update={"raw_input": answer_text.strip()})
        ingest_result = self._ingest.ingest_from_ir(ir, user, session)

        if ingest_result.status is not IngestStatus.COMMITTED:
            return ClarificationRecoveryResult(
                status=RecoveryStatus.REMAINS_UNRESOLVED,
                pending=self._fail_round(pending, answer_text),
                filled_proposal=filled,
                ingest=ingest_result,
                trace=trace,
                message=f"ingest_{ingest_result.status.value}",
            )

        mat = ingest_result.materialization
        if mat is not None:
            for eid in mat.event_ids:
                if eid in pending.committed_event_ids:
                    trace.duplicate_sibling_commit = True
            for mid in mat.measurement_ids:
                if mid in pending.committed_measurement_ids:
                    trace.duplicate_target_commit = True
            for sid in getattr(mat, "state_ids", []) or []:
                if sid in pending.committed_state_ids:
                    trace.duplicate_target_commit = True
            for aid in getattr(mat, "attribute_ids", []) or []:
                if aid in pending.committed_attribute_ids:
                    trace.duplicate_target_commit = True

        resolved = pending.model_copy(
            update={
                "status": PendingOperationStatus.RESOLVED,
                "rounds_used": pending.rounds_used + 1,
                "answer_text": answer_text.strip(),
                "committed_measurement_ids": list(
                    {
                        *pending.committed_measurement_ids,
                        *(mat.measurement_ids if mat else []),
                    }
                ),
                "committed_event_ids": list(
                    {*pending.committed_event_ids, *(mat.event_ids if mat else [])}
                ),
                "committed_state_ids": list(
                    {
                        *pending.committed_state_ids,
                        *(getattr(mat, "state_ids", []) if mat else []),
                    }
                ),
                "committed_attribute_ids": list(
                    {
                        *pending.committed_attribute_ids,
                        *(getattr(mat, "attribute_ids", []) if mat else []),
                    }
                ),
            }
        )
        return ClarificationRecoveryResult(
            status=RecoveryStatus.RESOLVED_COMMITTED,
            pending=resolved,
            filled_proposal=filled,
            ingest=ingest_result,
            trace=trace,
            message="recovered",
        )

    @staticmethod
    def _fail_round(
        pending: PendingSemanticOperation, answer_text: str
    ) -> PendingSemanticOperation:
        return pending.model_copy(
            update={
                "status": PendingOperationStatus.FAILED,
                "rounds_used": pending.rounds_used + 1,
                "answer_text": answer_text.strip(),
            }
        )

    def _check_ambiguous(self, surface: str, user: UserContext) -> bool | None:
        assert self._entity_resolver is not None
        ctx = ResolutionContext(
            user_id=user.user_id,
            purpose=ResolutionPurpose.INGEST,
            personal=PersonalContext(user_id=user.user_id),
        )
        mention = EntityMention(text=surface)
        result = self._entity_resolver.resolve(mention, ctx)
        return result.status is ResolutionStatus.AMBIGUOUS

    @staticmethod
    def _mutable_keys_for_slot(slot: str) -> set[str]:
        if slot in {"measured_entity", "state_entity", "attribute_entity", "relation_subject"}:
            return {"subject"}
        if slot == "relation_object":
            return {"object"}
        if slot == "measurement_dimension":
            return {"measurable_dimension_key"}
        if slot == "attribute_dimension":
            return {"attribute_expression"}
        if slot == "state_dimension":
            return {"state_expression"}
        if slot == "state_value":
            return {"state_expression"}
        if slot == "measurement_value":
            return {"measurement_numeric_value"}
        return set()
