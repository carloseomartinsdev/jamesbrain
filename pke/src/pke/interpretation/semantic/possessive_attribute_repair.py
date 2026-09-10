"""Registry-driven possessive attribute repairs — entity-agnostic.

Dimensions come only from ATTRIBUTE_DIMENSION_REGISTRY aliases.
The possessed noun after meu/minha/my is the subject — not a vehicle lexicon.
When that noun *is* a dimension alias (meu nome, minha altura), the subject is self.
"""

from __future__ import annotations

import re
import unicodedata

from pke.interpretation.semantic.attribute_commit import commit_attribute_slots
from pke.interpretation.semantic.attribute_registry import (
    alias_to_dimension_key,
    dimension_alias_map,
    get_dimension,
    is_registered_dimension,
)
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

SNAPSHOT_EXPRESSION = "*"

_COLOR_WORDS = frozenset(
    {
        "prata",
        "silver",
        "branca",
        "branco",
        "white",
        "preto",
        "preta",
        "black",
        "cinza",
        "gray",
        "grey",
        "azul",
        "blue",
        "vermelho",
        "vermelha",
        "red",
    }
)

# Soft resolver hints only — not a dimension catalog and not car-specific patterns.
_NOUN_KIND_HINT: dict[str, str] = {
    "carro": "vehicle",
    "car": "vehicle",
    "veiculo": "vehicle",
    "auto": "vehicle",
    "moto": "vehicle",
    "motocicleta": "vehicle",
    "bicicleta": "vehicle",
    "bike": "vehicle",
    "casa": "place",
    "apartamento": "place",
    "house": "place",
    "amigo": "person",
    "amiga": "person",
    "filho": "person",
    "filha": "person",
    "porta": "appliance",
    "telefone": "appliance",
    "celular": "appliance",
    "phone": "appliance",
}

_SELF_LEXEMES = frozenset({"eu", "i", "me", "mim"})
_JAMES_PREFIX = re.compile(r"^\s*james\s*[,:\-]+\s*", re.IGNORECASE)
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_PAINT_VERBS = re.compile(
    r"\b(?:pintei|pintou|painted|mudei|troquei|alterei|changed)\b",
)


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold().strip()


def _clean_raw(raw: str) -> str:
    text = (raw or "").strip()
    text = _JAMES_PREFIX.sub("", text)
    return re.sub(r"[?!.…]+$", "", text).strip()


def _possessed_noun(folded: str) -> str | None:
    match = re.search(
        r"\b(?:meu|minha|meus|minhas|my)\s+(?:um|uma|a|an\s+)?(?P<noun>[\w\-]+)",
        folded,
    )
    if match:
        return match.group("noun")
    return None


def _aliases_longest() -> list[tuple[str, str]]:
    items = [
        (alias, key)
        for alias, key in dimension_alias_map().items()
        if is_registered_dimension(key)
    ]
    return sorted(items, key=lambda row: (-len(row[0]), row[0]))


def dimension_in_text(folded: str) -> str | None:
    """Longest registry alias that appears as a whole token in folded text."""
    for alias, key in _aliases_longest():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", folded):
            return key
    return None


def _expression_dimension(expr: str) -> str | None:
    text = (expr or "").strip()
    if not text or text == SNAPSHOT_EXPRESSION:
        return None
    folded = _fold(text)
    tokens = folded.split()
    for candidate in (folded, tokens[0] if tokens else ""):
        if not candidate:
            continue
        key = alias_to_dimension_key(candidate)
        if key and is_registered_dimension(key):
            return key
    return dimension_in_text(folded)


def _noun_dimension(noun: str | None) -> str | None:
    if not noun:
        return None
    key = alias_to_dimension_key(_fold(noun))
    if key and is_registered_dimension(key):
        return key
    return None


def _display_noun(proposal: SemanticProposal, noun: str) -> tuple[str, bool]:
    """Keep original spelling; capitalized tokens (Corolla) are named, not generic."""
    raw = proposal.raw_input or ""
    match = re.search(rf"\b({re.escape(noun)})\b", raw, re.IGNORECASE)
    if not match:
        return noun, False
    token = match.group(1)
    named = bool(token[:1].isupper() and not token.isupper())
    return token, named


def _mention_for_noun(proposal: SemanticProposal, noun: str) -> SemanticEntityMention:
    existing = proposal.subject
    if existing is not None and _fold(existing.text) == _fold(noun):
        return existing
    display, named = _display_noun(proposal, noun)
    kind = _NOUN_KIND_HINT.get(_fold(noun))
    return SemanticEntityMention(
        text=display,
        kind_hint=kind,
        reference_kind="named" if named else "contextual",
        confidence=1.0,
    )


def _self_subject() -> SemanticEntityMention:
    return SemanticEntityMention(
        text="eu",
        kind_hint="person",
        reference_kind="contextual",
        confidence=1.0,
    )


