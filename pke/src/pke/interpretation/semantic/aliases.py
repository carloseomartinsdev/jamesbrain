"""Registry de aliases contextuais — não é keyword routing sobre raw text."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from pke.design.behavioral import ConceptMappingType
from pke.interpretation.semantic.models import PrimitiveKind


def normalize_expression(text: str) -> str:
    lowered = text.strip().lower()
    normalized = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


@dataclass(frozen=True)
class AliasConstraints:
    subject_kinds: frozenset[str] = frozenset()
    object_kinds: frozenset[str] = frozenset()
    require_change_semantics: bool = False
    require_condition_semantics: bool = False
    require_link_semantics: bool = False
    require_stable_property: bool = False
    forbid_if_expressions: frozenset[str] = frozenset()
    require_event_context: bool = False


@dataclass(frozen=True)
class ContextualAlias:
    mapping_type: ConceptMappingType
    primitive: PrimitiveKind
    expressions: frozenset[str]
    canonical_key: str | None = None
    dimension_key: str | None = None
    value_key: str | None = None
    action_key: str | None = None
    event_type_key: str | None = None
    attribute_key: str | None = None
    domain_keys: tuple[str, ...] = ()
    constraints: AliasConstraints = field(default_factory=AliasConstraints)
    priority: int = 0


def _expr(*parts: str) -> frozenset[str]:
    return frozenset(normalize_expression(p) for p in parts)


SEMANTIC_ALIASES: tuple[ContextualAlias, ...] = (
    # --- Relation ---
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.RELATION,
        _expr("works at", "work at", "trabalha em", "trabalha na", "employed by"),
        canonical_key="relation.employed_by",
        constraints=AliasConstraints(
            subject_kinds=frozenset({"person"}),
            object_kinds=frozenset({"organization"}),
            require_link_semantics=True,
        ),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.RELATION,
        _expr("lives in", "mora em", "resides at", "reside em"),
        canonical_key="relation.resides_at",
        constraints=AliasConstraints(
            subject_kinds=frozenset({"person"}),
            object_kinds=frozenset({"place"}),
            require_link_semantics=True,
        ),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.RELATION,
        _expr("owns", "possui", "is mine", "e meu", "é meu"),
        canonical_key="relation.owns",
        constraints=AliasConstraints(
            subject_kinds=frozenset({"person"}),
            require_link_semantics=True,
        ),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.RELATION,
        _expr(
            "gosta de",
            "gosto de",
            "gostam de",
            "likes",
            "curte",
            "adora",
        ),
        canonical_key="relation.likes",
        constraints=AliasConstraints(
            subject_kinds=frozenset({"person"}),
        ),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.RELATION,
        _expr("married to", "casada com", "casado com", "marriage"),
        canonical_key="relation.married_to",
        constraints=AliasConstraints(
            subject_kinds=frozenset({"person"}),
            object_kinds=frozenset({"person"}),
            require_link_semantics=True,
        ),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.RELATION,
        _expr("parent of", "mae de", "mãe de", "pai de", "parent"),
        canonical_key="relation.parent_of",
        constraints=AliasConstraints(
            subject_kinds=frozenset({"person"}),
            object_kinds=frozenset({"person"}),
            require_link_semantics=True,
        ),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.RELATION,
        _expr("provider for", "cardiologista", "medico", "médico", "provider"),
        canonical_key="relation.provider_for",
        constraints=AliasConstraints(
            subject_kinds=frozenset({"person"}),
            object_kinds=frozenset({"person"}),
            require_link_semantics=True,
        ),
        priority=8,
    ),
    # --- State ---
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.STATE,
        _expr("broken", "quebrada", "quebrado", "broken down"),
        dimension_key="state.operational_condition",
        value_key="state.value.broken",
        constraints=AliasConstraints(require_condition_semantics=True),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.STATE,
        _expr("open", "aberta", "aberto", "is open"),
        dimension_key="state.openness",
        value_key="state.value.open",
        constraints=AliasConstraints(require_condition_semantics=True),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.STATE,
        _expr("overdue", "atrasada", "atrasado", "late bill"),
        dimension_key="state.due_status",
        value_key="state.value.overdue",
        constraints=AliasConstraints(require_condition_semantics=True),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.STATE,
        _expr("depleted", "acabou", "ran out", "empty", "esgotado", "esgotada"),
        dimension_key="state.availability",
        value_key="state.value.depleted",
        constraints=AliasConstraints(require_condition_semantics=True),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.STATE,
        _expr("unemployed", "desempregado", "desempregada"),
        dimension_key="state.availability",
        value_key="state.value.depleted",
        constraints=AliasConstraints(require_condition_semantics=True),
        priority=5,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.STATE,
        _expr("working", "funcionando", "operational"),
        dimension_key="state.operational_condition",
        value_key="state.value.working",
        constraints=AliasConstraints(require_condition_semantics=True),
        priority=9,
    ),
    # CORE seed labels (bounded vocabulary — not a second Interpreter).
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.STATE,
        _expr("fechado", "fechada", "closed"),
        dimension_key="state.openness",
        value_key="state.value.closed",
        constraints=AliasConstraints(require_condition_semantics=True),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.STATE,
        _expr("nao pago", "não pago", "unpaid"),
        dimension_key="state.payment_status",
        value_key="state.value.unpaid",
        constraints=AliasConstraints(require_condition_semantics=True),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.STATE,
        _expr("valido", "válido", "valid"),
        dimension_key="state.validity",
        value_key="state.value.valid",
        constraints=AliasConstraints(require_condition_semantics=True),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.STATE,
        _expr("vencido", "vencida", "expired"),
        dimension_key="state.validity",
        value_key="state.value.expired",
        constraints=AliasConstraints(require_condition_semantics=True),
        priority=10,
    ),
    # --- Attribute (CORE has no color/nationality — prefer UNRESOLVED over wrong key) ---
    # --- Event / Action ---
    ContextualAlias(
        ConceptMappingType.EVENT_CUE,
        PrimitiveKind.EVENT,
        _expr(
            "replace clutch",
            "substitui a embreagem",
            "substituí a embreagem",
            "troquei a embreagem",
            "substituir a embreagem",
            "trocar a embreagem",
        ),
        action_key="action.replace",
        event_type_key="event.vehicle_maintenance",
        domain_keys=("domain.vehicle",),
        constraints=AliasConstraints(
            require_change_semantics=True,
            forbid_if_expressions=frozenset(
                {
                    "troquei ideia",
                    "trocar ideia",
                    "exchange idea",
                    "changed mind",
                    "troquei reais",
                    "trocar reais",
                    "troquei de roupa",
                    "trocar de roupa",
                }
            ),
        ),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.EVENT_CUE,
        PrimitiveKind.EVENT,
        _expr(
            "troquei o",
            "troquei a",
            "trocar o",
            "trocar a",
            "substituí o",
            "substituí a",
            "substitui o",
            "substitui a",
            "replaced the",
            "replace the",
        ),
        action_key="action.replace",
        constraints=AliasConstraints(
            require_change_semantics=True,
            forbid_if_expressions=frozenset(
                {
                    "troquei ideia",
                    "trocar ideia",
                    "exchange idea",
                    "changed mind",
                    "troquei reais",
                    "trocar reais",
                    "troquei de roupa",
                    "trocar de roupa",
                    "instalou",
                    "instalei",
                    "instalações",
                    "instalacoes",
                }
            ),
        ),
        priority=9,
    ),
    ContextualAlias(
        ConceptMappingType.EVENT_CUE,
        PrimitiveKind.EVENT,
        _expr("broke", "quebrou", "break", "failed"),
        event_type_key="event.maintenance",
        constraints=AliasConstraints(require_change_semantics=True),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.EVENT_CUE,
        PrimitiveKind.EVENT,
        _expr("opened", "abriu", "open event"),
        event_type_key="event.maintenance",
        constraints=AliasConstraints(require_change_semantics=True),
        priority=10,
    ),
    ContextualAlias(
        ConceptMappingType.EVENT_CUE,
        PrimitiveKind.EVENT,
        _expr(
            "oil change",
            "trocar oleo",
            "trocar óleo",
            "troquei o oleo",
            "troquei o óleo",
        ),
        action_key="action.oil_change",
        event_type_key="event.vehicle_maintenance",
        domain_keys=("domain.vehicle",),
        constraints=AliasConstraints(require_change_semantics=True),
        priority=11,
    ),
    ContextualAlias(
        ConceptMappingType.EVENT_CUE,
        PrimitiveKind.EVENT,
        _expr(
            "instalou",
            "instalei",
            "instalaram",
            "instalar",
            "installed",
            "install",
            "instalacao",
            "instalação",
            "instalacao do",
            "instalação do",
            "fez a instalacao",
            "fez a instalação",
        ),
        action_key="action.install",
        constraints=AliasConstraints(
            require_change_semantics=True,
            forbid_if_expressions=frozenset(
                {
                    "instalacoes",
                    "instalações",
                    "facilities",
                    "instalacoes da empresa",
                    "instalações da empresa",
                    "sao novas",
                    "são novas",
                }
            ),
        ),
        priority=12,
    ),
    ContextualAlias(
        ConceptMappingType.EVENT_CUE,
        PrimitiveKind.EVENT,
        _expr("consertei", "consertei o", "consertei a", "consertar", "repaired", "repaired the"),
        action_key="action.maintain",
        event_type_key="event.maintenance",
        constraints=AliasConstraints(
            require_change_semantics=True,
            forbid_if_expressions=frozenset(
                {
                    "instalou",
                    "instalei",
                    "troquei",
                    "substitu",
                }
            ),
        ),
        priority=9,
    ),
    # Ideia exchange — explicitly NOT replace
    ContextualAlias(
        ConceptMappingType.CONTEXTUAL_CUE,
        PrimitiveKind.UNKNOWN,
        _expr("exchange idea", "troquei ideia", "trocar ideia", "changed mind"),
        constraints=AliasConstraints(
            forbid_if_expressions=frozenset(),
        ),
        priority=20,
    ),
)


def expression_in_proposal(proposal_text: str | None, *candidates: str) -> bool:
    if not proposal_text:
        return False
    norm = normalize_expression(proposal_text)
    for candidate in candidates:
        if normalize_expression(candidate) in norm or norm in normalize_expression(candidate):
            return True
    return False


def collect_expressions(proposal) -> list[str]:
    parts: list[str] = []
    for field in (
        proposal.action_expression,
        proposal.relation_expression,
        proposal.state_expression,
        proposal.attribute_expression,
        proposal.event_expression,
        proposal.raw_input,
    ):
        if field:
            parts.append(normalize_expression(field))
    return parts


def resolve_state_value_key_from_answer(answer: str) -> str | None:
    """Resolve clarification answer to a CORE state.value key via STATE aliases.

    Exact expression match only (normalized). Ambiguous equal-priority hits → None.
    Does not scan original utterance. Does not invent non-CORE values.
    """
    text = normalize_expression(answer or "")
    if not text:
        return None
    head = text.split(",")[0].strip()
    candidates: list[tuple[int, str, str]] = []
    for alias in SEMANTIC_ALIASES:
        if alias.primitive is not PrimitiveKind.STATE or not alias.value_key:
            continue
        if head in alias.expressions or text in alias.expressions:
            candidates.append((-alias.priority, alias.value_key, min(alias.expressions)))
    if not candidates:
        return None
    candidates.sort()
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0] and candidates[0][1] != candidates[1][1]:
        return None
    return candidates[0][1]
