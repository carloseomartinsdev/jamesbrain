"""Learn an attribute dimension from a structured Interpreter predicate.

Does not read raw_input. Does not build a language glossary. Semantic identity
is the Interpreter predicate / predicate_key; display label is the observed
surface. CORE aliases always win over a learned slug (fur_color ≠ color).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pke.interpretation.semantic.aliases import normalize_expression
from pke.interpretation.semantic.attribute_registry import (
    AttributeDimensionSpec,
    AttributeDimensionTier,
    alias_to_dimension_key,
    get_dimension,
    is_registered_dimension,
    register_learned_dimension,
)
from pke.interpretation.semantic.learned_relation import slug_from_expression
from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticClaimKind,
    SemanticClaimOrigin,
    SemanticProposal,
)
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology.learned import (
    LEARNED_ATTRIBUTE_PREFIX,
    ensure_if_learned_attribute,
    is_learned_attribute_key,
)
from pke.ontology.registry import OntologyRegistry


@dataclass(frozen=True)
class DimensionIdentity:
    key: str
    source: Literal["core", "learned"]
    label: str
    surface: str


def publish_attribute_dimension(key: str) -> None:
    if key:
        ConceptCatalog.attributes.add(key)


def learned_attribute_key_from_predicate(predicate: str) -> str | None:
    slug = slug_from_expression(predicate)
    if slug is None:
        return None
    key = f"{LEARNED_ATTRIBUTE_PREFIX}{slug}"
    if not is_learned_attribute_key(key):
        return None
    return key


def publish_learned_attribute_dimension(
    key: str,
    *,
    label: str | None = None,
    value_kind: Literal["text", "number", "year", "date", "concept"] = "text",
) -> AttributeDimensionSpec:
    existing = get_dimension(key)
    if existing is not None:
        return existing
    slug = key.rsplit(".", 1)[-1]
    canonical = (label or slug.replace("_", " ")).strip()
    aliases: tuple[str, ...] = ()
    if canonical:
        folded = normalize_expression(canonical)
        aliases = tuple(
            dict.fromkeys(
                item for item in (canonical, folded, slug, key) if item
            )
        )
    spec = AttributeDimensionSpec(
        key=key,
        value_kind=value_kind,
        aliases=aliases,
        tier=AttributeDimensionTier.LEARNED,
        singleton_current=True,
    )
    published = register_learned_dimension(spec)
    publish_attribute_dimension(key)
    return published


def resolve_dimension_identity(
    *,
    predicate: str | None = None,
    dimension: str | None = None,
    predicate_key: str | None = None,
    learn: bool = False,
    value_kind: Literal["text", "number", "year", "date", "concept"] = "text",
) -> DimensionIdentity | None:
    """Map a structured predicate onto a CORE or learned dimension key.

    Exact registry / alias lookup only. Does not substring-match `color` inside
    `fur color`. Does not read raw_input.
    """
    surface = (predicate or dimension or predicate_key or "").strip()
    candidates = [
        (predicate_key or "").strip(),
        (dimension or "").strip(),
        (predicate or "").strip(),
    ]
    for raw in candidates:
        if not raw:
            continue
        identity = _identity_from_token(raw, surface=surface or raw, learn=learn, value_kind=value_kind)
        if identity is not None:
            return identity
    return None


def resolve_claim_dimension(
    claim: SemanticClaim,
    *,
    learn: bool = False,
) -> DimensionIdentity | None:
    kind: Literal["text", "number", "year", "date", "concept"] = "number" if claim.numeric_value else "text"
    return resolve_dimension_identity(
        predicate=claim.predicate,
        dimension=claim.dimension,
        predicate_key=claim.predicate_key,
        learn=learn,
        value_kind=kind,
    )


def claim_attribute_value(claim: SemanticClaim) -> tuple[str | None, str | None, str | None]:
    """Return (text_value, numeric_value, unit). Prefers value_key; never translates."""
    text = (claim.value_key or claim.value_text or "").strip() or None
    numeric = (claim.numeric_value or "").strip() or None
    unit = (claim.unit or "").strip() or None
    return text, numeric, unit


def structured_attribute_claim(
    proposal: SemanticProposal,
    *,
    learn: bool = False,
    require_value: bool = True,
) -> tuple[DimensionIdentity, SemanticClaim] | None:
    for claim in proposal.claims:
        if claim.kind is not SemanticClaimKind.ATTRIBUTE:
            continue
        if claim.origin is not SemanticClaimOrigin.EXPLICIT:
            continue
        identity = resolve_claim_dimension(claim, learn=learn)
        if identity is None:
            continue
        text, numeric, _unit = claim_attribute_value(claim)
        if require_value and text is None and numeric is None:
            continue
        return identity, claim
    return None


def bind_learned_attribute_dimensions(ontology: OntologyRegistry, ir: object) -> None:
    """Register EXTENDED attribute dimensions on the runtime ontology."""
    for key, label in _dimension_keys(ir):
        _bind_one(ontology, key, label=label)


def _identity_from_token(
    raw: str,
    *,
    surface: str,
    learn: bool,
    value_kind: Literal["text", "number", "year", "date", "concept"],
) -> DimensionIdentity | None:
    folded = normalize_expression(raw)
    for token in (raw, raw.lower(), folded):
        if not token:
            continue
        aliased = alias_to_dimension_key(token)
        if aliased and is_registered_dimension(aliased):
            source: Literal["core", "learned"] = (
                "learned" if is_learned_attribute_key(aliased) else "core"
            )
            return DimensionIdentity(
                key=aliased,
                source=source,
                label=surface if source == "learned" else aliased,
                surface=surface,
            )
        if is_registered_dimension(token):
            source = "learned" if is_learned_attribute_key(token) else "core"
            return DimensionIdentity(
                key=token,
                source=source,
                label=surface if source == "learned" else token,
                surface=surface,
            )
        if is_learned_attribute_key(token):
            if learn:
                publish_learned_attribute_dimension(token, label=surface, value_kind=value_kind)
            return DimensionIdentity(
                key=token, source="learned", label=surface, surface=surface
            )

    learned = learned_attribute_key_from_predicate(raw)
    if learned is None:
        return None
    if is_registered_dimension(learned) or learn:
        if learn:
            publish_learned_attribute_dimension(learned, label=surface, value_kind=value_kind)
        return DimensionIdentity(
            key=learned, source="learned", label=surface, surface=surface
        )
    return DimensionIdentity(
        key=learned, source="learned", label=surface, surface=surface
    )


def _dimension_keys(ir: object) -> list[tuple[str, str | None]]:
    found: list[tuple[str, str | None]] = []
    attr = getattr(ir, "attribute", None)
    if attr is not None:
        key = getattr(attr, "dimension_key", None)
        if key:
            found.append((key, None))
    for extra in getattr(ir, "additional_attributes", None) or []:
        key = getattr(extra, "dimension_key", None)
        if key:
            found.append((key, None))
    query = getattr(ir, "query", None)
    if query is not None:
        key = getattr(query, "attribute_dimension_key", None)
        if key:
            found.append((key, None))
    return found


def _bind_one(ontology: OntologyRegistry, key: str | None, *, label: str | None) -> None:
    if not key:
        return
    if ensure_if_learned_attribute(ontology, key):
        spec = get_dimension(key)
        kind = spec.value_kind if spec is not None else "text"
        publish_learned_attribute_dimension(key, label=label, value_kind=kind)
        publish_attribute_dimension(key)
