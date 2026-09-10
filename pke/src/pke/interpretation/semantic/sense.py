"""Reconhecimento de sentido lexical — distinto de conceito canônico."""

from __future__ import annotations

import re
from enum import StrEnum

from pke.interpretation.semantic.aliases import collect_expressions, normalize_expression
from pke.interpretation.semantic.models import SemanticProposal


class SemanticSense(StrEnum):
    INSTALL = "install"
    FACILITIES = "facilities"
    REPLACE_PHYSICAL = "replace_physical"
    EXCHANGE_IDEA = "exchange_idea"
    CURRENCY_EXCHANGE = "currency_exchange"
    CLOTHING_CHANGE = "clothing_change"
    EMPLOYMENT = "employment"
    OPERATIONAL_BROKEN = "operational_broken"
    OPENNESS_OPEN = "openness_open"
    OVERDUE = "overdue"
    DEPLETED = "depleted"
    PROPERTY_NEW = "property_new"
    AMBIGUOUS_PASS = "ambiguous_pass"
    OWNERSHIP = "ownership"
    CLASSIFICATION = "classification"


# Install occurrence — singular installation action, NOT facilities plural
_INSTALL_PATTERNS = (
    r"\binstalacao do\b",
    r"\binstalação do\b",
    r"\binstalacao da\b",
    r"\binstalação da\b",
    r"\bfez a instalacao\b",
    r"\bfez a instalação\b",
    r"\binstalou\b",
    r"\binstalei\b",
    r"\binstalaram\b",
    r"\binstalar\b",
    r"\binstall(ed)?\b",
    r"\binstalacao\b(?!s\b)",
    r"\binstalação\b(?!s\b)",
)

_FACILITIES_PATTERNS = (
    r"\binstalacoes\b",
    r"\binstalações\b",
    r"\bfacilities\b",
    r"\binstalacoes da empresa\b",
    r"\binstalações da empresa\b",
)

_REPLACE_PHYSICAL_PATTERNS = (
    r"\bembreagem\b",
    r"\boleo\b",
    r"\bóleo\b",
    r"\bcomponent\b",
    r"\bpeca\b",
    r"\bpeça\b",
    r"\bsubstitu",
    r"\btroquei a\b",
    r"\btroquei o\b",
    r"\btrocar a\b",
    r"\btrocar o\b",
)

_BLOCK_PATTERNS: dict[SemanticSense, tuple[str, ...]] = {
    SemanticSense.EXCHANGE_IDEA: (
        r"\btroquei ideia\b",
        r"\btrocar ideia\b",
        r"\bexchange idea\b",
        r"\bchanged mind\b",
    ),
    SemanticSense.CURRENCY_EXCHANGE: (
        r"\btroquei reais\b",
        r"\btrocar reais\b",
        r"\bpor dolares\b",
        r"\bpor dólares\b",
        r"\bcurrency exchange\b",
    ),
    SemanticSense.CLOTHING_CHANGE: (
        r"\btroquei de roupa\b",
        r"\btrocar de roupa\b",
        r"\bchanged clothes\b",
    ),
    SemanticSense.PROPERTY_NEW: (
        r"\be nova\b",
        r"\be novo\b",
        r"\bsao novas\b",
        r"\bsão novas\b",
        r"\bsao novos\b",
        r"\bsão novos\b",
        r"\bis new\b",
        r"\bnovas\b",
        r"\bnovo\b",
    ),
    SemanticSense.AMBIGUOUS_PASS: (
        r"\bpassei no\b",
        r"\bpassei em\b",
        r"\bpassed by\b",
    ),
}


def _blob(proposal: SemanticProposal) -> str:
    return " ".join(collect_expressions(proposal))


def _any_pattern(blob: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, blob) for p in patterns)


def recognize_senses(proposal: SemanticProposal) -> frozenset[SemanticSense]:
    blob = _blob(proposal)
    senses: set[SemanticSense] = set()

    if _any_pattern(blob, _FACILITIES_PATTERNS):
        senses.add(SemanticSense.FACILITIES)
    elif _any_pattern(blob, _INSTALL_PATTERNS):
        senses.add(SemanticSense.INSTALL)

    if _any_pattern(blob, _REPLACE_PHYSICAL_PATTERNS) and proposal.change_semantics:
        if SemanticSense.EXCHANGE_IDEA not in senses:
            senses.add(SemanticSense.REPLACE_PHYSICAL)

    for sense, patterns in _BLOCK_PATTERNS.items():
        if _any_pattern(blob, patterns):
            senses.add(sense)

    if proposal.link_semantics and proposal.relation_expression:
        subj = proposal.subject.kind_hint if proposal.subject else None
        obj = proposal.object.kind_hint if proposal.object else None
        rel = normalize_expression(proposal.relation_expression or "")
        if ("trabalh" in rel or "works at" in rel or "employed" in rel) and subj == "person":
            if obj == "organization":
                senses.add(SemanticSense.EMPLOYMENT)

    if proposal.condition_semantics:
        state = normalize_expression(proposal.state_expression or "")
        if any(w in state for w in ("quebrad", "broken", "failed")):
            senses.add(SemanticSense.OPERATIONAL_BROKEN)
        if any(w in state for w in ("abert", "open")):
            senses.add(SemanticSense.OPENNESS_OPEN)
        if any(w in state for w in ("atrasad", "overdue")):
            senses.add(SemanticSense.OVERDUE)
        if any(w in state for w in ("acabou", "depleted", "esgotad")):
            senses.add(SemanticSense.DEPLETED)

    if proposal.stable_property_semantics or SemanticSense.PROPERTY_NEW in senses:
        if SemanticSense.FACILITIES in senses or "nov" in blob:
            senses.add(SemanticSense.PROPERTY_NEW)

    if proposal.link_semantics and any(
        w in normalize_expression(proposal.relation_expression or "")
        for w in ("possui", "owns", "meu", "mine")
    ):
        senses.add(SemanticSense.OWNERSHIP)

    if proposal.classification_semantics:
        senses.add(SemanticSense.CLASSIFICATION)

    return frozenset(senses)


def primary_surface_expression(proposal: SemanticProposal) -> str | None:
    for field in (
        proposal.action_expression,
        proposal.state_expression,
        proposal.attribute_expression,
        proposal.relation_expression,
        proposal.event_expression,
    ):
        if field:
            return field
    return None
