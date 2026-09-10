"""Fixtures ER1–ER6 — papéis semânticos de Event."""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime


def _happened() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="happened")


def er1_replace_clutch_corolla_implicit() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei a embreagem do Corolla.",
        object=SemanticEntityMention(text="embreagem", kind_hint="thing"),
        entities_mentioned=[SemanticEntityMention(text="Corolla", kind_hint="vehicle")],
        action_expression="troquei a embreagem",
        change_semantics=True,
        event_expression="troquei a embreagem do Corolla",
        primitive_hint="event",
        temporal=_happened(),
    )


def er2_mechanic_replace_clutch_corolla() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O mecânico trocou a embreagem do Corolla.",
        subject=SemanticEntityMention(text="mecânico", kind_hint="person"),
        object=SemanticEntityMention(text="embreagem", kind_hint="thing"),
        entities_mentioned=[SemanticEntityMention(text="Corolla", kind_hint="vehicle")],
        action_expression="troquei a embreagem",
        change_semantics=True,
        event_expression="replace clutch",
        primitive_hint="event",
        temporal=_happened(),
    )


def er3_joao_open_door() -> SemanticProposal:
    return SemanticProposal(
        raw_input="João abriu a porta.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="porta", kind_hint="thing"),
        action_expression="abriu",
        change_semantics=True,
        event_expression="João abriu a porta",
        primitive_hint="event",
        temporal=_happened(),
    )


def er4_door_opened_intransitive() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A porta abriu.",
        subject=SemanticEntityMention(text="porta", kind_hint="thing"),
        change_semantics=True,
        event_expression="porta abriu",
        primitive_hint="event",
        temporal=_happened(),
    )


def er5_technician_install_ac_bedroom() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O técnico instalou o ar-condicionado no quarto.",
        subject=SemanticEntityMention(text="técnico", kind_hint="person"),
        object=SemanticEntityMention(text="ar-condicionado", kind_hint="appliance"),
        entities_mentioned=[SemanticEntityMention(text="quarto", kind_hint="place")],
        action_expression="instalou",
        change_semantics=True,
        event_expression="instalou ar-condicionado no quarto",
        primitive_hint="event",
        temporal=_happened(),
    )


def er6_brought_corolla_workshop() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Levei o Corolla para a oficina.",
        object=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        entities_mentioned=[SemanticEntityMention(text="oficina", kind_hint="place")],
        action_expression="levei",
        change_semantics=True,
        event_expression="levei Corolla para oficina",
        primitive_hint="event",
        temporal=_happened(),
    )
