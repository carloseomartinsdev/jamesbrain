"""Semantic completeness assessment — distinct from transport validity."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.router import route_primitive


class SemanticActionability(StrEnum):
    ACTIONABLE = "actionable"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"
    CONTRADICTORY = "contradictory"


@dataclass(frozen=True)
class ProposalSemanticAssessment:
    status: SemanticActionability
    routed_primitive: PrimitiveKind
    missing_semantic_roles: tuple[str, ...] = ()
    conflicting_signals: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


def _entity_text(proposal: SemanticProposal, role: str) -> str | None:
    ent = proposal.subject if role == "subject" else proposal.object
    if ent is None:
        return None
    text = (ent.text or "").strip()
    return text or None


def _has_expression(proposal: SemanticProposal) -> bool:
    return any(
        (
            proposal.action_expression,
            proposal.relation_expression,
            proposal.state_expression,
            proposal.attribute_expression,
            proposal.event_expression,
            proposal.measurement_expression,
        )
    )


def _measurement_requirements(proposal: SemanticProposal) -> tuple[bool, tuple[str, ...]]:
    missing: list[str] = []
    if not (
        proposal.measurement_semantics
        or proposal.measurement_expression
        or proposal.measurable_dimension_key
        or proposal.measurement_numeric_value
    ):
        missing.append("measurement_evidence")
    if not (
        _entity_text(proposal, "subject")
        or _entity_text(proposal, "object")
        or (proposal.context is not None and (proposal.context.text or "").strip())
    ):
        missing.append("measured_entity")
    return not missing, tuple(missing)


def _relation_requirements(proposal: SemanticProposal) -> tuple[bool, tuple[str, ...]]:
    missing: list[str] = []
    if not (proposal.link_semantics or proposal.relation_expression):
        missing.append("link_semantics_or_relation_expression")
    if _entity_text(proposal, "subject") is None:
        missing.append("subject")
    if proposal.utterance_kind != "query" and _entity_text(proposal, "object") is None:
        missing.append("object")
    return not missing, tuple(missing)


def _state_requirements(proposal: SemanticProposal) -> tuple[bool, tuple[str, ...]]:
    missing: list[str] = []
    if not (proposal.condition_semantics or proposal.state_expression):
        missing.append("condition_semantics_or_state_expression")
    if _entity_text(proposal, "subject") is None and not proposal.entities_mentioned:
        missing.append("subject_or_entities_mentioned")
    return not missing, tuple(missing)


def _event_requirements(proposal: SemanticProposal) -> tuple[bool, tuple[str, ...]]:
    missing: list[str] = []
    if not (
        proposal.change_semantics
        or proposal.action_expression
        or proposal.event_expression
        or proposal.temporal.occurrence_aspect in {"happened", "planned"}
    ):
        missing.append("change_or_event_evidence")
    return not missing, tuple(missing)


def _attribute_requirements(proposal: SemanticProposal) -> tuple[bool, tuple[str, ...]]:
    missing: list[str] = []
    if not (proposal.stable_property_semantics or proposal.attribute_expression):
        missing.append("stable_property_or_attribute_expression")
    if _entity_text(proposal, "subject") is None and not proposal.entities_mentioned:
        missing.append("subject_or_entities_mentioned")
    return not missing, tuple(missing)


def _type_requirements(proposal: SemanticProposal) -> tuple[bool, tuple[str, ...]]:
    missing: list[str] = []
    if not proposal.classification_semantics:
        missing.append("classification_semantics")
    if _entity_text(proposal, "subject") is None and not proposal.entities_mentioned:
        missing.append("subject_or_entities_mentioned")
    return not missing, tuple(missing)


def _detect_conflicts(proposal: SemanticProposal) -> tuple[str, ...]:
    conflicts: list[str] = []
    if proposal.link_semantics and proposal.condition_semantics:
        if proposal.relation_expression and proposal.state_expression:
            conflicts.append("link_and_condition_with_both_expressions")
    if proposal.primitive_hint == "attribute" and proposal.change_semantics and not proposal.stable_property_semantics:
        conflicts.append("attribute_hint_with_change_semantics")
    if proposal.classification_semantics and proposal.condition_semantics:
        conflicts.append("classification_and_condition")
    return tuple(conflicts)


def _event_query_requirements(proposal: SemanticProposal) -> tuple[bool, tuple[str, ...]]:
    missing: list[str] = []
    if not (
        proposal.action_expression
        or proposal.event_expression
        or proposal.change_semantics
        or proposal.temporal.occurrence_aspect in {"happened", "planned"}
    ):
        missing.append("query_event_evidence")
    return not missing, tuple(missing)


def assess_semantic_proposal(proposal: SemanticProposal) -> ProposalSemanticAssessment:
    """Deterministic semantic role coverage — does not invent missing fields."""
    primitive, routing_notes = route_primitive(proposal)
    conflicts = _detect_conflicts(proposal)

    if not _has_expression(proposal) and not any(
        (
            proposal.change_semantics,
            proposal.condition_semantics,
            proposal.link_semantics,
            proposal.stable_property_semantics,
            proposal.classification_semantics,
            proposal.measurement_semantics,
            proposal.correction_semantics,
        )
    ):
        return ProposalSemanticAssessment(
            status=SemanticActionability.INSUFFICIENT,
            routed_primitive=primitive,
            missing_semantic_roles=("semantic_signals",),
            notes=tuple(routing_notes),
        )

    if conflicts:
        return ProposalSemanticAssessment(
            status=SemanticActionability.CONTRADICTORY,
            routed_primitive=primitive,
            conflicting_signals=conflicts,
            notes=tuple(routing_notes),
        )

    # Correction meta may be actionable without a world primitive when retract-only.
    if proposal.correction_semantics and proposal.utterance_kind == "correct":
        if proposal.correction_operation == "retract":
            return ProposalSemanticAssessment(
                status=SemanticActionability.ACTIONABLE,
                routed_primitive=primitive,
                notes=tuple(routing_notes) + ("correction_retract",),
            )

    if primitive is PrimitiveKind.RELATION:
        ok, missing = _relation_requirements(proposal)
    elif primitive is PrimitiveKind.STATE:
        ok, missing = _state_requirements(proposal)
    elif primitive is PrimitiveKind.EVENT:
        if proposal.utterance_kind == "query":
            ok, missing = _event_query_requirements(proposal)
        else:
            ok, missing = _event_requirements(proposal)
    elif primitive is PrimitiveKind.ATTRIBUTE:
        ok, missing = _attribute_requirements(proposal)
    elif primitive is PrimitiveKind.TYPE:
        ok, missing = _type_requirements(proposal)
    elif primitive is PrimitiveKind.MEASUREMENT:
        ok, missing = _measurement_requirements(proposal)
    else:
        ok, missing = False, ("unknown_primitive",)

    if ok:
        return ProposalSemanticAssessment(
            status=SemanticActionability.ACTIONABLE,
            routed_primitive=primitive,
            notes=tuple(routing_notes),
        )

    partial_ok = primitive is not PrimitiveKind.UNKNOWN and (
        proposal.change_semantics
        or proposal.condition_semantics
        or proposal.link_semantics
        or proposal.stable_property_semantics
        or proposal.classification_semantics
        or proposal.measurement_semantics
        or proposal.correction_semantics
        or _has_expression(proposal)
    )
    if partial_ok:
        return ProposalSemanticAssessment(
            status=SemanticActionability.PARTIAL,
            routed_primitive=primitive,
            missing_semantic_roles=missing,
            notes=tuple(routing_notes),
        )

    return ProposalSemanticAssessment(
        status=SemanticActionability.INSUFFICIENT,
        routed_primitive=primitive,
        missing_semantic_roles=missing,
        notes=tuple(routing_notes),
    )
