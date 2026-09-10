"""T1–T10 transport normalization and semantic assessment tests."""

from __future__ import annotations

import json

import pytest

from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.semantic.envelope_dispatch import ProviderRoute, dispatch_provider_payload
from pke.interpretation.semantic.proposal_assessment import SemanticActionability, assess_semantic_proposal
from pke.interpretation.semantic.proposal_normalizer import NormalizationCategory, normalize_raw_provider_output
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.ontology import OntologyRegistry


def _valid_envelope() -> str:
    return json.dumps(
        {
            "ir_kind": "semantic_proposal",
            "ir": {
                "raw_input": "João trabalha na Acme.",
                "subject": {"text": "João", "kind_hint": "person"},
                "object": {"text": "Acme", "kind_hint": "organization"},
                "relation_expression": "trabalha na",
                "link_semantics": True,
            },
        }
    )


def test_t1_valid_semantic_envelope() -> None:
    result = normalize_raw_provider_output(_valid_envelope())
    assert result.ok
    assert result.success is not None
    env = WireSemanticEnvelope.parse_json(_valid_envelope())
    assert env.ir_kind == "semantic_proposal"


def test_t2_fenced_json() -> None:
    raw = "```json\n" + _valid_envelope() + "\n```"
    result = normalize_raw_provider_output(raw)
    assert result.ok
    assert NormalizationCategory.MARKDOWN_FENCE in result.success.categories  # type: ignore[union-attr]
    env = WireSemanticEnvelope.parse_json(raw)
    assert env.ir_kind == "semantic_proposal"


def test_t3_json_with_harmless_wrapper() -> None:
    raw = "Aqui está a proposta:\n" + _valid_envelope()
    result = normalize_raw_provider_output(raw)
    assert result.ok
    env = WireSemanticEnvelope.parse_json(raw)
    assert env.ir_kind == "semantic_proposal"


def test_t4_flat_semantic_proposal() -> None:
    flat = json.dumps(
        {
            "raw_input": "João trabalha na Acme.",
            "primitive_hint": "relation",
            "subject": {"text": "João", "kind_hint": "person"},
            "object": {"text": "Acme", "kind_hint": "organization"},
            "relation_expression": "trabalha na",
            "link_semantics": True,
        }
    )
    result = normalize_raw_provider_output(flat)
    assert result.ok
    assert NormalizationCategory.FLAT_PROPOSAL in result.success.categories  # type: ignore[union-attr]
    dispatched = dispatch_provider_payload(flat)
    assert dispatched.route is ProviderRoute.SEMANTIC_V3


def test_t5_enum_casing_drift() -> None:
    payload = json.loads(_valid_envelope())
    payload["ir_kind"] = "SEMANTIC_PROPOSAL"
    payload["ir"]["primitive_hint"] = "RELATION"
    raw = json.dumps(payload)
    result = normalize_raw_provider_output(raw)
    assert result.ok
    assert result.success.payload["ir_kind"] == "semantic_proposal"


def test_t6_malformed_json() -> None:
    result = normalize_raw_provider_output("{ not json")
    assert not result.ok
    assert result.failure is not None
    assert result.failure.category is NormalizationCategory.MALFORMED_JSON


def test_t7_unrelated_json() -> None:
    result = normalize_raw_provider_output(json.dumps({"foo": "bar"}))
    assert not result.ok or dispatch_provider_payload(json.dumps({"foo": "bar"})).route is ProviderRoute.INVALID


def test_drops_unknown_llm_fields() -> None:
    raw = json.dumps(
        {
            "ir_kind": "semantic_proposal",
            "ir": {
                "raw_input": "o ano do meu carro é 2008",
                "primitive_hint": "attribute",
                "stable_property_semantics": True,
                "attribute_expression": "ano 2008",
                "subject": {"text": "carro", "kind_hint": "vehicle"},
                "entity_attribute_value": {"year": 2008},
            },
        }
    )
    result = normalize_raw_provider_output(raw)
    assert result.ok and result.success is not None
    ir = result.success.payload["ir"]
    assert "entity_attribute_value" not in ir
    env = WireSemanticEnvelope.model_validate(result.success.payload)
    assert env.parsed_proposal().attribute_expression == "ano 2008"


def test_t8_structurally_valid_semantically_empty() -> None:
    raw = json.dumps({"ir_kind": "semantic_proposal", "ir": {"raw_input": "algo"}})
    env = WireSemanticEnvelope.parse_json(raw)
    assessment = assess_semantic_proposal(env.parsed_proposal())
    assert assessment.status is SemanticActionability.INSUFFICIENT


def test_t9_contradictory_semantic_signals() -> None:
    raw = json.dumps(
        {
            "ir_kind": "semantic_proposal",
            "ir": {
                "raw_input": "x",
                "primitive_hint": "attribute",
                "change_semantics": True,
                "stable_property_semantics": False,
                "attribute_expression": "x",
                "subject": {"text": "a", "kind_hint": "thing"},
            },
        }
    )
    env = WireSemanticEnvelope.parse_json(raw)
    assessment = assess_semantic_proposal(env.parsed_proposal())
    assert assessment.status is SemanticActionability.CONTRADICTORY


