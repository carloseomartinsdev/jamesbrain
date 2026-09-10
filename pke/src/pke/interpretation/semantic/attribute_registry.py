"""Controlled Attribute Dimension Registry (E1.2).

LLM proposals never register dimensions. Only this registry authorizes materialization.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class AttributeDimensionTier(StrEnum):
    CORE_V1 = "core_v1"
    EVERYDAY_E1 = "everyday_e1"


@dataclass(frozen=True)
class AttributeDimensionSpec:
    key: str
    value_kind: Literal["text", "number", "year", "date", "concept"]
    aliases: tuple[str, ...]
    tier: AttributeDimensionTier
    subject_kind_hints: frozenset[str] | None = None
    """If set, preferred subject kinds (soft constraint for resolvers)."""
    privacy_class: Literal["normal", "sensitive"] = "normal"
    materializable: bool = True
    queryable: bool = True
    unit_required: bool = False
    singleton_current: bool = False
    """When True, a new is_current write closes prior current rows for the same dimension."""


def _spec(
    key: str,
    value_kind: Literal["text", "number", "year", "date", "concept"],
    aliases: tuple[str, ...],
    *,
    tier: AttributeDimensionTier,
    subject_kind_hints: frozenset[str] | None = None,
    privacy_class: Literal["normal", "sensitive"] = "normal",
    unit_required: bool = False,
    singleton_current: bool = False,
) -> AttributeDimensionSpec:
    return AttributeDimensionSpec(
        key=key,
        value_kind=value_kind,
        aliases=aliases,
        tier=tier,
        subject_kind_hints=subject_kind_hints,
        privacy_class=privacy_class,
        unit_required=unit_required,
        singleton_current=singleton_current,
    )


# Static controlled catalog — no runtime mutation / adaptive learning.
ATTRIBUTE_DIMENSION_REGISTRY: tuple[AttributeDimensionSpec, ...] = (
    # --- v1 core write dimensions ---
    _spec(
        "color",
        "text",
        ("cor", "color", "cores", "colour", "colours"),
        tier=AttributeDimensionTier.CORE_V1,
        singleton_current=True,
    ),
    _spec(
        "model_year",
        "year",
        ("ano", "ano do carro", "ano do veiculo", "model year", "model_year", "year"),
        tier=AttributeDimensionTier.CORE_V1,
        subject_kind_hints=frozenset({"vehicle", "automobile"}),
    ),
    _spec(
        "weight",
        "number",
        ("peso", "weight", "pesa"),
        tier=AttributeDimensionTier.CORE_V1,
        unit_required=True,
    ),
    _spec(
        "height",
        "number",
        ("altura", "height"),
        tier=AttributeDimensionTier.CORE_V1,
        unit_required=True,
    ),
    _spec(
        "area",
        "number",
        ("area", "área", "metros quadrados", "metro quadrado", "m2", "m²"),
        tier=AttributeDimensionTier.CORE_V1,
        unit_required=True,
    ),
    _spec(
        "capacity",
        "number",
        ("capacidade", "capacity", "capacidade do tanque"),
        tier=AttributeDimensionTier.CORE_V1,
        unit_required=True,
    ),
    # --- E1.2 everyday ---
    _spec(
        "name",
        "text",
        ("nome", "name", "chamo", "chama"),
        tier=AttributeDimensionTier.EVERYDAY_E1,
        subject_kind_hints=frozenset({"person"}),
        privacy_class="sensitive",
        singleton_current=True,
    ),
    _spec(
        "brand",
        "text",
        ("marca", "brand"),
        tier=AttributeDimensionTier.EVERYDAY_E1,
        subject_kind_hints=frozenset({"vehicle", "automobile"}),
        singleton_current=True,
    ),
    _spec(
        "model",
        "text",
        ("modelo", "model"),
        tier=AttributeDimensionTier.EVERYDAY_E1,
        subject_kind_hints=frozenset({"vehicle", "automobile"}),
        singleton_current=True,
    ),
)

_BY_KEY: dict[str, AttributeDimensionSpec] = {s.key: s for s in ATTRIBUTE_DIMENSION_REGISTRY}

_ALIAS_TO_KEY: dict[str, str] = {}
for _spec_row in ATTRIBUTE_DIMENSION_REGISTRY:
    _ALIAS_TO_KEY[_spec_row.key] = _spec_row.key
    for _alias in _spec_row.aliases:
        _ALIAS_TO_KEY[_alias] = _spec_row.key


def get_dimension(key: str) -> AttributeDimensionSpec | None:
    return _BY_KEY.get(key)


def is_registered_dimension(key: str) -> bool:
    spec = _BY_KEY.get(key)
    return spec is not None and spec.materializable


def alias_to_dimension_key(alias: str) -> str | None:
    """Map normalized alias → dimension key. Unknown → None (never invent)."""
    return _ALIAS_TO_KEY.get(alias)


def dimension_alias_map() -> dict[str, str]:
    """Copy of alias→key for resolvers (read-only use)."""
    return dict(_ALIAS_TO_KEY)


def registered_dimension_keys() -> frozenset[str]:
    return frozenset(_BY_KEY.keys())
