"""Catálogo treinado (EXTENDED) — lemmas por conceito, revisão humana.

CORE permanece congelado. Verbetes novos entram com id `ext:{key}`.
`extends_core` só acrescenta lemmas a keys já seedadas.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pke.design.behavioral import ConceptMappingType
from pke.domain.ontology import (
    CONCEPT_KEY_PATTERN,
    ConceptKind,
    ConceptPresentation,
    ConceptScope,
    OntologyConcept,
)
from pke.interpretation.semantic.aliases import (
    AliasConstraints,
    ContextualAlias,
    normalize_expression,
)
from pke.interpretation.semantic.models import PrimitiveKind
from pke.ontology.learned import EXTENDED_ID_PREFIX
from pke.ontology.registry import OntologyRegistry
from pke.ontology.seeds import CORE_CREATED_AT, CORE_SEEDS

KindName = Literal["relation_type", "action", "event_type", "entity_type"]

_KIND_MAP: dict[str, ConceptKind] = {
    "relation_type": ConceptKind.RELATION_TYPE,
    "action": ConceptKind.ACTION,
    "event_type": ConceptKind.EVENT_TYPE,
    "entity_type": ConceptKind.ENTITY_TYPE,
}

_PRIMITIVE_MAP: dict[str, PrimitiveKind] = {
    "relation_type": PrimitiveKind.RELATION,
    "action": PrimitiveKind.EVENT,
    "event_type": PrimitiveKind.EVENT,
}

APPROVED_FILENAME = "approved.json"
PROMPT_FILENAME = "TRAINING_PROMPT.md"
_MIN_LEMMA_LEN = 4


def trained_catalog_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "catalog" / "trained"


def approved_catalog_path() -> Path:
    return trained_catalog_dir() / APPROVED_FILENAME


def training_prompt_path() -> Path:
    return trained_catalog_dir() / PROMPT_FILENAME


class TrainedConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_kinds: list[str] = Field(default_factory=list)
    object_kinds: list[str] = Field(default_factory=list)
    require_link_semantics: bool = False
    require_change_semantics: bool = False
    require_condition_semantics: bool = False
    forbid_if_expressions: list[str] = Field(default_factory=list)


class TrainedConcept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=CONCEPT_KEY_PATTERN)
    kind: KindName
    label: str
    meaning: str
    lemmas: list[str] = Field(min_length=1)
    extends_core: bool = False
    event_type_key: str | None = None
    parent_key: str | None = None
    priority: int = 8
    constraints: TrainedConstraints = Field(default_factory=TrainedConstraints)

    @model_validator(mode="after")
    def lemmas_usable(self) -> TrainedConcept:
        cleaned = []
        seen: set[str] = set()
        for raw in self.lemmas:
            norm = normalize_expression(raw)
            if len(norm) < _MIN_LEMMA_LEN:
                raise ValueError(f"lemma too short for {self.key}: {raw!r}")
            if norm in seen:
                continue
            seen.add(norm)
            cleaned.append(raw)
        if not cleaned:
            raise ValueError(f"no usable lemmas for {self.key}")
        self.lemmas = cleaned
        return self


class TrainedCatalogFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    concepts: list[TrainedConcept]

    def by_key(self) -> dict[str, TrainedConcept]:
        return {item.key: item for item in self.concepts}


class CatalogValidationError(ValueError):
    pass


def trained_concept_id(key: str) -> str:
    return f"{EXTENDED_ID_PREFIX}{key}"


@lru_cache(maxsize=4)
def load_trained_catalog(path: str | None = None) -> TrainedCatalogFile:
    target = Path(path) if path else approved_catalog_path()
    payload = json.loads(target.read_text(encoding="utf-8"))
    catalog = TrainedCatalogFile.model_validate(payload)
    problems = validate_trained_catalog(catalog)
    if problems:
        raise CatalogValidationError("; ".join(problems))
    return catalog


def clear_trained_catalog_cache() -> None:
    load_trained_catalog.cache_clear()
    trained_aliases.cache_clear()


def core_keys() -> frozenset[str]:
    return frozenset(seed.key for seed in CORE_SEEDS)


def validate_trained_catalog(catalog: TrainedCatalogFile) -> list[str]:
    """Human-review gate: collisions, CORE freeze, lemma uniqueness."""
    from pke.interpretation.semantic.aliases import SEMANTIC_ALIASES

    problems: list[str] = []
    core = core_keys()
    seen_keys: set[str] = set()
    lemma_owner: dict[str, str] = {}

    for alias in SEMANTIC_ALIASES:
        owner = (
            alias.canonical_key
            or alias.action_key
            or alias.event_type_key
            or alias.attribute_key
            or alias.value_key
            or ""
        )
        if not owner:
            continue
        for expr in alias.expressions:
            lemma_owner.setdefault(expr, owner)

    for item in catalog.concepts:
        if item.key in seen_keys:
            problems.append(f"duplicate catalog key {item.key}")
        seen_keys.add(item.key)
        in_core = item.key in core
        if item.extends_core and not in_core:
            problems.append(f"{item.key} extends_core but is not a CORE key")
        if not item.extends_core and in_core:
            problems.append(f"{item.key} is CORE — use extends_core for extra lemmas")
        if item.kind == "entity_type" and item.lemmas:
            pass
        for raw in item.lemmas:
            norm = normalize_expression(raw)
            owner = lemma_owner.get(norm)
            if owner and owner != item.key:
                problems.append(f"lemma {raw!r} already maps to {owner}")
            lemma_owner[norm] = item.key
        if item.kind not in _KIND_MAP:
            problems.append(f"unknown kind for {item.key}")
        if item.kind == "entity_type" and not item.extends_core:
            pass
        if item.kind in {"action", "event_type"} and item.constraints.require_link_semantics:
            problems.append(f"{item.key} event/action should not require_link_semantics")
    return problems


def _to_ontology_concept(item: TrainedConcept) -> OntologyConcept:
    kind = _KIND_MAP[item.kind]
    return OntologyConcept(
        id=trained_concept_id(item.key),
        key=item.key,
        kind=kind,
        scope=ConceptScope.EXTENDED,
        created_at=CORE_CREATED_AT,
        presentation=ConceptPresentation(label=item.label, description=item.meaning),
    )


def apply_trained_catalog(ontology: OntologyRegistry) -> int:
    """Register approved EXTENDED concepts. Does not mutate CORE."""
    catalog = load_trained_catalog()
    count = 0
    for item in catalog.concepts:
        if item.extends_core:
            continue
        if ontology.get_by_key(item.key) is not None:
            continue
        ontology.register(_to_ontology_concept(item))
        count += 1
    return count


def ensure_if_trained(ontology: OntologyRegistry, key: str) -> bool:
    if not key:
        return False
    catalog = load_trained_catalog()
    item = catalog.by_key().get(key)
    if item is None or item.extends_core:
        return False
    if ontology.get_by_key(key) is not None:
        return True
    ontology.register(_to_ontology_concept(item))
    return True


def is_trained_extended_key(key: str) -> bool:
    item = load_trained_catalog().by_key().get(key)
    return item is not None and not item.extends_core


def trained_hint(key: str) -> str | None:
    item = load_trained_catalog().by_key().get(key)
    if item is None:
        return None
    return item.meaning


def _entry_to_alias(item: TrainedConcept) -> ContextualAlias | None:
    primitive = _PRIMITIVE_MAP.get(item.kind)
    if primitive is None:
        return None
    c = item.constraints
    constraints = AliasConstraints(
        subject_kinds=frozenset(c.subject_kinds),
        object_kinds=frozenset(c.object_kinds),
        require_link_semantics=c.require_link_semantics,
        require_change_semantics=c.require_change_semantics,
        require_condition_semantics=c.require_condition_semantics,
        forbid_if_expressions=frozenset(normalize_expression(x) for x in c.forbid_if_expressions),
    )
    expressions = frozenset(normalize_expression(p) for p in item.lemmas)
    if primitive is PrimitiveKind.RELATION:
        return ContextualAlias(
            ConceptMappingType.CONTEXTUAL_CUE,
            primitive,
            expressions,
            canonical_key=item.key,
            constraints=constraints,
            priority=item.priority,
        )
    return ContextualAlias(
        ConceptMappingType.EVENT_CUE,
        primitive,
        expressions,
        action_key=item.key if item.kind == "action" else None,
        event_type_key=item.event_type_key or (item.key if item.kind == "event_type" else None),
        constraints=constraints,
        priority=item.priority,
    )


@lru_cache(maxsize=1)
def trained_aliases() -> tuple[ContextualAlias, ...]:
    aliases: list[ContextualAlias] = []
    for item in load_trained_catalog().concepts:
        alias = _entry_to_alias(item)
        if alias is not None:
            aliases.append(alias)
    return tuple(aliases)


def lemma_index() -> dict[str, str]:
    """Normalized lemma → canonical key (CORE aliases + trained)."""
    from pke.interpretation.semantic.aliases import SEMANTIC_ALIASES

    index: dict[str, str] = {}
    for alias in SEMANTIC_ALIASES:
        owner = (
            alias.canonical_key
            or alias.action_key
            or alias.event_type_key
            or alias.attribute_key
            or alias.value_key
        )
        if not owner:
            continue
        for expr in alias.expressions:
            index.setdefault(expr, owner)
    for item in load_trained_catalog().concepts:
        for raw in item.lemmas:
            index.setdefault(normalize_expression(raw), item.key)
    return index


def snapshot_for_training_prompt() -> dict[str, Any]:
    core = [
        {"key": seed.key, "kind": seed.kind.value, "label": seed.label}
        for seed in CORE_SEEDS
    ]
    trained = [
        {
            "key": item.key,
            "kind": item.kind,
            "label": item.label,
            "meaning": item.meaning,
            "extends_core": item.extends_core,
            "lemmas": item.lemmas,
        }
        for item in load_trained_catalog().concepts
    ]
    return {
        "core": core,
        "trained": trained,
        "lemmas": lemma_index(),
    }


def render_training_prompt(*, extra_instruction: str = "") -> str:
    template = training_prompt_path().read_text(encoding="utf-8")
    snap = snapshot_for_training_prompt()
    core_txt = json.dumps(snap["core"], ensure_ascii=False, indent=2)
    trained_txt = json.dumps(snap["trained"], ensure_ascii=False, indent=2)
    lemmas_txt = json.dumps(snap["lemmas"], ensure_ascii=False, indent=2)
    filled = (
        template.replace("{{CORE_CATALOG}}", core_txt)
        .replace("{{TRAINED_CATALOG}}", trained_txt)
        .replace("{{LEMMA_INDEX}}", lemmas_txt)
    )
    if extra_instruction.strip():
        filled += "\n\nPedido extra do revisor:\n" + extra_instruction.strip()
    return filled


PROPOSAL_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["catalog_proposal"],
    "properties": {
        "catalog_proposal": {
            "type": "object",
            "additionalProperties": False,
            "required": ["rationale", "concepts"],
            "properties": {
                "rationale": {"type": "string"},
                "concepts": {
                    "type": "array",
                    "maxItems": 25,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["key", "kind", "label", "meaning", "lemmas"],
                        "properties": {
                            "key": {"type": "string"},
                            "kind": {
                                "type": "string",
                                "enum": [
                                    "relation_type",
                                    "action",
                                    "event_type",
                                    "entity_type",
                                ],
                            },
                            "label": {"type": "string"},
                            "meaning": {"type": "string"},
                            "extends_core": {"type": "boolean"},
                            "priority": {"type": "integer"},
                            "lemmas": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                            },
                            "event_type_key": {"type": "string"},
                            "parent_key": {"type": "string"},
                            "constraints": {
                                "type": "object",
                                "properties": {
                                    "subject_kinds": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "object_kinds": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "require_link_semantics": {"type": "boolean"},
                                    "require_change_semantics": {"type": "boolean"},
                                    "require_condition_semantics": {"type": "boolean"},
                                    "forbid_if_expressions": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
    },
}
