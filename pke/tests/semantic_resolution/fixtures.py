"""Fixtures determinísticos — simulam SemanticProposal do LLM."""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime


def _ongoing() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="ongoing")


def _happened() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="happened")


def pr1_fridge_broken() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A geladeira está quebrada.",
        subject=SemanticEntityMention(text="geladeira", kind_hint="appliance"),
        state_expression="broken",
        condition_semantics=True,
        primitive_hint="state",
    )


def pr2_fridge_broke() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A geladeira quebrou.",
        subject=SemanticEntityMention(text="geladeira", kind_hint="appliance"),
        state_expression="broke",
        change_semantics=True,
        event_expression="broke",
        primitive_hint="event",
        temporal=_happened(),
    )


def pr3_employment() -> SemanticProposal:
    return SemanticProposal(
        raw_input="João trabalha na Acme.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="Acme", kind_hint="organization"),
        relation_expression="trabalha na",
        link_semantics=True,
        primitive_hint="relation",
        temporal=_ongoing(),
    )


def pr4_color() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O Corolla é prata.",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="prata",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def pr5_door_open() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A porta está aberta.",
        subject=SemanticEntityMention(text="porta", kind_hint="thing"),
        state_expression="open",
        condition_semantics=True,
        primitive_hint="state",
    )


def pr6_door_opened() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A porta abriu.",
        subject=SemanticEntityMention(text="porta", kind_hint="thing"),
        change_semantics=True,
        event_expression="opened",
        primitive_hint="event",
        temporal=_happened(),
    )


def sc1_employment() -> SemanticProposal:
    return pr3_employment()


def sc2_broken() -> SemanticProposal:
    return pr1_fridge_broken()


def sc3_open() -> SemanticProposal:
    return pr5_door_open()


def sc4_replace_clutch() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei a embreagem.",
        action_expression="troquei",
        change_semantics=True,
        event_expression="replace clutch",
        primitive_hint="event",
        temporal=_happened(),
    )


def sc5_substitute_clutch() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Substituí a embreagem.",
        action_expression="substituí",
        change_semantics=True,
        event_expression="substitute",
        primitive_hint="event",
        temporal=_happened(),
    )


def sc6_overdue() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A conta está atrasada.",
        subject=SemanticEntityMention(text="conta", kind_hint="document"),
        state_expression="atrasada",
        condition_semantics=True,
        primitive_hint="state",
    )


def px1_installation_service() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O técnico fez a instalação do ar.",
        subject=SemanticEntityMention(text="técnico", kind_hint="person"),
        action_expression="instalação",
        event_expression="fez a instalação",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def px2_facilities_new() -> SemanticProposal:
    return SemanticProposal(
        raw_input="As instalações da empresa são novas.",
        subject=SemanticEntityMention(text="instalações", kind_hint="organization"),
        attribute_expression="novas",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def px3_replace_clutch() -> SemanticProposal:
    return sc4_replace_clutch()


def px4_exchange_idea() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei ideia com João.",
        action_expression="troquei ideia",
        change_semantics=False,
        link_semantics=False,
        primitive_hint="event",
    )


def ambiguity_sao_luiz() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Passei no São Luiz.",
        action_expression="passei",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


# --- LS1–LS11 lexical sense fixtures ---


def ls1_installed_ac() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O técnico instalou o ar-condicionado.",
        subject=SemanticEntityMention(text="técnico", kind_hint="person"),
        object=SemanticEntityMention(text="ar-condicionado", kind_hint="appliance"),
        action_expression="instalou",
        event_expression="instalou ar-condicionado",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def ls2_installation_service() -> SemanticProposal:
    return px1_installation_service()


def ls3_installation_yesterday() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A instalação do ar foi ontem.",
        subject=SemanticEntityMention(text="instalação", kind_hint="thing"),
        event_expression="instalação do ar",
        change_semantics=True,
        primitive_hint="event",
        temporal=SemanticTime(original_text="ontem", occurrence_aspect="happened"),
    )


def ls4_facilities_new() -> SemanticProposal:
    return px2_facilities_new()


def ls5_replace_clutch() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei a embreagem.",
        action_expression="troquei a embreagem",
        change_semantics=True,
        event_expression="troquei a embreagem",
        primitive_hint="event",
        temporal=_happened(),
    )


def ls6_substitute_clutch() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Substituí a embreagem.",
        action_expression="substituí a embreagem",
        change_semantics=True,
        event_expression="substituí a embreagem",
        primitive_hint="event",
        temporal=_happened(),
    )


def ls7_exchange_idea() -> SemanticProposal:
    return px4_exchange_idea()


def ls8_currency_exchange() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei reais por dólares.",
        action_expression="troquei reais",
        change_semantics=True,
        event_expression="troquei reais por dólares",
        primitive_hint="event",
        temporal=_happened(),
    )


def ls9_clothing_change() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei de roupa.",
        action_expression="troquei de roupa",
        change_semantics=True,
        event_expression="troquei de roupa",
        primitive_hint="event",
        temporal=_happened(),
    )


def ls10_passed_sao_luiz() -> SemanticProposal:
    return ambiguity_sao_luiz()


def ls11_shopping_context() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Passei no São Luiz.",
        action_expression="passei",
        subject=SemanticEntityMention(text="São Luiz", kind_hint="place"),
        change_semantics=True,
        domain_hints=["domain.shopping"],
        primitive_hint="event",
        temporal=_happened(),
    )


# --- State / relation safety ---


def state_fridge_new() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A geladeira é nova.",
        subject=SemanticEntityMention(text="geladeira", kind_hint="appliance"),
        attribute_expression="nova",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def state_door_new() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A porta é nova.",
        subject=SemanticEntityMention(text="porta", kind_hint="thing"),
        attribute_expression="nova",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def relation_motor_works() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O motor trabalha em alta rotação.",
        subject=SemanticEntityMention(text="motor", kind_hint="thing"),
        relation_expression="trabalha em alta rotação",
        link_semantics=True,
        primitive_hint="relation",
        temporal=_ongoing(),
    )
