"""Language-independent Semantic IR — PKE must not reread the utterance."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import UserContext
from pke.interpretation.interpreter import InterpretationContext, discourse_payload
from pke.interpretation.ontology_view import InterpreterOntologyView
from pke.interpretation.prompts import PROMPT_VERSION_V4, build_messages
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.possessive_attribute_repair import SNAPSHOT_EXPRESSION
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir, resolve_query_proposal
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.query.attribute_resolver import AttributeResolutionStatus, resolve_attribute_query
from pke.query.spec import AttributeQueryMode, FactVersionPolicy, SortKey


OPAQUE = "⟨utterance⟩"
NOW = dt.datetime(2026, 9, 10, 12, 0, tzinfo=dt.UTC)


def setup_module() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _vehicle() -> SemanticEntityMention:
    return SemanticEntityMention(
        text="carro",
        kind_hint="vehicle",
        reference_kind="possessive",
        confidence=1.0,
    )


def _actor() -> SemanticEntityMention:
    return SemanticEntityMention(
        text="self",
        kind_hint="person",
        reference_kind="contextual",
        role_hint="actor",
        confidence=1.0,
    )


def _query(**kwargs) -> SemanticProposal:
    body = {
        "raw_input": OPAQUE,
        "utterance_kind": "query",
        "temporal": SemanticTime(),
        "confidence": 1.0,
    }
    body.update(kwargs)
    return SemanticProposal(**body)


def test_discourse_payload_exposes_focus_not_pending_dump() -> None:
    from pke.interpretation.discourse import (
        DiscourseFocus,
        DiscoursePendingIntent,
        DiscourseReferent,
        DiscourseState,
        discourse_prompt_payload,
    )

    state = DiscourseState(
        active_focus=DiscourseFocus(
            entity_ids=["E123"],
            display_name="Casa da Praia",
            target_type="entity.learned.house",
        ),
        recent_referents=[
            DiscourseReferent(
                entity_id="E123",
                display_name="Casa da Praia",
                type_key="entity.learned.house",
            )
        ],
        pending_intent=DiscoursePendingIntent(
            operation="attribute_query",
            attribute_dimension_key="model",
            candidate_entity_ids=["E456"],
            query_dump={"raw_input": "secret-query", "query": {"intent": "attribute"}},
        ),
    )
    payload = discourse_prompt_payload(state, [])
    structured = payload["structured"]
    assert structured["active_focus"]["display_name"] == "Casa da Praia"
    assert structured["pending_intent"]["attribute_dimension_key"] == "model"
    assert "E456" in structured["allowed_entity_ids"]
    blob = str(payload)
    assert "query_dump" not in blob
    assert "secret-query" not in blob
    assert "relation.owns" not in blob


def test_discourse_is_not_a_knowledge_dump() -> None:
    ctx = InterpretationContext(
        user=UserContext(user_id="u", timezone="UTC", now=NOW),
        recent_utterances=["eu tenho carro?", "qual?"],
    )
    payload = discourse_payload(ctx)
    assert payload["recent_user_utterances"] == ["eu tenho carro?", "qual?"]
    assert "structured" in payload
    assert payload["structured"]["allowed_entity_ids"] == []
    view = InterpreterOntologyView.from_registry(OntologyRegistry.with_core_seeds())
    messages = build_messages("qual?", ctx, view, prompt_version=PROMPT_VERSION_V4)
    blob = "\n".join(m.content for m in messages)
    assert "recent_user_utterances" in blob
    assert "eu tenho carro?" in blob
    assert "relation.owns" not in blob  # knowledge keys must not be dumped


def test_case1_possession_query_does_not_need_portuguese() -> None:
    proposal = _query(
        primitive_hint="relation",
        subject=_actor(),
        object=SemanticEntityMention(text="carro", kind_hint="vehicle", confidence=1.0),
        relation_expression="owns",
        link_semantics=True,
    )
    outcome = proposal_to_query_ir(proposal)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    assert outcome.query_ir.query.intent == "relation"
    assert any(r.key == "relation.owns" for r in outcome.query_ir.query.relation_types)


def test_case2_ellipsis_is_complete_ir_not_qual_rule() -> None:
    proposal = _query(
        primitive_hint="relation",
        subject=_actor(),
        object=SemanticEntityMention(text="carro", kind_hint="vehicle", confidence=1.0),
        relation_expression="owns",
        link_semantics=True,
    )
    outcome = resolve_query_proposal(proposal)
    assert outcome.query_ir is not None
    assert "qual" not in (proposal.raw_input or "").lower()


def test_case3_identity_is_snapshot_not_brand_phrase() -> None:
    proposal = _query(
        primitive_hint="attribute",
        subject=_vehicle(),
        attribute_expression=SNAPSHOT_EXPRESSION,
        stable_property_semantics=True,
    )
    outcome = proposal_to_query_ir(proposal)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    assert outcome.query_ir.query.attribute_query_mode == "snapshot"


def test_case4_paint_is_structured_color_write() -> None:
    proposal = SemanticProposal(
        raw_input=OPAQUE,
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=_vehicle(),
        attribute_expression="cor = green",
        stable_property_semantics=True,
        change_semantics=True,
        temporal=SemanticTime(occurrence_aspect="happened"),
        confidence=1.0,
    )
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    assert outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "color"


def test_case5_color_query_ignores_opaque_raw_input() -> None:
    proposal = _query(
        primitive_hint="attribute",
        subject=_vehicle(),
        attribute_expression="cor",
        stable_property_semantics=True,
    )
    outcome = proposal_to_query_ir(proposal)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    assert outcome.query_ir.query.attribute_dimension_key == "color"
    assert outcome.query_ir.query.attribute_query_mode == "value_lookup"
    assert outcome.query_ir.query.version_policy == "current"


def test_case6_previous_state_is_structured_not_antes() -> None:
    proposal = _query(
        primitive_hint="attribute",
        subject=_vehicle(),
        attribute_expression="color",
        stable_property_semantics=True,
        temporal=SemanticTime(selection="previous", relation_to_reference="before"),
    )
    outcome = proposal_to_query_ir(proposal)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    assert outcome.query_ir.query.version_policy == "history"
    assert outcome.query_ir.query.sort == "event_time_desc"
    assert outcome.query_ir.query.limit == 1
    assert "antes" not in (proposal.raw_input or "")


def test_case7_first_selection_is_structured_not_primeira() -> None:
    proposal = _query(
        primitive_hint="attribute",
        subject=_vehicle(),
        attribute_expression="color",
        stable_property_semantics=True,
        temporal=SemanticTime(selection="first"),
    )
    outcome = proposal_to_query_ir(proposal)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    assert outcome.query_ir.query.version_policy == "history"
    assert outcome.query_ir.query.sort == "event_time_asc"
    assert outcome.query_ir.query.limit == 1


@pytest.mark.parametrize(
    "raw",
    (
        "qual a cor do meu carro?",
        "what color is my car?",
        "¿de qué color es mi coche?",
    ),
)
def test_equivalent_languages_converge_on_color_query(raw: str) -> None:
    proposal = _query(
        raw_input=raw,
        primitive_hint="attribute",
        subject=_vehicle(),
        attribute_expression="color",
        stable_property_semantics=True,
    )
    outcome = resolve_query_proposal(proposal)
    assert outcome.query_ir is not None, (raw, outcome.status, outcome.notes)
    assert outcome.query_ir.query.intent == "attribute"
    assert outcome.query_ir.query.attribute_dimension_key == "color"
    assert outcome.query_ir.query.attribute_query_mode == "value_lookup"


def test_ask_module_has_no_portuguese_identity_phrase() -> None:
    source = Path(__file__).resolve().parents[2] / "src" / "pke" / "application" / "ask.py"
    text = source.read_text(encoding="utf-8")
    assert "meu carro" not in text
    assert r"\bqual\b" not in text


def test_historical_lookup_returns_closed_value() -> None:
    closed = EntityAttribute(
        id="attr-closed",
        user_id="u",
        entity_id="e1",
        dimension_key="color",
        value_kind=AttributeValueKind.TEXT,
        text_value="blue",
        temporal=TemporalKnowledge.unknown(),
        observed_at=NOW,
        is_current=False,
    )
    current = EntityAttribute(
        id="attr-current",
        user_id="u",
        entity_id="e1",
        dimension_key="color",
        value_kind=AttributeValueKind.TEXT,
        text_value="green",
        temporal=TemporalKnowledge.unknown(),
        observed_at=NOW,
        is_current=True,
        supersedes_id="attr-closed",
    )
    resolved = resolve_attribute_query(
        [closed, current],
        dimension_key="color",
        mode=AttributeQueryMode.VALUE_LOOKUP,
        version_policy=FactVersionPolicy.HISTORY,
        sort=SortKey.EVENT_TIME_DESC,
        limit=1,
    )
    assert resolved.status is AttributeResolutionStatus.KNOWN_SINGLE
    assert resolved.groups[0].identity.text_value == "blue"