def _self_subject_for(proposal: SemanticProposal, noun: str) -> SemanticEntityMention:
    existing = proposal.subject
    if existing is not None and _fold(existing.text) in _SELF_LEXEMES:
        return existing
    return _self_subject()


def _as_attribute_query(
    proposal: SemanticProposal, noun: str, expression: str, *, self_subject: bool = False
) -> SemanticProposal:
    subject = (
        _self_subject_for(proposal, noun) if self_subject else _mention_for_noun(proposal, noun)
    )
    return commit_attribute_slots(
        proposal,
        utterance_kind="query",
        subject=subject,
        attribute_expression=expression,
    )


def _as_attribute_write(
    proposal: SemanticProposal, noun: str, expression: str, *, self_subject: bool = False
) -> SemanticProposal:
    subject = (
        _self_subject_for(proposal, noun) if self_subject else _mention_for_noun(proposal, noun)
    )
    return commit_attribute_slots(
        proposal,
        utterance_kind="assert",
        subject=subject,
        attribute_expression=expression,
    )


def _query_like(folded: str) -> bool:
    return bool(
        re.search(
            r"\b(qual|quais|quanto|quanta|quantos|what|how|como)\b",
            folded,
        )
        or folded.endswith("?")
    )


def _overview_like(folded: str) -> bool:
    return bool(
        re.search(
            r"\b(o\s+que|what)\b.*\b(sabe|souber|conhece|know)\b.*\b(sobre|about|d[oea]|do|da)\b",
            folded,
        )
        or re.search(r"\b(me\s+)?(conta|fala|diz|tell)\b.*\b(sobre|about|d[oea]|do|da)\b", folded)
    )


def _possession_query(folded: str) -> str | None:
    match = re.fullmatch(
        r"(?:eu\s+)?(?:tenho|tem|possuo|have)\s+(?:um|uma|o|a|uns|umas)?\s*(?P<noun>[\w\-]+)",
        folded,
    )
    if match:
        return match.group("noun")
    return None


def _color_token(text: str) -> str | None:
    folded = _fold(text)
    for token in re.findall(r"[\w\-]+", folded):
        if token in _COLOR_WORDS:
            return token
    return None


def _write_expression(dimension_key: str, value: str) -> str:
    spec = get_dimension(dimension_key)
    value = value.strip().strip(".,;:!")
    if spec is None:
        return value
    if spec.value_kind == "year":
        year = _YEAR.search(value)
        return year.group(1) if year else value
    if spec.key == "color":
        color = _color_token(value)
        return f"cor {color}" if color else f"cor {value}"
    alias = spec.aliases[0] if spec.aliases else spec.key
    return f"{alias} {value}"


def _dimension_alias(dimension_key: str) -> str:
    spec = get_dimension(dimension_key)
    if spec and spec.aliases:
        return spec.aliases[0]
    return dimension_key


def _already_aligned(
    proposal: SemanticProposal,
    *,
    dimension: str | None,
    folded: str,
) -> bool:
    """Do not clobber a proposal that already targets a registered dimension on a subject.

    Live LLM mismatches (marca vs ano) still repair because the raw dimension differs.
    Writes also need a typed value — 'ano 2008' as expression is not aligned.
    """
    if proposal.subject is None or proposal.change_semantics or _PAINT_VERBS.search(folded):
        return False
    existing_dim = _expression_dimension(proposal.attribute_expression or "")
    if not existing_dim:
        return False
    if dimension and dimension != existing_dim:
        return False
    if proposal.primitive_hint not in {None, "unknown", "attribute"}:
        return False
    if proposal.utterance_kind != "query":
        from pke.interpretation.semantic.attribute_resolution import resolve_attribute_value

        if resolve_attribute_value(proposal) is None:
            return False
    return True


def _value_only(folded: str) -> str | None:
    match = re.fullmatch(r"(?:e|é|=|is)\s+(?P<value>.+)", folded)
    if match:
        return match.group("value").strip()
    if _YEAR.fullmatch(folded):
        return folded
    tokens = folded.split()
    if len(tokens) == 1 and tokens[0] in _COLOR_WORDS:
        return tokens[0]
    return None


def _value_fits_dimension(dimension_key: str, value: str) -> bool:
    spec = get_dimension(dimension_key)
    if spec is None or not is_registered_dimension(dimension_key):
        return False
    if spec.value_kind == "year":
        return _YEAR.search(value) is not None
    if spec.key == "color":
        return _color_token(value) is not None
    if spec.value_kind == "number":
        return bool(re.search(r"\d", value))
    return bool(value.strip())


def _continuation_target(prior: str) -> tuple[str, str] | None:
    """Possessed noun + registry dimension from the previous user utterance."""
    folded = _fold(_clean_raw(prior))
    if not folded:
        return None
    dimension = dimension_in_text(folded)
    noun = _possessed_noun(folded)
    if not dimension or not noun:
        return None
    if _noun_dimension(noun) == dimension:
        return ("eu", dimension)
    return (noun, dimension)


