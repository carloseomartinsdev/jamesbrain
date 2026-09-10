"""Resolução de papéis semânticos de participantes em Event."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

PERSON_KINDS = frozenset({"person", "organization"})
CONTEXT_KINDS = frozenset({"vehicle", "place"})
THING_KINDS = frozenset({"thing", "appliance", "document", "medication", "unknown"})

_FIRST_PERSON = re.compile(
    r"\b("
    r"troquei|substituí|substitui|levei|instalei|abri|fechei|comprei|vendi|"
    r"fiz|disse|fui|vim|coloquei|tirei|removi|consertei|arrumei|passei"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResolvedEventRoles:
    """Papéis semânticos distintos dos slots físicos Event.actor_id/subject_id."""

    actor: SemanticEntityMention | None = None
    actor_implicit: bool = False
    object: SemanticEntityMention | None = None
    context: tuple[SemanticEntityMention, ...] = field(default_factory=tuple)
    affected: SemanticEntityMention | None = None


def _mention_text(mention: SemanticEntityMention | None) -> str | None:
    return mention.text.strip().casefold() if mention else None


def _is_person(mention: SemanticEntityMention) -> bool:
    return mention.kind_hint in PERSON_KINDS


def _is_context_kind(mention: SemanticEntityMention) -> bool:
    return mention.kind_hint in CONTEXT_KINDS


def _role_hint_is(mention: SemanticEntityMention, *hints: str) -> bool:
    if mention.role_hint is None:
        return False
    key = mention.role_hint.strip().casefold().removeprefix("role.")
    return key in {h.casefold().removeprefix("role.") for h in hints}


def _is_first_person(proposal: SemanticProposal) -> bool:
    blob = " ".join(
        part
        for part in (
            proposal.action_expression,
            proposal.event_expression,
            proposal.raw_input,
        )
        if part
    )
    return bool(_FIRST_PERSON.search(blob))


def _intransitive_affected(proposal: SemanticProposal) -> SemanticEntityMention | None:
    if not proposal.change_semantics or proposal.object is not None:
        return None
    if proposal.subject is None or _is_person(proposal.subject):
        return None
    if proposal.subject.kind_hint in THING_KINDS or proposal.subject.kind_hint is None:
        return proposal.subject
    return None


def resolve_event_roles(proposal: SemanticProposal) -> ResolvedEventRoles:
    """Deriva papéis semânticos a partir da proposta estruturada — sem NL bruto."""

    affected = _intransitive_affected(proposal)
    actor: SemanticEntityMention | None = None
    obj: SemanticEntityMention | None = proposal.object
    context: list[SemanticEntityMention] = []
    seen_context: set[str] = set()

    def add_context(mention: SemanticEntityMention) -> None:
        key = mention.text.strip().casefold()
        if key in seen_context:
            return
        seen_context.add(key)
        context.append(mention)

    if affected is None and proposal.subject is not None and _is_person(proposal.subject):
        if _role_hint_is(proposal.subject, "actor") or proposal.change_semantics:
            actor = proposal.subject

    for participant in proposal.participants:
        if _role_hint_is(participant, "actor") and _is_person(participant):
            actor = participant
        elif _role_hint_is(participant, "object") and obj is None:
            obj = participant
        elif _role_hint_is(participant, "context") and _is_context_kind(participant):
            add_context(participant)

    if affected is not None:
        actor = None
    elif proposal.subject is not None and _is_context_kind(proposal.subject):
        add_context(proposal.subject)

    actor_text = _mention_text(actor)
    obj_text = _mention_text(obj)
    affected_text = _mention_text(affected)

    for mention in proposal.entities_mentioned:
        text = _mention_text(mention)
        if text is None:
            continue
        if text == actor_text or text == obj_text or text == affected_text:
            continue
        if _is_context_kind(mention) or _role_hint_is(mention, "context"):
            add_context(mention)

    actor_implicit = False
    if affected is None and actor is None and proposal.change_semantics and _is_first_person(proposal):
        actor_implicit = True

    return ResolvedEventRoles(
        actor=actor,
        actor_implicit=actor_implicit,
        object=obj,
        context=tuple(context),
        affected=affected,
    )


def wire_role_for_mention(mention: SemanticEntityMention, roles: ResolvedEventRoles) -> str | None:
    """Mapeia menção para role wire canônico conforme papéis resolvidos."""

    text = _mention_text(mention)
    if text is None:
        return None
    if roles.actor and _mention_text(roles.actor) == text:
        return "role.actor"
    if roles.object and _mention_text(roles.object) == text:
        return "role.object"
    if roles.affected and _mention_text(roles.affected) == text:
        return "role.patient"
    for ctx in roles.context:
        if _mention_text(ctx) == text:
            return "role.context"
    from pke.interpretation.semantic.entity_kinds import resolve_role

    return resolve_role(mention)


def role_preservation_audit(roles: ResolvedEventRoles) -> dict[str, str]:
    """Métrica SEMANTIC_ROLE_PRESERVATION — status por dimensão."""

    def status(known: bool, required: bool = True) -> str:
        if known:
            return "preserved"
        if required:
            return "missing"
        return "not_applicable"

    return {
        "actor": (
            "implicit_known"
            if roles.actor_implicit and roles.actor is None
            else status(roles.actor is not None, required=False)
        ),
        "object": status(roles.object is not None, required=roles.affected is None),
        "context": status(bool(roles.context), required=False),
        "affected_entity": status(roles.affected is not None, required=False),
    }


def false_role_assignments(roles: ResolvedEventRoles) -> list[str]:
    """Métrica FALSE_ROLE_ASSIGNMENT — papéis semanticamente incorretos."""

    violations: list[str] = []
    if roles.actor is not None and _is_context_kind(roles.actor):
        violations.append(f"vehicle_or_place_as_actor:{roles.actor.text}")
    if roles.actor is not None and roles.affected is not None and _mention_text(roles.actor) == _mention_text(
        roles.affected
    ):
        violations.append(f"affected_as_actor:{roles.actor.text}")
    if roles.object is not None and roles.object.kind_hint == "place":
        violations.append(f"place_as_object:{roles.object.text}")
    for ctx in roles.context:
        if roles.actor is not None and _mention_text(roles.actor) == _mention_text(ctx):
            violations.append(f"context_as_actor:{ctx.text}")
    return violations
