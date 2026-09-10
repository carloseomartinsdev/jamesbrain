"""Deterministic Attribute dimension + typed value resolution — no NLP inventiveness."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from pke.domain.attributes import AttributeValueKind
from pke.interpretation.semantic.aliases import normalize_expression
from pke.interpretation.semantic.attribute_registry import (
    alias_to_dimension_key,
    dimension_alias_map,
    get_dimension,
    is_registered_dimension,
)
from pke.interpretation.semantic.models import SemanticProposal


@dataclass(frozen=True)
class ResolvedAttributeValue:
    dimension_key: str
    value_kind: AttributeValueKind
    text_value: str | None = None
    numeric_value: Decimal | None = None
    unit: str | None = None
    year_value: int | None = None
    date_value: None = None  # reserved
    concept_value_id: str | None = None
    is_current: bool = True
    historical: bool = False


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

_QUANTITY_SPECS: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("area", "m²", frozenset({"m2", "m²", "metros quadrados", "metro quadrado"})),
    ("weight", "kg", frozenset({"kg", "kilo", "kilos", "quilograma", "quilogramas"})),
    ("height", "m", frozenset({"m", "metro", "metros"})),
    ("capacity", "L", frozenset({"l", "lt", "litro", "litros", "liter", "liters"})),
)

# Controlled vehicle brands for everyday E1 — not an open invent list.
_VEHICLE_BRANDS: frozenset[str] = frozenset(
    {
        "honda",
        "toyota",
        "ford",
        "chevrolet",
        "vw",
        "volkswagen",
        "fiat",
        "hyundai",
        "nissan",
        "renault",
        "peugeot",
        "citroen",
        "citroën",
        "jeep",
        "bmw",
        "mercedes",
        "audi",
        "kia",
        "mitsubishi",
        "subaru",
        "volvo",
        "byd",
        "caoa",
    }
)

_NAME_EXPR = re.compile(
    r"(?:name|nome)\s+(?:is|e|é|=)\s+(?P<value>.+)$",
    re.IGNORECASE,
)
_BRAND_EXPR = re.compile(
    r"(?:brand|marca)\s+(?:is|e|é|=)\s+(?P<value>.+)$",
    re.IGNORECASE,
)
_MODEL_EXPR = re.compile(
    r"(?:model|modelo)\s+(?:is|e|é|=)\s+(?P<value>.+)$",
    re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _surface(proposal: SemanticProposal) -> str:
    parts = [
        proposal.attribute_expression or "",
        proposal.raw_input or "",
    ]
    return normalize_expression(" ".join(parts))


def _parse_decimal(token: str) -> Decimal | None:
    cleaned = token.replace(",", ".")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def normalize_name_like(value: str) -> str | None:
    """Name-like text: trim, collapse whitespace, preserve Unicode letters."""
    text = unicodedata.normalize("NFC", value or "")
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return None
    if len(text) > 128:
        return None
    # Reject empty / punctuation-only
    if not re.search(r"\w", text, flags=re.UNICODE):
        return None
    return text


def normalize_brand_like(value: str) -> str | None:
    text = normalize_name_like(value)
    if text is None:
        return None
    folded = _strip_accents(text).casefold()
    if folded not in _VEHICLE_BRANDS:
        return None
    # Canonical display: first registry spelling match prefer title from input tokens
    return text[0].upper() + text[1:] if text else None


def normalize_model_like(value: str) -> str | None:
    text = normalize_name_like(value)
    if text is None:
        return None
    # Models are free-ish tokens (Civic, Corolla, Onix) — reject sentences.
    if len(text.split()) > 3:
        return None
    return text


def _dimension_alias_hit(text: str, alias: str) -> bool:
    """Word-boundary alias match — avoids 'cor' ⊂ 'corolla'."""
    if not text or not alias:
        return False
    if text.strip() == alias:
        return True
    return re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text) is not None


def resolve_attribute_dimension_key_from_answer(answer: str) -> str | None:
    """Map clarification answer to Attribute dimension key via controlled aliases.

    Exact / full-string alias match only. Does not scan original raw_input.
    Does not invent unregistered dimensions.
    """
    text = normalize_expression(answer or "")
    if not text:
        return None
    head = text.split(",")[0].strip()
    key = alias_to_dimension_key(head)
    if key and is_registered_dimension(key):
        return key
    key = alias_to_dimension_key(text)
    if key and is_registered_dimension(key):
        return key
    aliases = dimension_alias_map()
    for alias, dim in sorted(aliases.items(), key=lambda x: -len(x[0])):
        if head == alias or text == alias:
            return dim if is_registered_dimension(dim) else None
    return None


def resolve_attribute_dimension_key(proposal: SemanticProposal) -> str | None:
    """Shared WRITE/READ dimension key from controlled registry + value resolution.

    Does not invent ontology concepts. Returns None when unsafe.
    """
    if proposal.classification_semantics:
        return None
    valued = resolve_attribute_value(proposal)
    if valued is not None:
        return valued.dimension_key
    companions = resolve_companion_attribute_values(proposal)
    if companions:
        return companions[0].dimension_key
    surface = _surface(proposal)
    expr = normalize_expression(proposal.attribute_expression or "")
    aliases = dimension_alias_map()
    for candidate in (expr, surface):
        if not candidate:
            continue
        key = alias_to_dimension_key(candidate.strip())
        if key and is_registered_dimension(key):
            return key
        for alias, dim in sorted(aliases.items(), key=lambda x: -len(x[0])):
            if _dimension_alias_hit(candidate, alias) and is_registered_dimension(dim):
                return dim
    return None


def resolve_companion_attribute_values(
    proposal: SemanticProposal,
) -> tuple[ResolvedAttributeValue, ...]:
    """Extra attributes resolved alongside the primary (e.g. brand+model).

    Empty when only a single dimension applies. Never invents unregistered keys.
    """
    if proposal.classification_semantics:
        return ()
    brand_model = _resolve_brand_and_model(proposal)
    if brand_model is None:
        return ()
    brand, model = brand_model
    out: list[ResolvedAttributeValue] = []
    if brand is not None:
        out.append(brand)
    if model is not None:
        out.append(model)
    return tuple(out)


def resolve_attribute_value(proposal: SemanticProposal) -> ResolvedAttributeValue | None:
    """Map structured Attribute proposals to dimension + typed value.

    Returns None when dimension/value cannot be determined safely.
    """
    if proposal.classification_semantics:
        return None
    if not (proposal.stable_property_semantics or proposal.attribute_expression):
        return None

    surface = _surface(proposal)
    expr = normalize_expression(proposal.attribute_expression or "")
    historical = bool(
        re.search(r"\bera\b|\beram\b|\bwas\b|\bwere\b", surface)
        or (proposal.temporal.tense_evidence or "").lower() in {"era", "eram", "was"}
    )

    named = _resolve_name_value(proposal, historical=historical)
    if named is not None:
        return named

    brand_model = _resolve_brand_and_model(proposal, historical=historical)
    if brand_model is not None:
        brand, model = brand_model
        # Primary for single-attribute IR: brand if present else model.
        if brand is not None:
            return brand
        if model is not None:
            return model

    # capacity cue in expression/raw
    if "capacidad" in surface or "capacity" in surface:
        qty = _match_quantity(surface, "capacity")
        if qty is None:
            qty = _match_quantity(surface, None)
            if qty is not None and qty.dimension_key in {"capacity", "weight", "height", "area"}:
                if qty.unit == "L":
                    qty = ResolvedAttributeValue(
                        dimension_key="capacity",
                        value_kind=AttributeValueKind.NUMBER,
                        numeric_value=qty.numeric_value,
                        unit="L",
                        historical=historical,
                        is_current=not historical,
                    )
                else:
                    qty = None
        if qty is not None:
            return ResolvedAttributeValue(
                dimension_key="capacity",
                value_kind=AttributeValueKind.NUMBER,
                numeric_value=qty.numeric_value,
                unit=qty.unit or "L",
                historical=historical,
                is_current=not historical,
            )

    for dim, _unit, _aliases in _QUANTITY_SPECS:
        qty = _match_quantity(expr or surface, dim)
        if qty is not None:
            return ResolvedAttributeValue(
                dimension_key=qty.dimension_key,
                value_kind=qty.value_kind,
                numeric_value=qty.numeric_value,
                unit=qty.unit,
                historical=historical,
                is_current=not historical,
            )

    year_token = None
    if expr:
        full = re.fullmatch(r"(19|20)\d{2}", expr.strip())
        if full:
            year_token = full.group(0)
        elif "ano" in surface or "year" in surface or "model_year" in surface:
            found = re.search(r"\b((?:19|20)\d{2})\b", expr)
            if found:
                year_token = found.group(1)
    if year_token:
        return ResolvedAttributeValue(
            dimension_key="model_year",
            value_kind=AttributeValueKind.YEAR,
            year_value=int(year_token),
            historical=historical,
            is_current=not historical,
        )

    color_candidates = [expr.strip()] if expr else []
    color_candidates.extend(expr.split() if expr else [])
    for color_token in color_candidates:
        color_norm = _strip_accents(color_token)
        if color_norm in _COLOR_WORDS or color_token in _COLOR_WORDS:
            return ResolvedAttributeValue(
                dimension_key="color",
                value_kind=AttributeValueKind.TEXT,
                text_value=color_norm or color_token,
                historical=historical,
                is_current=not historical,
            )

    aliased = _resolve_color_after_dimension_alias(expr, historical=historical)
    if aliased is not None:
        return aliased

    return None


def _resolve_color_after_dimension_alias(
    expr: str, *, historical: bool
) -> ResolvedAttributeValue | None:
    """Trust LLM slot `cor = verde` without a closed color-word list.

    Dimension must already be on attribute_expression (registry alias). The
    remainder is the text value. Does not scan raw_input for color words.
    """
    folded = normalize_expression(expr or "")
    if not folded:
        return None
    spec = get_dimension("color")
    if spec is None or not is_registered_dimension("color"):
        return None
    aliases = sorted((spec.key, *spec.aliases), key=len, reverse=True)
    for alias in aliases:
        alias_n = normalize_expression(alias)
        if not alias_n or folded == alias_n:
            continue
        if not folded.startswith(alias_n):
            continue
        boundary = folded[len(alias_n) : len(alias_n) + 1]
        if boundary and boundary.isalnum():
            continue
        rest = folded[len(alias_n) :].strip(" \t=:|-")
        rest = re.sub(r"^(?:e|é|is)\s+", "", rest).strip()
        if not rest or alias_to_dimension_key(rest) == "color":
            continue
        normalized = normalize_name_like(rest)
        if normalized is None:
            continue
        text_value = _strip_accents(normalized).casefold() or normalized
        return ResolvedAttributeValue(
            dimension_key="color",
            value_kind=AttributeValueKind.TEXT,
            text_value=text_value,
            historical=historical,
            is_current=not historical,
        )
    return None


def _resolve_name_value(
    proposal: SemanticProposal, *, historical: bool = False
) -> ResolvedAttributeValue | None:
    expr = (proposal.attribute_expression or "").strip()
    raw = (proposal.raw_input or "").strip()
    value: str | None = None
    for candidate in (expr, raw):
        # Prefer original casing from surface (do not fold via normalize_expression).
        match = re.search(
            r"(?:name|nome)\s+(?:is|e|é|=)\s+(?P<value>.+)$",
            candidate,
            flags=re.IGNORECASE,
        )
        if match:
            value = match.group("value").strip().strip(".,;:!")
            break
    if value is None:
        return None
    normalized = normalize_name_like(value)
    if normalized is None:
        return None
    if not is_registered_dimension("name"):
        return None
    return ResolvedAttributeValue(
        dimension_key="name",
        value_kind=AttributeValueKind.TEXT,
        text_value=normalized,
        historical=historical,
        is_current=not historical,
    )


def _resolve_brand_and_model(
    proposal: SemanticProposal, *, historical: bool = False
) -> tuple[ResolvedAttributeValue | None, ResolvedAttributeValue | None] | None:
    expr = (proposal.attribute_expression or "").strip()
    raw = (proposal.raw_input or "").strip()
    surface = normalize_expression(f"{expr} {raw}")

    brand_text: str | None = None
    model_text: str | None = None

    for candidate in (expr, raw):
        bm = _BRAND_EXPR.search(normalize_expression(candidate)) if candidate else None
        if bm:
            brand_text = bm.group("value").strip().strip(".,;:!")
        mm = _MODEL_EXPR.search(normalize_expression(candidate)) if candidate else None
        if mm:
            model_text = mm.group("value").strip().strip(".,;:!")

    # "um Honda Civic" / "Honda Civic" after vehicle cue
    if brand_text is None and model_text is None:
        tokens = [
            t
            for t in re.findall(r"[A-Za-zÀ-ÿ0-9\-]+", raw or expr)
            if t.casefold() not in {"meu", "carro", "e", "é", "um", "uma", "o", "a", "de"}
        ]
        if tokens:
            head = _strip_accents(tokens[0]).casefold()
            if head in _VEHICLE_BRANDS:
                brand_text = tokens[0]
                if len(tokens) >= 2:
                    model_text = " ".join(tokens[1:])

    # Color-only vehicle phrases handled by color path, not brand.
    if brand_text is None and model_text is None:
        return None

    brand_val = normalize_brand_like(brand_text) if brand_text else None
    model_val = normalize_model_like(model_text) if model_text else None

    # If brand token present but not in controlled list → refuse (no invent).
    if brand_text and brand_val is None:
        return None

    brand_attr = (
        ResolvedAttributeValue(
            dimension_key="brand",
            value_kind=AttributeValueKind.TEXT,
            text_value=brand_val,
            historical=historical,
            is_current=not historical,
        )
        if brand_val and is_registered_dimension("brand")
        else None
    )
    model_attr = (
        ResolvedAttributeValue(
            dimension_key="model",
            value_kind=AttributeValueKind.TEXT,
            text_value=model_val,
            historical=historical,
            is_current=not historical,
        )
        if model_val and is_registered_dimension("model")
        else None
    )
    if brand_attr is None and model_attr is None:
        return None
    # Prefer vehicle-ish subject for brand/model; allow None subject (repair may fill).
    subject = proposal.subject
    if subject is not None and subject.kind_hint not in {
        None,
        "vehicle",
        "automobile",
        "thing",
        "unknown",
    }:
        # Person subject with brand → not vehicle brand write
        if subject.kind_hint == "person" and "carro" not in surface and "car" not in surface:
            return None
    return brand_attr, model_attr


def _match_quantity(text: str, preferred_dim: str | None = None) -> ResolvedAttributeValue | None:
    pattern = re.compile(
        r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>m2|m²|metros?\s+quadrados?|kg|kilos?|quilogramas?|"
        r"metros?|m\b|litros?|litro|liters?|l\b|lt\b)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    num = _parse_decimal(match.group("num"))
    if num is None:
        return None
    unit_raw = _strip_accents(match.group("unit").lower().replace(" ", ""))
    for dim, canon_unit, aliases in _QUANTITY_SPECS:
        if preferred_dim and dim != preferred_dim:
            continue
        alias_norm = {_strip_accents(a.replace(" ", "")) for a in aliases}
        if unit_raw in alias_norm or unit_raw.rstrip("s") in alias_norm:
            if dim == "area" and unit_raw in {"m", "metro", "metros"}:
                continue
            if dim == "height" and unit_raw in {"m2", "m²", "metrosquadrados", "metroquadrado"}:
                continue
            return ResolvedAttributeValue(
                dimension_key=dim,
                value_kind=AttributeValueKind.NUMBER,
                numeric_value=num,
                unit=canon_unit,
            )
    if unit_raw in {"l", "lt", "litro", "litros", "liter", "liters"}:
        return ResolvedAttributeValue(
            dimension_key="capacity",
            value_kind=AttributeValueKind.NUMBER,
            numeric_value=num,
            unit="L",
        )
    return None
