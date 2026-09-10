"""Mapeamento kind_hint → entity_type canônico."""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticEntityMention

KIND_TO_ENTITY_TYPE: dict[str, str] = {
    "person": "entity.person",
    "organization": "entity.organization",
    "place": "entity.place",
    "appliance": "entity.appliance",
    "vehicle": "entity.automobile",
    "document": "entity.document",
    "medication": "entity.medication",
    "thing": "entity.thing",
}

ROLE_HINT_TO_KEY: dict[str, str] = {
    "provider": "role.provider",
    "subject": "role.subject",
    "object": "role.object",
    "patient": "role.patient",
    "context": "role.context",
    "actor": "role.actor",
}


def resolve_entity_type(mention: SemanticEntityMention) -> str | None:
    if mention.kind_hint is None or mention.kind_hint == "unknown":
        return None
    return KIND_TO_ENTITY_TYPE.get(mention.kind_hint)


def resolve_role(mention: SemanticEntityMention) -> str | None:
    if mention.role_hint is None:
        return None
    key = mention.role_hint.strip().lower()
    if key.startswith("role."):
        role = key
    else:
        role = ROLE_HINT_TO_KEY.get(key)
    if role is None:
        return None
    return role
