from __future__ import annotations

import json
from pathlib import Path

from pke.debug.request_log import append_stage, safe_file_id
from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.llm import LlmCallMetadata, LlmStructuredRequest, LlmStructuredResponse
from pke.ontology import OntologyRegistry
from pke.product.conversation.engine_gateway import EngineGateway, TurnCachedInterpreter
from pke.application.session import SessionContext
from pke.resolution.context import PersonalContext
import datetime as dt
from zoneinfo import ZoneInfo


def test_safe_file_id_strips_path_chars() -> None:
    assert safe_file_id("../a/b") == "a_b"
    assert safe_file_id("a1dbc55727c8c5957f296a954044ab18") == "a1dbc55727c8c5957f296a954044ab18"
    assert safe_file_id("  ") is None


def test_append_stage_writes_named_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PKE_REQUEST_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("PKE_REQUEST_LOG", "1")
    path = append_stage(
        "abc123",
        "llm_response",
        '{"ir_kind":"semantic_proposal"}',
        user_text="meu nome é carlos",
        attempt=1,
    )
    assert path is not None
    assert path.name.endswith("_abc123.log")
    assert path.name[:14].isdigit()
    assert path.name[14] == "_"
    text = path.read_text(encoding="utf-8")
    assert "stage=llm_response" in text
    assert "meu nome é carlos" in text
    assert '"ir_kind": "semantic_proposal"' in text
    again_path = append_stage("abc123", "llm_response", '{"ok":true}', attempt=2)
    assert again_path == path
    again = path.read_text(encoding="utf-8")
    assert again.count("stage=llm_response") == 2


class _Stub:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def generate_structured(self, request: LlmStructuredRequest) -> LlmStructuredResponse:
        return LlmStructuredResponse(
            content=json.dumps(self.payload),
            metadata=LlmCallMetadata(
                provider="stub", model="stub", request_id="stub-1", latency_ms=1
            ),
        )


def test_interpreter_logs_stages_after_llm(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PKE_REQUEST_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("PKE_REQUEST_LOG", "1")
    payload = {
        "ir_kind": "semantic_proposal",
        "ir": {
            "raw_input": "João trabalha na Acme.",
            "subject": {"text": "João", "kind_hint": "person"},
            "object": {"text": "Acme", "kind_hint": "organization"},
            "relation_expression": "trabalha na",
            "link_semantics": True,
        },
    }
    now = dt.datetime(2026, 9, 1, 15, 0, tzinfo=ZoneInfo("America/Fortaleza"))
    ctx = InterpretationContext(
        user=UserContext(user_id="u1", timezone="America/Fortaleza", now=now),
        client_request_id="req-log-stages",
    )
    DeepSeekInterpreter(
        _Stub(payload),
        OntologyRegistry.with_core_seeds(),
        prompt_version=PROMPT_VERSION_V4,
    ).interpret("João trabalha na Acme.", ctx)
    files = list(tmp_path.glob("*_req-log-stages.log"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    for stage in (
        "llm_response",
        "normalize",
        "proposal",
        "repair",
        "assessment",
        "canonical",
    ):
        assert f"stage={stage}" in text, stage
    assert "trabalha na" in text
    assert "routed_primitive" in text
    assert "stage=engine" not in text


def test_append_stage_truncation_is_explicit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PKE_REQUEST_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("PKE_REQUEST_LOG", "1")
    huge = {"blob": "x" * 80_000}
    path = append_stage("trunc-1", "canonical", huge)
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "truncated: true" in text
    assert "original_size:" in text
    assert "logged_size:" in text
    assert "…[truncated]" not in text


def test_interpreter_logs_claims_when_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PKE_REQUEST_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("PKE_REQUEST_LOG", "1")
    payload = {
        "ir_kind": "semantic_proposal",
        "ir": {
            "raw_input": "OPAQUE-claims-1",
            "subject": {"text": "Luna", "kind_hint": "unknown", "reference_kind": "named"},
            "object": {"text": "self", "kind_hint": "person", "reference_kind": "contextual"},
            "relation_expression": "owns",
            "link_semantics": True,
            "claims": [
                {
                    "kind": "classification",
                    "subject": {"text": "Luna", "reference_kind": "named"},
                    "class_hint": "cat",
                    "origin": "explicit",
                    "confidence": 1.0,
                },
                {
                    "kind": "relation",
                    "subject": {"text": "self", "reference_kind": "contextual"},
                    "predicate": "owns",
                    "object": {"text": "Luna", "reference_kind": "named"},
                    "origin": "explicit",
                },
            ],
        },
    }
    now = dt.datetime(2026, 9, 1, 15, 0, tzinfo=ZoneInfo("America/Fortaleza"))
    ctx = InterpretationContext(
        user=UserContext(user_id="u1", timezone="America/Fortaleza", now=now),
        client_request_id="req-claims",
    )
    DeepSeekInterpreter(
        _Stub(payload),
        OntologyRegistry.with_core_seeds(),
        prompt_version=PROMPT_VERSION_V4,
    ).interpret("OPAQUE-claims-1", ctx)
    text = next(tmp_path.glob("*_req-claims.log")).read_text(encoding="utf-8")
    assert "stage=claims" in text
    assert '"claim_id": "c1"' in text
    assert '"kind": "classification"' in text
    assert "stage=canonical" in text
    assert "OPAQUE-claims-1" in text


def test_insufficient_omits_engine_stage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PKE_REQUEST_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("PKE_REQUEST_LOG", "1")

    class BoomInterpreter:
        def interpret(self, raw: str, ctx: InterpretationContext):
            raise InterpretationError("proposal_semantics:insufficient:subject")

    class StubIngest:
        def ingest(self, *a, **k):
            raise AssertionError("ingest must not run")

    class StubAsk:
        def ask(self, *a, **k):
            raise AssertionError("ask must not run")

    gw = EngineGateway(
        TurnCachedInterpreter(BoomInterpreter()),  # type: ignore[arg-type]
        StubIngest(),  # type: ignore[arg-type]
        StubAsk(),  # type: ignore[arg-type]
    )
    user = UserContext(user_id="u1", timezone="America/Fortaleza")
    session = SessionContext(personal=PersonalContext(user_id="u1"))
    turn = gw.process(
        "???",
        user,
        session,
        client_request_id="req-insufficient",
        pke_request_id="pke-insufficient",
    )
    assert turn.interpretation_error is not None
    files = list(tmp_path.glob("*_req-insufficient.log"))
    if files:
        text = files[0].read_text(encoding="utf-8")
        assert "stage=engine" not in text
        assert "stage=entity_resolution" not in text
        assert "stage=materialization" not in text
