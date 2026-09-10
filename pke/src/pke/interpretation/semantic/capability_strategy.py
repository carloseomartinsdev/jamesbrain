"""Engine capability strategy — execute / clarify / unsupported / abstain (E1.3).

Single authority for capability *decision* over structured Engine state.
Composes ExecutionReadiness; does not reinterpret raw_input; is not an Interpreter.

CLARIFY only when additional user input can realistically unlock the operation.
UNSUPPORTED when the Engine understands enough but lacks capability.
SAFE_ABSTAIN when unsafe / non-actionable with no useful clarification question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pke.interpretation.semantic.execution_readiness import (
    REASON_AMBIGUOUS_CORRECTION_TARGET,
    REASON_CANONICAL_TYPE_UNRESOLVED_SAFE_PARTIAL,
    REASON_EVENT_IDENTITY_INCOMPLETE,
    REASON_MISSING_ATTRIBUTE_DIMENSION,
    REASON_MISSING_ATTRIBUTE_VALUE,
    REASON_MISSING_ENTITY,
    REASON_MISSING_MEASUREMENT_DIMENSION,
    REASON_MISSING_MEASUREMENT_VALUE,
    REASON_MISSING_RELATION_OBJECT,
    REASON_MISSING_RELATION_SUBJECT,
    REASON_MISSING_STATE_DIMENSION,
    REASON_MISSING_STATE_VALUE,
    REASON_ONTOLOGY_GAP,
    REASON_RELATION_CANONICAL_UNRESOLVED,
    REASON_STATE_CANONICAL_UNRESOLVED,
    REASON_UNSUPPORTED_ATTRIBUTE_DIMENSION,
    REASON_UNSUPPORTED_PRIMITIVE,
    REASON_CLASSIFICATION_NOT_MATERIALIZABLE,
    _UNSUPPORTED_REASONS,
    ExecutionReadiness,
    PrimitiveExecutionStatus,
    ProposalExecutionOutcome,
    question_key_for_reason,
)
from pke.interpretation.semantic.models import (
    PrimitiveKind,
    SemanticEntityMention,
    SemanticProposal,
)

AnswerKind = Literal[
    "entity_reference",
    "dimension",
    "value",
    "correction_target",
    "none",
]

InformationValue = Literal["high", "medium", "low", "none"]


class CapabilityOutcome(StrEnum):
    AUTO_EXECUTE = "auto_execute"
    PARTIAL_EXECUTE = "partial_execute"
    CLARIFY = "clarify"
    UNSUPPORTED = "unsupported"
    SAFE_ABSTAIN = "safe_abstain"
    INVALID = "invalid"


# Clarifiable reasons with Engine information-value + unlockability policy.
_SLOT_FOR_REASON: dict[str, tuple[str, AnswerKind, InformationValue]] = {
    REASON_MISSING_ENTITY: ("measured_entity", "entity_reference", "high"),
    REASON_MISSING_RELATION_SUBJECT: ("relation_subject", "entity_reference", "high"),
    REASON_MISSING_RELATION_OBJECT: ("relation_object", "entity_reference", "high"),
    REASON_AMBIGUOUS_CORRECTION_TARGET: ("correction_target", "correction_target", "high"),
    REASON_MISSING_MEASUREMENT_DIMENSION: ("measurement_dimension", "dimension", "high"),
    REASON_MISSING_MEASUREMENT_VALUE: ("measurement_value", "value", "high"),
    REASON_MISSING_ATTRIBUTE_VALUE: ("attribute_value", "value", "high"),
    # Legacy incomplete cue without surface content — still unlockable via value/dimension.
    REASON_MISSING_ATTRIBUTE_DIMENSION: ("attribute_dimension", "dimension", "medium"),
    REASON_MISSING_STATE_VALUE: ("state_value", "value", "medium"),
    REASON_MISSING_STATE_DIMENSION: ("state_dimension", "dimension", "medium"),
}

# Low-value / non-clarifying structured signals (abstain, not unsupported).
_LOW_VALUE_OR_NON_CLARIFY = frozenset(
    {
        REASON_CANONICAL_TYPE_UNRESOLVED_SAFE_PARTIAL,
        REASON_EVENT_IDENTITY_INCOMPLETE,
        "classification_not_materializable",
        "missing_relation_identity",
    }
)

# One clarification round per semantic gap (Engine v1 budget).
MAX_CLARIFICATIONS_PER_GAP = 1


@dataclass(frozen=True)
class ClarificationRequest:
    """Structured clarification — Product may render text; Engine owns the slot contract."""

    primitive: PrimitiveKind
    missing_slot: str
    expected_answer_kind: AnswerKind
    reason: str
    question_key: str
    information_value: InformationValue
    blocking: bool = True
    user_unlockable: bool = True


@dataclass(frozen=True)
class CapabilityDecision:
    outcome: CapabilityOutcome
    readiness: ExecutionReadiness
    clarification: ClarificationRequest | None = None
    notes: tuple[str, ...] = ()
    user_unlockable: bool | None = None
    """Whether additional user input can unlock; None when not applicable."""
    primary_reason: str | None = None
    diagnostic: tuple[str, ...] = field(default_factory=tuple)
    """Observability: reason / unlockability / outcome chain."""

    @property
    def can_auto_or_partial_execute(self) -> bool:
        return self.outcome in {
            CapabilityOutcome.AUTO_EXECUTE,
            CapabilityOutcome.PARTIAL_EXECUTE,
        }


def reason_user_unlockable(reason: str) -> bool:
    """True iff supplying more user information can realistically unlock."""
    if reason in _UNSUPPORTED_REASONS:
        return False
    meta = _SLOT_FOR_REASON.get(reason)
    return meta is not None and meta[2] in {"high", "medium"}


def gap_user_answerable(reason: str) -> bool:
    """Backward-compatible alias for reason_user_unlockable."""
    return reason_user_unlockable(reason)


def _primitive_for_reason(readiness: ExecutionReadiness, reason: str) -> PrimitiveKind:
    for item in readiness.primitives:
        if reason in item.reasons:
            return item.primitive
    if reason in {
        REASON_MISSING_ENTITY,
        REASON_MISSING_MEASUREMENT_DIMENSION,
        REASON_MISSING_MEASUREMENT_VALUE,
    }:
        return PrimitiveKind.MEASUREMENT
    if reason in {REASON_MISSING_RELATION_SUBJECT, REASON_MISSING_RELATION_OBJECT}:
        return PrimitiveKind.RELATION
    if reason in {REASON_MISSING_STATE_VALUE, REASON_MISSING_STATE_DIMENSION}:
        return PrimitiveKind.STATE
    if reason in {
        REASON_MISSING_ATTRIBUTE_DIMENSION,
        REASON_MISSING_ATTRIBUTE_VALUE,
        REASON_UNSUPPORTED_ATTRIBUTE_DIMENSION,
    }:
        return PrimitiveKind.ATTRIBUTE
    if reason == REASON_AMBIGUOUS_CORRECTION_TARGET:
        return PrimitiveKind.UNKNOWN
    return PrimitiveKind.UNKNOWN


def _question_key_for(
    reason: str,
    *,
    proposal: SemanticProposal | None,
) -> str:
    key = question_key_for_reason(reason)
    if reason == REASON_MISSING_ATTRIBUTE_VALUE and proposal is not None:
        kind = None
        if proposal.subject is not None:
            kind = proposal.subject.kind_hint
        if kind in {"vehicle", "automobile"}:
            return "clarify.attribute.vehicle_value"
    return key


def _select_clarification(
    readiness: ExecutionReadiness,
    *,
    proposal: SemanticProposal | None = None,
) -> ClarificationRequest | None:
    """At most one high/medium-value unlockable clarifiable gap. No questionnaire."""
    candidates: list[ClarificationRequest] = []
    for item in readiness.primitives:
        if item.status is not PrimitiveExecutionStatus.INCOMPLETE_REQUIRED_INFORMATION:
            continue
        if not item.clarification_eligible:
            continue
        for reason in item.reasons:
            if not reason_user_unlockable(reason):
                continue
            meta = _SLOT_FOR_REASON.get(reason)
            if meta is None:
                continue
            slot, kind, value = meta
            if value == "none" or value == "low":
                continue
            candidates.append(
                ClarificationRequest(
                    primitive=item.primitive,
                    missing_slot=slot,
                    expected_answer_kind=kind,
                    reason=reason,
                    question_key=_question_key_for(reason, proposal=proposal),
                    information_value=value,
                    blocking=True,
                    user_unlockable=True,
                )
            )
    if not candidates:
        return None
    order = {"high": 0, "medium": 1, "low": 2, "none": 3}
    candidates.sort(key=lambda c: (order[c.information_value], c.reason))
    return candidates[0]


def _primary_unsupported_reason(readiness: ExecutionReadiness) -> str | None:
    for reason in readiness.reasons:
        if reason in _UNSUPPORTED_REASONS:
            return reason
    return None


def decide_capability(
    readiness: ExecutionReadiness | None,
    *,
    proposal: SemanticProposal | None = None,
) -> CapabilityDecision:
    """Deterministic capability decision. No model call. No raw_input scan for authority."""
    if readiness is None:
        return CapabilityDecision(
            outcome=CapabilityOutcome.INVALID,
            readiness=ExecutionReadiness(outcome=ProposalExecutionOutcome.INVALID),
            notes=("no_readiness",),
            user_unlockable=None,
            diagnostic=("no_readiness",),
        )

    if readiness.outcome is ProposalExecutionOutcome.INVALID:
        return CapabilityDecision(
            outcome=CapabilityOutcome.INVALID,
            readiness=readiness,
            notes=("invalid_proposal",),
            user_unlockable=False,
            primary_reason=readiness.reasons[0] if readiness.reasons else "invalid",
            diagnostic=("invalid_proposal", *(readiness.reasons[:3])),
        )

    if readiness.outcome is ProposalExecutionOutcome.VALID_EXECUTABLE:
        return CapabilityDecision(
            outcome=CapabilityOutcome.AUTO_EXECUTE,
            readiness=readiness,
            notes=("fully_executable",),
            user_unlockable=None,
            diagnostic=("fully_executable",),
        )

    if readiness.outcome is ProposalExecutionOutcome.VALID_PARTIALLY_EXECUTABLE:
        notes = ["partial_commit_allowed"]
        clar = _select_clarification(readiness, proposal=proposal)
        if clar is not None:
            notes.append("sibling_gap_clarifiable_deferred")
        return CapabilityDecision(
            outcome=CapabilityOutcome.PARTIAL_EXECUTE,
            readiness=readiness,
            clarification=None,  # do not block ready commit with clarification
            notes=tuple(notes),
            user_unlockable=None,
            diagnostic=("partial_commit_allowed",),
        )

    # VALID_EXECUTION_INCOMPLETE
    unsupported = _primary_unsupported_reason(readiness)
    clar = _select_clarification(readiness, proposal=proposal)

    # Prefer unlockable CLARIFY when present (even if a sibling unsupported note exists).
    if clar is not None and clar.information_value in {"high", "medium"} and clar.user_unlockable:
        return CapabilityDecision(
            outcome=CapabilityOutcome.CLARIFY,
            readiness=readiness,
            clarification=clar,
            notes=("detectable_user_answerable_gap", clar.reason),
            user_unlockable=True,
            primary_reason=clar.reason,
            diagnostic=(
                "capability_outcome=clarify",
                f"reason={clar.reason}",
                "user_unlockable=true",
                f"question_key={clar.question_key}",
                f"missing_slot={clar.missing_slot}",
            ),
        )

    if unsupported is not None:
        return CapabilityDecision(
            outcome=CapabilityOutcome.UNSUPPORTED,
            readiness=readiness,
            clarification=None,
            notes=("known_capability_gap", unsupported),
            user_unlockable=False,
            primary_reason=unsupported,
            diagnostic=(
                "capability_outcome=unsupported",
                f"reason={unsupported}",
                "user_unlockable=false",
            ),
        )

    # Safe partial Event alone / low-value taxonomy / non-answerable gaps
    only_low = bool(readiness.reasons) and all(
        r in _LOW_VALUE_OR_NON_CLARIFY or r not in _SLOT_FOR_REASON for r in readiness.reasons
    )
    notes = ["safe_abstain"]
    if only_low or readiness.safe_partial_count > 0:
        notes.append("low_value_or_safe_partial_only")
    primary = readiness.reasons[0] if readiness.reasons else "execution_incomplete"
    return CapabilityDecision(
        outcome=CapabilityOutcome.SAFE_ABSTAIN,
        readiness=readiness,
        clarification=None,
        notes=tuple(notes),
        user_unlockable=False,
        primary_reason=primary,
        diagnostic=(
            "capability_outcome=safe_abstain",
            f"reason={primary}",
            "user_unlockable=false",
        ),
    )


def apply_clarification_evidence(
    proposal: SemanticProposal,
    request: ClarificationRequest,
    *,
    entity_text: str | None = None,
    dimension_key: str | None = None,
    value: str | None = None,
) -> SemanticProposal:
    """Fill exactly the requested slot with new user evidence.

    Does not scan raw_input. Does not add unrelated primitives.
    Does not mutate the original object (returns a copy).
    """
    data = proposal.model_dump()
    slot = request.missing_slot
    if slot in {"measured_entity", "state_entity", "attribute_entity", "relation_subject"}:
        if not entity_text or not entity_text.strip():
            raise ValueError("entity_reference required")
        data["subject"] = SemanticEntityMention(
            text=entity_text.strip(), kind_hint="thing"
        ).model_dump()
    elif slot == "relation_object":
        if not entity_text or not entity_text.strip():
            raise ValueError("entity_reference required")
        data["object"] = SemanticEntityMention(
            text=entity_text.strip(), kind_hint="thing"
        ).model_dump()
    elif slot in {"measurement_dimension", "attribute_dimension", "state_dimension"}:
        if not dimension_key or not dimension_key.strip():
            raise ValueError("dimension required")
        if slot == "measurement_dimension":
            data["measurable_dimension_key"] = dimension_key.strip()
        elif slot == "attribute_dimension":
            token = dimension_key.strip()
            existing = (data.get("attribute_expression") or "").strip()
            if not existing:
                data["attribute_expression"] = token
            elif token.casefold() not in existing.casefold():
                data["attribute_expression"] = f"{token} {existing}"
        else:
            token = dimension_key.strip()
            existing = (data.get("state_expression") or "").strip()
            if not existing:
                data["state_expression"] = token
            elif token.casefold() not in existing.casefold():
                data["state_expression"] = f"{token} {existing}"
    elif slot in {"measurement_value", "state_value", "attribute_value"}:
        if value is None or not str(value).strip():
            raise ValueError("value required")
        if slot == "measurement_value":
            data["measurement_numeric_value"] = str(value).strip()
        elif slot == "attribute_value":
            existing = (data.get("attribute_expression") or "").strip()
            token = str(value).strip()
            data["attribute_expression"] = f"{existing} {token}".strip() if existing else token
            data["stable_property_semantics"] = True
        else:
            data["state_expression"] = str(value).strip()
    elif slot == "correction_target":
        raise ValueError("correction_target recovery deferred to Correction Target Resolver")
    else:
        raise ValueError(f"unsupported clarification slot: {slot}")

    return SemanticProposal.model_validate(data)


def is_detectable_completeness_gap(readiness: ExecutionReadiness) -> bool:
    return any(
        p.status is PrimitiveExecutionStatus.INCOMPLETE_REQUIRED_INFORMATION
        for p in readiness.primitives
    )