def test_t10_canonical_v2_output() -> None:
    v2 = json.dumps(
        {
            "ir_kind": "ingest",
            "ir": {
                "intent": "record_state",
                "raw_input": "A geladeira está quebrada.",
                "state": {"value": "state.value.broken", "dimension": "state.operational_condition"},
            },
        }
    )
    dispatched = dispatch_provider_payload(v2)
    assert dispatched.route is ProviderRoute.V2_CANONICAL
    assert dispatched.v2_compat_fallback is True


def test_insufficient_raises_proposal_semantics_not_wire() -> None:
    from pke.interpretation.prompts import PROMPT_VERSION_V3
    from tests.unit.test_deepseek_interpreter import StubProvider, _ctx

    empty = json.dumps({"ir_kind": "semantic_proposal", "ir": {"raw_input": "teste vazio"}})
    interpreter = DeepSeekInterpreter(
        StubProvider(empty),
        OntologyRegistry.with_core_seeds(),
        prompt_version=PROMPT_VERSION_V3,
    )
    with pytest.raises(InterpretationError, match="proposal_semantics:insufficient"):
        interpreter.interpret("teste vazio", _ctx())
    assert interpreter.last_raw_content == empty


def test_ontology_gap_raises_semantic_resolution_not_keyerror() -> None:
    from pke.interpretation.prompts import PROMPT_VERSION_V3
    from tests.unit.test_deepseek_interpreter import StubProvider, _ctx

    # facilities + property_new remains an ontology gap (I11.11 deferred)
    facilities = json.dumps(
        {
            "ir_kind": "semantic_proposal",
            "ir": {
                "raw_input": "As instalações da empresa são novas.",
                "subject": {"text": "instalações", "kind_hint": "organization"},
                "attribute_expression": "novas",
                "stable_property_semantics": True,
                "primitive_hint": "attribute",
            },
        }
    )
    interpreter = DeepSeekInterpreter(
        StubProvider(facilities),
        OntologyRegistry.with_core_seeds(),
        prompt_version=PROMPT_VERSION_V3,
    )
    with pytest.raises(InterpretationError, match="semantic_resolution:"):
        interpreter.interpret("As instalações da empresa são novas.", _ctx())


def test_llm_possessive_and_present_are_accepted() -> None:
    """Provider ficha uses a wider lexicon than the old wire Literals."""
    attempt1 = json.dumps(
        {
            "ir_kind": "semantic_query",
            "ir": {
                "raw_input": "qual é o meu carro?",
                "utterance_kind": "query",
                "primitive_hint": "type",
                "subject": {
                    "text": "meu carro",
                    "kind_hint": "vehicle",
                    "reference_kind": "possessive",
                },
                "classification_semantics": True,
                "attribute_expression": "qual é",
                "temporal": {},
                "confidence": 0.9,
            },
        }
    )
    result = normalize_raw_provider_output(attempt1)
    assert result.ok and result.success is not None
    ir = result.success.payload["ir"]
    assert ir["subject"]["reference_kind"] == "possessive"
    env = WireSemanticEnvelope.parse_json(attempt1)
    proposal = env.parsed_query_proposal()
    assert proposal.subject is not None
    assert proposal.subject.reference_kind == "possessive"
    assert proposal.subject.kind_hint == "vehicle"

    attempt2 = json.dumps(
        {
            "ir_kind": "semantic_query",
            "ir": {
                "raw_input": "qual é o meu carro?",
                "utterance_kind": "query",
                "primitive_hint": "relation",
                "subject": {
                    "text": "eu",
                    "kind_hint": "person",
                    "reference_kind": "contextual",
                },
                "object": {"text": "carro", "kind_hint": "vehicle"},
                "relation_expression": "possuir",
                "link_semantics": True,
                "temporal": {"original_text": "", "occurrence_aspect": "present"},
            },
        }
    )
    env2 = WireSemanticEnvelope.parse_json(attempt2)
    proposal2 = env2.parsed_query_proposal()
    assert proposal2.temporal.occurrence_aspect == "ongoing"
    assert proposal2.relation_expression == "possuir"


def test_possessive_type_query_translates_to_snapshot() -> None:
    from pke.interpretation.semantic.possessive_attribute_repair import SNAPSHOT_EXPRESSION
    from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
    from pke.interpretation.semantic.self_repair import apply_e1_self_repairs
    from pke.interpretation.transport.catalog import ConceptCatalog

    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    raw = json.dumps(
        {
            "ir_kind": "semantic_query",
            "ir": {
                "raw_input": "qual é o meu carro?",
                "utterance_kind": "query",
                "primitive_hint": "type",
                "subject": {
                    "text": "meu carro",
                    "kind_hint": "vehicle",
                    "reference_kind": "possessive",
                },
                "classification_semantics": True,
                "attribute_expression": "qual é",
                "temporal": {},
            },
        }
    )
    proposal = apply_e1_self_repairs(WireSemanticEnvelope.parse_json(raw).parsed_query_proposal())
    assert proposal.primitive_hint == "attribute"
    assert proposal.attribute_expression == SNAPSHOT_EXPRESSION
    assert proposal.subject is not None
    assert proposal.subject.text == "carro"
    assert proposal.subject.reference_kind == "possessive"
    outcome = proposal_to_query_ir(proposal)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    assert outcome.query_ir.query.attribute_query_mode == "snapshot"
