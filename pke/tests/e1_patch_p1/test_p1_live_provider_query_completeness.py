"""E1 Patch P1 — Live Provider Query Completeness (self-name).

Preserves captured incomplete provider proposals that failed Beta.
No live DeepSeek in default pytest.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.ask_results import AskStatus
from pke.application.clock import FixedClock
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import InterpretationContext
from pke.interpretation.models import QueryIR
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.proposal_assessment import (
    SemanticActionability,
    assess_semantic_proposal,
)
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.semantic.self_repair import apply_e1_self_repairs
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_uow
from pke.product.api.v1.app import create_app
from pke.product.conversation.engine_gateway import EngineGateway, TurnCachedInterpreter
from pke.product.runtime import ProductRuntime
from pke.resolution.context import PersonalContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW
from tests.interpreter_retry.fakes import ScriptedProvider
from tests.interpreter_retry.test_interpreter_retry_i122 import _interpreter
from fastapi.testclient import TestClient

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"


# Captured Beta-shape (anon): missing attribute cues → was INSUFFICIENT without P1 repair.
def live_gap_qual_meu_nome() -> dict:
    return {
        "ir_kind": "semantic_query",
        "ir": {
            "raw_input": "qual é o meu nome?",
            "utterance_kind": "query",
            "subject": {"text": "meu", "kind_hint": "person"},
            "primitive_hint": "unknown",
            "temporal": {"original_text": ""},
        },
    }


def live_gap_como_me_chamo() -> dict:
    return {
        "ir_kind": "semantic_query",
        "ir": {
            "raw_input": "como me chamo?",
            "utterance_kind": "query",
            "primitive_hint": "unknown",
            "entities_mentioned": [],
            "temporal": {"original_text": ""},
        },
    }


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = "u-p1") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-p1") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _ctx(uid: str = "u-p1") -> InterpretationContext:
    return InterpretationContext(user=_user(uid))


POSITIVE_RAW = [
    "Qual é o meu nome?",
    "qual é o meu nome?",
    "Qual meu nome?",
    "Como me chamo?",
    "como me chamo?",
    "Como eu me chamo?",
    "Você sabe meu nome?",
]

NEGATIVE_RAW = [
    "Qual é o nome do João?",
    "Como o nome do usuário é armazenado?",
    "Meu amigo não sabe meu nome.",
    "Qual é o nome do meu carro?",
    "O nome do meu amigo é João.",
]


@pytest.mark.parametrize("raw", POSITIVE_RAW)
def test_p1_repair_positives(raw: str) -> None:
    weak = SemanticProposal(
        raw_input=raw,
        utterance_kind="query",
        primitive_hint="unknown",
        subject=SemanticEntityMention(text="meu", kind_hint="person"),
        temporal=SemanticTime(),
        confidence=0.5,
    )
    assert assess_semantic_proposal(weak).status is SemanticActionability.INSUFFICIENT
    repaired = apply_e1_self_repairs(weak)
    assessment = assess_semantic_proposal(repaired)
    assert assessment.status is SemanticActionability.ACTIONABLE
    assert repaired.primitive_hint == "attribute"
    assert repaired.stable_property_semantics is True
    assert repaired.subject is not None
    assert repaired.subject.reference_kind == "contextual"
    assert "nome" in (repaired.attribute_expression or "").lower()
    outcome = proposal_to_query_ir(repaired)
    assert outcome.query_ir is not None
    assert isinstance(outcome.query_ir, QueryIR)


@pytest.mark.parametrize("raw", NEGATIVE_RAW)
def test_p1_repair_negatives(raw: str) -> None:
    weak = SemanticProposal(
        raw_input=raw,
        utterance_kind="query",
        primitive_hint="unknown",
        temporal=SemanticTime(),
        confidence=0.5,
    )
    repaired = apply_e1_self_repairs(weak)
    # Must not become principal.name attribute query
    if repaired.attribute_expression and repaired.subject is not None:
        is_self_name = (
            repaired.primitive_hint == "attribute"
            and repaired.subject.reference_kind == "contextual"
            and repaired.subject.text in {"eu", "me"}
            and "nome" in (repaired.attribute_expression or "").lower()
            and "carro" not in (repaired.attribute_expression or "").lower()
        )
        # Negatives must not get the whitelist repair shape from weak unknown proposal
        assert not (
            is_self_name
            and assess_semantic_proposal(repaired).status is SemanticActionability.ACTIONABLE
            and weak.primitive_hint == "unknown"
            and not weak.attribute_expression
        ), f"false repair on {raw!r}"


def test_p1_fixture_provider_path_emits_query_ir() -> None:
    interp = _interpreter(ScriptedProvider([live_gap_qual_meu_nome()]))
    result = interp.interpret("qual é o meu nome?", _ctx())
    assert isinstance(result, QueryIR)


def test_p1_fixture_como_me_chamo_emits_query_ir() -> None:
    interp = _interpreter(ScriptedProvider([live_gap_como_me_chamo()]))
    result = interp.interpret("como me chamo?", _ctx())
    assert isinstance(result, QueryIR)


def test_p1_engine_gateway_ask_path(tmp_path: Path) -> None:
    """Product EngineGateway: incomplete provider proposal → QueryIR → Ask."""
    from pke.application.ask import AskService
    from pke.application.ingest import IngestService
    from pke.interpretation import FakeInterpreter
    from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
    from pke.persist import open_sqlite_read_store

    db = fresh_db_path(tmp_path, "p1-gw")
    user = _user()
    write = SemanticProposal(
        raw_input="Meu nome é Carlos.",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="Carlos", kind_hint="person", reference_kind="named", confidence=1.0
        ),
        attribute_expression="name is Carlos",
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    outcome = proposal_to_canonical_ir(write)
    assert outcome.ir is not None
    ingest = IngestService(
        FakeInterpreter({write.raw_input: outcome.ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    committed = ingest.ingest(write.raw_input, user, _session())
    assert committed.status is IngestStatus.COMMITTED

    live_interp = _interpreter(ScriptedProvider([live_gap_qual_meu_nome()]))
    cached = TurnCachedInterpreter(live_interp)
    ask = AskService(
        cached,
        OntologyRegistry.with_core_seeds(),
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    gateway = EngineGateway(cached, ingest, ask)
    turn = gateway.process("qual é o meu nome?", user, _session())
    assert turn.interpretation_error is None
    assert turn.ask is not None
    assert turn.ask.status is AskStatus.ANSWERED
    assert turn.ask.query_result is not None
    values = turn.ask.query_result.attribute_values
    assert values and values[0].text_value == "Carlos"


def test_p1_product_api_cross_conversation(tmp_path: Path) -> None:
    """POST /api/v1/messages — write then new conversation query via provider fixture path."""
    from pke.interpretation import FakeInterpreter
    from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
    from tests.api.conftest import register_user

    write = SemanticProposal(
        raw_input="Meu nome é Carlos.",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="Carlos", kind_hint="person", reference_kind="named", confidence=1.0
        ),
        attribute_expression="name is Carlos",
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    write_ir = proposal_to_canonical_ir(write).ir
    assert write_ir is not None

    class HybridInterpreter:
        def __init__(self) -> None:
            self._write = FakeInterpreter({"Meu nome é Carlos.": write_ir})
            self._query = _interpreter(
                ScriptedProvider(
                    [
                        live_gap_qual_meu_nome(),
                        live_gap_como_me_chamo(),
                    ]
                )
            )

        def interpret(self, raw: str, ctx: InterpretationContext):
            if raw == "Meu nome é Carlos.":
                return self._write.interpret(raw, ctx)
            return self._query.interpret(raw, ctx)

    runtime = ProductRuntime.build(
        interpreter=HybridInterpreter(),  # type: ignore[arg-type]
        knowledge_db=tmp_path / "k.db",
        product_db=tmp_path / "p.db",
        web_root=WEB_ROOT,
        clock=FixedClock(NOW),
        auth_mode="session",
        debug_ui=False,
    )
    client = TestClient(create_app(runtime))
    h = register_user(client, "p1user", "password123", display_name="P1")

    conv_a = client.post("/api/v1/conversations", json={"title": "A"}, headers=h)
    assert conv_a.status_code in {200, 201}
    id_a = conv_a.json()["id"]
    w = client.post(
        "/api/v1/messages",
        json={"text": "Meu nome é Carlos.", "conversation_id": id_a},
        headers=h,
    )
    assert w.status_code == 200
    assert w.json()["operation"]["outcome"] == "committed"

    conv_b = client.post("/api/v1/conversations", json={"title": "B"}, headers=h)
    assert conv_b.status_code in {200, 201}
    id_b = conv_b.json()["id"]
    q1 = client.post(
        "/api/v1/messages",
        json={"text": "qual é o meu nome?", "conversation_id": id_b},
        headers=h,
    )
    assert q1.status_code == 200
    body1 = q1.json()
    assert body1["operation"]["kind"] == "knowledge_query"
    assert body1["type"] == "answer"
    assert "Carlos" in body1["text"] or (
        body1.get("data") and "Carlos" in str(body1["data"])
    )

    conv_c = client.post("/api/v1/conversations", json={"title": "C"}, headers=h)
    assert conv_c.status_code in {200, 201}
    id_c = conv_c.json()["id"]
    q2 = client.post(
        "/api/v1/messages",
        json={"text": "como me chamo?", "conversation_id": id_c},
        headers=h,
    )
    assert q2.status_code == 200
    body2 = q2.json()
    assert body2["operation"]["kind"] == "knowledge_query"
    assert "Carlos" in body2["text"] or (
        body2.get("data") and "Carlos" in str(body2["data"])
    )


def test_p1_presenter_interpretation_error_neutral() -> None:
    from pke.interpretation.interpreter import InterpretationError
    from pke.product.conversation.engine_gateway import EngineTurn
    from pke.product.conversation.presenter import present_turn

    resp = present_turn(
        EngineTurn(interpretation_error=InterpretationError("proposal_semantics:insufficient")),
        conversation_id="c1",
        client_request_id=None,
        request_id="req_x",
        entity_label=lambda *_a, **_k: "x",
        user_id="u1",
    )
    assert resp.operation.kind.value == "none"
    assert "registrar" not in resp.text.lower()
    assert "segurança" in resp.text.lower() or "seguranca" in resp.text.lower()
