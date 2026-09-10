"""Self-reference detection for Principal Binding (E1.1)."""

from __future__ import annotations

import re
import unicodedata

from pke.interpretation.models import EntityMention, MentionReferenceKind
from pke.interpretation.semantic.models import SemanticEntityMention

_SELF_TOKENS = frozenset(
    {
        "eu",
        "me",
        "mim",
        "comigo",
        "meu",
        "minha",
        "meus",
        "minhas",
    }
)

_SELF_PHRASES = frozenset(
    {
        "para mim",
        "pra mim",
        "a mim",
    }
)


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped.casefold().strip())


def is_self_lexeme(text: str) -> bool:
    folded = _fold(text)
    if not folded:
        return False
    if folded in _SELF_PHRASES or folded in _SELF_TOKENS:
        return True
    # Single-token possessives / pronouns only — not "meu carro".
    return folded in _SELF_TOKENS


def is_self_semantic_mention(mention: SemanticEntityMention | None) -> bool:
    if mention is None:
        return False
    if mention.reference_kind == "contextual" and is_self_lexeme(mention.text):
        return True
    return False


def is_self_entity_mention(mention: EntityMention) -> bool:
    if mention.known_entity_id:
        # Explicit id may be principal; caller still ensures binding separately.
        return mention.reference_kind is MentionReferenceKind.CONTEXTUAL and is_self_lexeme(
            mention.text
        )
    return mention.reference_kind is MentionReferenceKind.CONTEXTUAL and is_self_lexeme(
        mention.text
    )
