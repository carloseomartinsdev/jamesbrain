"""I11.11 — OC1–OC6 ontology coverage fixtures."""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from tests.semantic_resolution.fixtures import (
    ls1_installed_ac,
    px1_installation_service,
    px2_facilities_new,
)


def _happened() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="happened")


def oc1_installed_ac() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Instalei o ar-condicionado.",
        object=SemanticEntityMention(text="ar-condicionado", kind_hint="appliance"),
        action_expression="instalei",
        event_expression="instalei o ar-condicionado",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def oc2_technician_installed_ac() -> SemanticProposal:
    return ls1_installed_ac()


def oc3_installed_program() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Instalei um programa.",
        object=SemanticEntityMention(text="programa", kind_hint="thing"),
        action_expression="instalei",
        event_expression="instalei um programa",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def oc4_replaced_ac() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei o ar-condicionado.",
        object=SemanticEntityMention(text="ar-condicionado", kind_hint="appliance"),
        action_expression="troquei o",
        event_expression="troquei o ar-condicionado",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def oc5_repaired_ac() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Consertei o ar-condicionado.",
        object=SemanticEntityMention(text="ar-condicionado", kind_hint="appliance"),
        action_expression="consertei o",
        event_expression="consertei o ar-condicionado",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def oc6_facilities_new() -> SemanticProposal:
    return px2_facilities_new()


def px1_for_regression() -> SemanticProposal:
    return px1_installation_service()
