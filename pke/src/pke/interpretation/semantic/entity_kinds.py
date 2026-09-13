"""Mapeamento kind_hint / class_hint → entity_type canônico."""

from __future__ import annotations

from pke.interpretation.semantic.llm_vocab import KIND_HINT_ALIASES, KIND_HINTS
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


def class_hint_to_entity_type_key(class_hint: str) -> str | None:
    """Canonicalize an Interpreter class lemma. Never slugs surface language as ontology."""
    from pke.interpretation.semantic.learned_entity import learned_entity_key_from_class_hint
    from pke.interpretation.semantic.learned_relation import slug_from_expression
    from pke.interpretation.transport.catalog import ConceptCatalog

    folded = class_hint.strip().lower()
    kind = KIND_HINT_ALIASES.get(folded, folded if folded in KIND_HINTS else None)
    if kind and kind in KIND_TO_ENTITY_TYPE:
        return KIND_TO_ENTITY_TYPE[kind]
    slug = slug_from_expression(class_hint)
    if slug is None:
        return None
    core_key = f"entity.{slug}"
    if core_key in ConceptCatalog.entity_types and not core_key.startswith("entity.learned."):
        return core_key
    return learned_entity_key_from_class_hint(class_hint)


def resolve_entity_type(mention: SemanticEntityMention) -> str | None:
    key: str | None = None
    if mention.class_hint:
        key = class_hint_to_entity_type_key(mention.class_hint)
    elif mention.reference_kind == "class":
        if mention.kind_hint and mention.kind_hint not in {"unknown", "thing"}:
            key = KIND_TO_ENTITY_TYPE.get(mention.kind_hint)
    elif mention.kind_hint and mention.kind_hint != "unknown":
        key = KIND_TO_ENTITY_TYPE.get(mention.kind_hint)
    if key:
        from pke.interpretation.semantic.learned_entity import publish_entity_type

        publish_entity_type(key)
    return key


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
