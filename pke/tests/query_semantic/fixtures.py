"""Fixtures determinísticos — I11.9 semantic query resolution."""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from tests.semantic_resolution.fixtures import (
    ambiguity_sao_luiz,
    ls1_installed_ac,
    ls7_exchange_idea,
    pr3_employment,
    sc3_open,
    sc4_replace_clutch,
)


def _happened() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="happened")


def ingest_replace_clutch() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei a embreagem.",
        object=SemanticEntityMention(text="embreagem", kind_hint="vehicle"),
        action_expression="troquei a embreagem",
        change_semantics=True,
        event_expression="troquei a embreagem",
        primitive_hint="event",
        temporal=_happened(),
    )


def ingest_replace_clutch_corolla() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei a embreagem do Corolla.",
        object=SemanticEntityMention(text="embreagem", kind_hint="vehicle"),
        entities_mentioned=[SemanticEntityMention(text="Corolla", kind_hint="vehicle")],
        action_expression="troquei a embreagem",
        change_semantics=True,
        event_expression="troquei a embreagem do Corolla",
        primitive_hint="event",
        temporal=_happened(),
    )


def ingest_replace_oil_corolla() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei o óleo do Corolla.",
        object=SemanticEntityMention(text="óleo"),
        entities_mentioned=[SemanticEntityMention(text="Corolla", kind_hint="vehicle")],
        action_expression="troquei o óleo",
        change_semantics=True,
        event_expression="troquei o óleo",
        primitive_hint="event",
        temporal=_happened(),
    )


def ingest_event_with_type() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei a embreagem.",
        object=SemanticEntityMention(text="embreagem", kind_hint="vehicle"),
        action_expression="troquei a embreagem",
        event_expression="maintenance replace clutch",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
        domain_hints=["domain.vehicle"],
    )


def query_replace_clutch() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Já troquei a embreagem?",
        utterance_kind="query",
        object=SemanticEntityMention(text="embreagem", kind_hint="vehicle"),
        action_expression="troquei a embreagem",
        event_expression="já troquei a embreagem",
        temporal=_happened(),
        primitive_hint="event",
    )


def query_replace_clutch_corolla() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Já troquei a embreagem do Corolla?",
        utterance_kind="query",
        object=SemanticEntityMention(text="embreagem", kind_hint="vehicle"),
        entities_mentioned=[SemanticEntityMention(text="Corolla", kind_hint="vehicle")],
        action_expression="troquei a embreagem",
        event_expression="já troquei a embreagem do Corolla",
        temporal=_happened(),
        primitive_hint="event",
    )


def query_replace_clutch_no_event_type() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Já troquei a embreagem?",
        utterance_kind="query",
        object=SemanticEntityMention(text="embreagem", kind_hint="vehicle"),
        action_expression="replace",
        event_expression="replace clutch",
        temporal=_happened(),
        primitive_hint="event",
    )


def query_maintenance_replace_clutch() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Fiz manutenção trocando a embreagem?",
        utterance_kind="query",
        object=SemanticEntityMention(text="embreagem", kind_hint="vehicle"),
        action_expression="trocando a embreagem",
        event_expression="manutenção trocando embreagem",
        temporal=_happened(),
        primitive_hint="event",
    )


def query_clutch_august() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Troquei a embreagem em agosto?",
        utterance_kind="query",
        object=SemanticEntityMention(text="embreagem", kind_hint="vehicle"),
        action_expression="troquei a embreagem",
        event_expression="troquei a embreagem em agosto",
        temporal=SemanticTime(original_text="agosto", occurrence_aspect="happened", partial_month=8, partial_year=2026),
        primitive_hint="event",
    )


def query_door_open() -> SemanticProposal:
    return SemanticProposal(
        raw_input="A porta está aberta?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="porta"),
        state_expression="open",
        condition_semantics=True,
        primitive_hint="state",
    )


def query_employment() -> SemanticProposal:
    p = pr3_employment()
    return p.model_copy(update={"raw_input": "João trabalha na Acme?", "utterance_kind": "query"})


def query_install_ac() -> SemanticProposal:
    p = ls1_installed_ac()
    return p.model_copy(
        update={
            "raw_input": "Já instalei o ar-condicionado?",
            "utterance_kind": "query",
            "temporal": _happened(),
        }
    )


def query_exchange_idea() -> SemanticProposal:
    p = ls7_exchange_idea()
    return p.model_copy(update={"raw_input": "Já troquei ideia com João?", "utterance_kind": "query"})


def query_ambiguous_pass() -> SemanticProposal:
    return ambiguity_sao_luiz().model_copy(
        update={"raw_input": "Passei no São Luiz?", "utterance_kind": "query"}
    )


def ingest_door_open() -> SemanticProposal:
    return sc3_open()


def ingest_employment() -> SemanticProposal:
    return pr3_employment()