def repair_possessive_attributes(
    proposal: SemanticProposal,
    *,
    prior_utterances: list[str] | tuple[str, ...] = (),
) -> SemanticProposal:
    """Apply high-precision possessive patterns using the controlled registry."""
    if proposal.correction_semantics:
        return proposal
    raw = _clean_raw(proposal.raw_input or "")
    if not raw:
        return proposal
    folded = _fold(raw)
    noun = _possessed_noun(folded)
    dimension = dimension_in_text(folded)

    have_noun = _possession_query(folded)
    if have_noun and _noun_dimension(have_noun) is None:
        return proposal.model_copy(
            update={
                "utterance_kind": "query",
                "primitive_hint": "relation",
                "link_semantics": True,
                "stable_property_semantics": False,
                "change_semantics": False,
                "subject": _self_subject(),
                "object": _mention_for_noun(proposal, have_noun),
                "relation_expression": "owns",
                "attribute_expression": None,
            }
        )

    paint = re.search(
        r"\b(?:pintei|pintou|painted|mudei|troquei|alterei|changed)\b\s+"
        r"(?:a\s+cor\s+(?:d[oa]\s+)?)?(?:(?:o|a|os|as)\s+)?"
        r"(?:(?:meu|minha|meus|minhas|my)\s+)?"
        r"(?P<noun>[\w\-]+)\s+"
        r"(?:de|para|to|em)\s+(?P<value>.+)$",
        folded,
    )
    if paint:
        value = paint.group("value")
        dim = dimension or ("color" if _color_token(value) else None)
        if dim and is_registered_dimension(dim):
            return _as_attribute_write(
                proposal, paint.group("noun"), _write_expression(dim, value)
            )

    if _already_aligned(proposal, dimension=dimension, folded=folded):
        return proposal

    self_dim = _noun_dimension(noun)
    if noun and dimension and self_dim == dimension and _query_like(folded):
        return _as_attribute_query(
            proposal, noun, _dimension_alias(dimension), self_subject=True
        )

    if noun and dimension and _query_like(folded) and not _YEAR.fullmatch(folded):
        return _as_attribute_query(proposal, noun, _dimension_alias(dimension))

    write = re.search(
        r"\b(?P<alias>"
        + "|".join(re.escape(a) for a, _ in _aliases_longest())
        + r")\b\s+(?:d[oa]s?\s+)?(?:meu|minha|meus|minhas|my)\s+(?P<noun>[\w\-]+)\s+"
        r"(?:e|é|=|is)\s+(?P<value>.+)$",
        folded,
    )
    if write:
        dim = alias_to_dimension_key(write.group("alias"))
        owned = write.group("noun")
        if dim and is_registered_dimension(dim):
            return _as_attribute_write(
                proposal,
                owned,
                _write_expression(dim, write.group("value")),
                self_subject=_noun_dimension(owned) == dim,
            )

    if noun and _overview_like(folded) and self_dim is None:
        return _as_attribute_query(proposal, noun, SNAPSHOT_EXPRESSION)

    identity = re.fullmatch(
        r"(?:qual|quais|what)(?:\s+(?:e|é|is))?\s+(?:o|a|os|as|the)?\s+"
        r"(?:meu|minha|meus|minhas|my)\s+(?P<noun>[\w\-]+)",
        folded,
    )
    if identity and dimension is None:
        ident_noun = identity.group("noun")
        ident_dim = _noun_dimension(ident_noun)
        if ident_dim:
            return _as_attribute_query(
                proposal, ident_noun, _dimension_alias(ident_dim), self_subject=True
            )
        if _expression_dimension(proposal.attribute_expression or ""):
            return proposal
        return _as_attribute_query(proposal, ident_noun, SNAPSHOT_EXPRESSION)

    copula = re.fullmatch(
        r"(?:o|a|os|as)?\s*(?:meu|minha|meus|minhas|my)\s+(?P<noun>[\w\-]+)\s+"
        r"(?:e|é|=|is)\s+(?:um|uma|a|an\s+)?(?P<rest>.+)",
        folded,
    )
    if copula and proposal.utterance_kind in {"assert", "change", "none", "describe"}:
        owned = copula.group("noun")
        if _noun_dimension(owned):
            return proposal
        rest = copula.group("rest").strip()
        color = _color_token(rest)
        year = _YEAR.search(rest)
        if color and len(_fold(rest).split()) <= 2:
            return _as_attribute_write(proposal, owned, f"cor {color}")
        if year and dimension in {None, "model_year"}:
            return _as_attribute_write(proposal, owned, year.group(1))

    value_only = _value_only(folded)
    if value_only and proposal.utterance_kind in {"assert", "change", "none", "describe"}:
        for prior in reversed(tuple(prior_utterances)):
            target = _continuation_target(prior)
            if target is None:
                continue
            noun, dim = target
            if not _value_fits_dimension(dim, value_only):
                continue
            return _as_attribute_write(
                proposal,
                noun,
                _write_expression(dim, value_only),
                self_subject=noun == "eu",
            )

    return proposal
