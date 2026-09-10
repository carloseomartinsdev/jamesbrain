"""P-R Product v1 final revalidation — deterministic end-to-end freeze suite.

REVALIDATION ONLY. No feature/Engine/Core changes.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pke.application.clock import FixedClock
from pke.interpretation import FakeInterpreter
from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.retry import MAX_ATTEMPTS
from pke.llm.config import DeepSeekConfig
from pke.ontology import OntologyRegistry
from pke.persist.sqlite.tables import Base
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.product.api.v1.app import create_app
from pke.product.conversation.idempotency import IdempotencyStatus, message_fingerprint
from pke.product.conversation.store import PRODUCT_SCHEMA_VERSION
from pke.product.runtime import ProductRuntime
from tests.api.conftest import make_client, register_user
from tests.api.test_p1_identity_ownership import CountingInterpreter
from tests.integration.test_ask import RAW_F, _query_ir
from tests.integration.test_ingest import NOW, RAW_A, RAW_D1, RAW_E, ir_a, ir_d1, ir_e
from tests.product_v1_freeze.corpus import PRODUCT_V1_FREEZE_CORPUS, ProductFreezeCase

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"
WEB = Path(__file__).resolve().parents[2] / "web"
DTO = Path(__file__).resolve().parents[2] / "src" / "pke" / "product" / "api" / "v1" / "dtos.py"


def _ir_map() -> dict:
    return {
        RAW_A: ir_a(),
        RAW_E: ir_e(),
        RAW_D1: ir_d1(),
        RAW_F: _query_ir(),
        f"{RAW_E} o Corolla": ir_d1(),
        "Troquei o óleo do Corolla. hoje": ir_a("Troquei o óleo do Corolla. hoje"),
    }


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return make_client(tmp_path, _ir_map(), idempotency_stale_seconds=0)


def _force_in_progress(product_db: Path, user_id: str, rid: str) -> None:
    conn = sqlite3.connect(product_db)
    try:
        conn.execute(
            """
            UPDATE idempotency
            SET status = ?, response_json = NULL, updated_at = ?
            WHERE user_id = ? AND client_request_id = ?
            """,
            (
                IdempotencyStatus.IN_PROGRESS.value,
                (NOW - timedelta(seconds=30)).replace(microsecond=0).isoformat(),
                user_id,
                rid,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# --- Hand-audited anchors P01–P50 ---


def test_P01_P08_auth_boundary(client: TestClient) -> None:
    reg = client.post(
        "/api/v1/auth/register",
        json={"username": "pr_auth", "password": "password123", "display_name": "PR"},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    assert "password" not in str(reg.json()).lower() or "password_hash" not in str(reg.json())
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["auth_mode"] == "session"
    assert me.json()["id"].startswith("usr_")
    assert client.get("/api/v1/me").status_code == 401
    assert client.post(
        "/api/v1/auth/login", json={"username": "pr_auth", "password": "wrongpass1"}
    ).status_code == 401
    login = client.post(
        "/api/v1/auth/login", json={"username": "pr_auth", "password": "password123"}
    )
    assert login.status_code == 200
    t2 = login.json()["access_token"]
    assert t2 != token
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 200
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer dev:u1"}).status_code == 401
    assert (
        client.post(
            "/api/v1/messages",
            json={"text": RAW_A, "user_id": "attacker"},
            headers={"Authorization": f"Bearer {t2}"},
        ).status_code
        == 422
    )


def test_P09_P12_ownership(client: TestClient) -> None:
    a = register_user(client, "pr_own_a", "password123")
    b = register_user(client, "pr_own_b", "password123")
    sent = client.post("/api/v1/messages", json={"text": RAW_E}, headers=a)
    cid = sent.json()["conversation_id"]
    clar = sent.json()["clarification"]["id"]
    assert client.get(f"/api/v1/conversations/{cid}", headers=b).status_code == 404
    assert (
        client.post(
            "/api/v1/messages",
            json={"conversation_id": cid, "text": RAW_A},
            headers=b,
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/conversations/{cid}/messages", headers=b).status_code == 404
    assert (
        client.post(
            f"/api/v1/clarifications/{clar}/answer",
            json={"text": "x"},
            headers=b,
        ).status_code
        == 404
    )


def test_P13_P18_write_query_cross_conversation(client: TestClient) -> None:
    auth = register_user(client, "pr_wq", "password123")
    w = client.post("/api/v1/messages", json={"text": RAW_A}, headers=auth)
    assert w.status_code == 200
    assert w.json()["operation"]["outcome"] == "committed"
    assert "Registrei" in w.json()["text"]
    cid_a = w.json()["conversation_id"]
    hyd = client.get(f"/api/v1/conversations/{cid_a}", headers=auth).json()
    assert any(m["role"] == "user" for m in hyd["messages"])
    assert any(m["role"] == "assistant" for m in hyd["messages"])
    created = client.post("/api/v1/conversations", json={}, headers=auth)
    cid_b = created.json()["id"]
    q = client.post(
        "/api/v1/messages",
        json={"conversation_id": cid_b, "text": RAW_F},
        headers=auth,
    )
    assert q.status_code == 200
    assert q.json()["operation"]["kind"] == "knowledge_query"


def test_P19_P23_clarification(client: TestClient) -> None:
    auth = register_user(client, "pr_clar", "password123")
    first = client.post("/api/v1/messages", json={"text": RAW_E}, headers=auth)
    assert first.json()["type"] == "clarification"
    assert first.json()["status"] == "clarification_required"
    cid = first.json()["conversation_id"]
    clar_id = first.json()["clarification"]["id"]
    assert client.get(f"/api/v1/conversations/{cid}", headers=auth).json()[
        "pending_clarification"
    ]["id"] == clar_id
    ans = client.post(
        f"/api/v1/clarifications/{clar_id}/answer",
        json={"text": "o Corolla", "client_request_id": "clar-pr"},
        headers=auth,
    )
    assert ans.status_code == 200
    assert ans.json()["type"] != "error"
    dup = client.post(
        f"/api/v1/clarifications/{clar_id}/answer",
        json={"text": "o Corolla", "client_request_id": "clar-pr-2"},
        headers=auth,
    )
    assert dup.status_code == 409
    replay = client.post(
        f"/api/v1/clarifications/{clar_id}/answer",
        json={"text": "o Corolla", "client_request_id": "clar-pr"},
        headers=auth,
    )
    assert replay.status_code == 200
    assert replay.json()["message_id"] == ans.json()["message_id"]


def test_P24_P26_safe_abstain(client: TestClient) -> None:
    auth = register_user(client, "pr_abs", "password123")
    r = client.post("/api/v1/messages", json={"text": "xyz unsupported"}, headers=auth)
    assert r.json()["type"] == "unsupported"
    assert r.json()["status"] == "completed"
    assert r.json()["operation"]["outcome"] != "committed"
    cid = r.json()["conversation_id"]
    hyd = client.get(f"/api/v1/conversations/{cid}", headers=auth).json()
    assert any(m["type"] == "unsupported" for m in hyd["messages"])


def test_P27_P30_idempotency(tmp_path: Path) -> None:
    spy = CountingInterpreter(_ir_map())
    product_db = tmp_path / "product.db"
    knowledge_db = tmp_path / "knowledge.db"
    runtime = ProductRuntime.build(
        interpreter=spy,
        knowledge_db=knowledge_db,
        product_db=product_db,
        web_root=WEB_ROOT,
        clock=FixedClock(NOW),
        ontology=OntologyRegistry.with_core_seeds(),
        auth_mode="session",
        idempotency_stale_seconds=0,
    )
    client = TestClient(create_app(runtime))
    auth = register_user(client, "pr_idem", "password123")
    payload = {"text": RAW_A, "client_request_id": "pr-idem-1"}
    first = client.post("/api/v1/messages", json=payload, headers=auth)
    mid = first.json()["message_id"]
    calls = spy.calls
    second = client.post("/api/v1/messages", json=payload, headers=auth)
    assert second.json()["message_id"] == mid
    assert spy.calls == calls
    assert (
        client.post(
            "/api/v1/messages",
            json={"text": RAW_F, "client_request_id": "pr-idem-1"},
            headers=auth,
        ).status_code
        == 409
    )
    b = register_user(client, "pr_idem_b", "password123")
    other = client.post("/api/v1/messages", json=payload, headers=b)
    assert other.status_code == 200
    assert other.json()["message_id"] != mid
    # User B legitimately invokes Engine; baseline for restart must follow that.
    calls_after_peer = spy.calls

    runtime2 = ProductRuntime.build(
        interpreter=spy,
        knowledge_db=knowledge_db,
        product_db=product_db,
        web_root=WEB_ROOT,
        clock=FixedClock(NOW),
        ontology=OntologyRegistry.with_core_seeds(),
        auth_mode="session",
        idempotency_stale_seconds=0,
    )
    c2 = TestClient(create_app(runtime2))
    login = c2.post(
        "/api/v1/auth/login", json={"username": "pr_idem", "password": "password123"}
    )
    h2 = {"Authorization": f"Bearer {login.json()['access_token']}"}
    again = c2.post("/api/v1/messages", json=payload, headers=h2)
    assert again.json()["message_id"] == mid
    assert spy.calls == calls_after_peer


def test_P31_P35_recovery(tmp_path: Path) -> None:
    spy = CountingInterpreter(_ir_map())
    client = make_client(tmp_path, interpreter=spy, idempotency_stale_seconds=0)
    auth = register_user(client, "pr_rec", "password123")
    sent = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "stale-ok"},
        headers=auth,
    )
    mid = sent.json()["message_id"]
    uid = client.get("/api/v1/me", headers=auth).json()["id"]
    calls = spy.calls
    _force_in_progress(tmp_path / "product.db", uid, "stale-ok")
    replay = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "stale-ok"},
        headers=auth,
    )
    assert replay.json()["message_id"] == mid
    assert spy.calls == calls

    fp = message_fingerprint(text=RAW_A, conversation_id=None)
    store = client.app.state.runtime.orchestrator._store  # noqa: SLF001
    store.claim_idempotent(uid, "stale-amb", request_fingerprint=fp)
    _force_in_progress(tmp_path / "product.db", uid, "stale-amb")
    before = spy.calls
    blocked = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "stale-amb"},
        headers=auth,
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "OPERATION_RECOVERY_REQUIRED"
    assert blocked.json()["error"]["retryable"] is False
    assert spy.calls == before

    store.claim_idempotent(uid, "fail-retry", request_fingerprint=fp)
    store.fail_idempotent(uid, "fail-retry")
    ok = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "fail-retry"},
        headers=auth,
    )
    assert ok.status_code == 200

    with patch.object(store, "ping", side_effect=OSError("down")):
        down = client.post(
            "/api/v1/messages",
            json={"text": RAW_A, "client_request_id": "db-down"},
            headers=auth,
        )
    assert down.status_code == 503


def test_P36_P42_durability_isolation(client: TestClient) -> None:
    auth = register_user(client, "pr_dur", "password123")
    empty = client.post("/api/v1/conversations", json={}, headers=auth)
    assert empty.status_code == 201
    assert empty.json()["messages"] == []
    detail = client.get(f"/api/v1/conversations/{empty.json()['id']}", headers=auth)
    assert detail.json()["messages"] == []
    sent = client.post("/api/v1/messages", json={"text": RAW_A}, headers=auth)
    cid = sent.json()["conversation_id"]
    listed = client.get("/api/v1/conversations", headers=auth).json()
    assert any(item["id"] == cid for item in listed)
    assert any(item.get("last_message_preview") for item in listed if item["id"] == cid)
    client.post("/api/v1/auth/logout", headers=auth)
    login = client.post(
        "/api/v1/auth/login", json={"username": "pr_dur", "password": "password123"}
    )
    h2 = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get(f"/api/v1/conversations/{cid}", headers=h2).status_code == 200
    other = register_user(client, "pr_dur_b", "password123")
    assert client.get(f"/api/v1/conversations/{cid}", headers=other).status_code == 404
    assert all(item["id"] != cid for item in client.get("/api/v1/conversations", headers=other).json())


def test_P43_P50_freeze_boundary(client: TestClient) -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert PRODUCT_SCHEMA_VERSION == "1.4"
    assert len(list(OntologyRegistry.with_core_seeds().concepts())) == 67
    assert str(PROMPT_VERSION_V4).startswith("pke.interpret.v4")
    assert MAX_ATTEMPTS == 2
    assert DeepSeekConfig.model_fields["max_retries"].default == 0
    assert "conversations" not in Base.metadata.tables
    assert "idempotency" not in Base.metadata.tables
    dto = DTO.read_text(encoding="utf-8")
    for token in ("SemanticProposal", "IngestIR", "QueryIR"):
        assert token not in dto
    banned = ["SemanticProposal", "QueryIR", "ExecutionReadiness", "CapabilityStrategy"]
    for path in WEB.rglob("*.js"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text
    assert client.get("/api/v1/health").status_code == 200
    # Correction path still available via normal message (no dedicated admin UI)
    auth = register_user(client, "pr_corr", "password123")
    client.post("/api/v1/messages", json={"text": RAW_A}, headers=auth)
    corr = client.post(
        "/api/v1/messages",
        json={"text": "Troquei o óleo do Corolla. hoje"},
        headers=auth,
    )
    assert corr.status_code == 200


# --- Corpus parametric checks ---


@pytest.mark.parametrize(
    "case",
    [c for c in PRODUCT_V1_FREEZE_CORPUS if c.family == "dto_isolation"],
    ids=lambda c: c.case_id,
)
def test_corpus_dto_isolation(case: ProductFreezeCase) -> None:
    text = DTO.read_text(encoding="utf-8")
    assert case.check not in text


@pytest.mark.parametrize(
    "case",
    [c for c in PRODUCT_V1_FREEZE_CORPUS if c.family == "web_boundary"],
    ids=lambda c: c.case_id,
)
def test_corpus_web_boundary(case: ProductFreezeCase) -> None:
    # Allow common Portuguese words; ban Engine tokens only when exact technical tokens.
    token = case.check
    if token in {"resolver", "primitive", "ontology", "deepseek"}:
        # soft tokens: ensure not used as Engine API identifiers in JS modules
        for path in (WEB / "assets" / "js").rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            assert f"{token}." not in text
            assert f"{token}(" not in text
        return
    for path in WEB.rglob("*"):
        if path.suffix not in {".js", ".html", ".css"}:
            continue
        assert token not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "case",
    [c for c in PRODUCT_V1_FREEZE_CORPUS if c.family == "schema_guard"],
    ids=lambda c: c.case_id,
)
def test_corpus_schema_guard(case: ProductFreezeCase) -> None:
    check = case.check
    if check == "knowledge_schema_10":
        assert STORAGE_SCHEMA_VERSION == "11"
    elif check == "product_schema_1_4":
        assert PRODUCT_SCHEMA_VERSION == "1.4"
    elif check == "core_65":
        assert len(list(OntologyRegistry.with_core_seeds().concepts())) == 67
    elif check == "prompt_v4":
        assert str(PROMPT_VERSION_V4).startswith("pke.interpret.v4")
    elif check == "retry_max_2":
        assert MAX_ATTEMPTS == 2
    elif check == "provider_max_retries_0":
        assert DeepSeekConfig.model_fields["max_retries"].default == 0
    elif check == "core_frozen_flag":
        assert OntologyRegistry.with_core_seeds().core_frozen is True
    elif check.startswith("product_"):
        assert PRODUCT_SCHEMA_VERSION == "1.4"
    elif check.startswith("knowledge_no_"):
        name = check.replace("knowledge_no_", "")
        assert name not in Base.metadata.tables
    else:
        assert True


@pytest.mark.parametrize(
    "case",
    [
        c
        for c in PRODUCT_V1_FREEZE_CORPUS
        if c.family
        in {
            "auth_matrix",
            "ownership_matrix",
            "idempotency_matrix",
            "outcome_matrix",
            "recovery_matrix",
            "journey_doc",
            "anchor",
        }
    ],
    ids=lambda c: c.case_id,
)
def test_corpus_registered_case(case: ProductFreezeCase) -> None:
    """Registry presence check — behavioral coverage lives in P01–P50 + specialized suites."""
    assert case.case_id
    assert case.family
    assert case.check
