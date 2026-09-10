"""P2 — Conversation application lifecycle & durable interaction state."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.api.conftest import make_client, register_user
from tests.api.test_p1_identity_ownership import CountingInterpreter
from tests.integration.test_ask import RAW_F, _query_ir
from tests.integration.test_ingest import RAW_A, RAW_E, ir_a, ir_e


def _client(tmp_path: Path, responses: dict | None = None, interpreter=None) -> TestClient:
    mapping = {
        RAW_A: ir_a(),
        RAW_E: ir_e(),
        RAW_F: _query_ir(),
    }
    if responses:
        mapping.update(responses)
    return make_client(tmp_path, mapping, interpreter=interpreter)


def test_empty_and_new_conversation(tmp_path: Path) -> None:
    client = _client(tmp_path)
    auth = register_user(client, "life_a", "password123")
    created = client.post("/api/v1/conversations", json={}, headers=auth)
    assert created.status_code == 201
    body = created.json()
    assert body["id"].startswith("conv_")
    assert body["messages"] == []
    assert body["pending_clarification"] is None
    detail = client.get(f"/api/v1/conversations/{body['id']}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["messages"] == []


def test_message_reload_hydration(tmp_path: Path) -> None:
    client = _client(tmp_path)
    auth = register_user(client, "life_b", "password123")
    sent = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "hyd-1"},
        headers=auth,
    )
    assert sent.status_code == 200
    cid = sent.json()["conversation_id"]
    assert sent.json()["operation"]["outcome"] == "committed"
    assert sent.json()["user_message_id"]

    hydrated = client.get(f"/api/v1/conversations/{cid}", headers=auth)
    assert hydrated.status_code == 200
    data = hydrated.json()
    assert len(data["messages"]) >= 2
    roles = [m["role"] for m in data["messages"]]
    assert "user" in roles and "assistant" in roles
    assert data["pending_clarification"] is None
    assert data["last_message_preview"]


def test_idempotent_retry_no_duplicate_engine(tmp_path: Path) -> None:
    spy = CountingInterpreter({RAW_A: ir_a()})
    client = _client(tmp_path, interpreter=spy)
    auth = register_user(client, "life_c", "password123")
    payload = {"text": RAW_A, "client_request_id": "idem-1"}
    first = client.post("/api/v1/messages", json=payload, headers=auth)
    assert first.status_code == 200
    mid = first.json()["message_id"]
    calls = spy.calls
    second = client.post("/api/v1/messages", json=payload, headers=auth)
    assert second.status_code == 200
    assert second.json()["message_id"] == mid
    assert spy.calls == calls


def test_idempotency_key_payload_conflict(tmp_path: Path) -> None:
    client = _client(tmp_path)
    auth = register_user(client, "life_d", "password123")
    client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "same-key"},
        headers=auth,
    )
    conflict = client.post(
        "/api/v1/messages",
        json={"text": RAW_F, "client_request_id": "same-key"},
        headers=auth,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_clarification_survives_reload_and_answers_once(tmp_path: Path) -> None:
    client = _client(tmp_path)
    auth = register_user(client, "life_e", "password123")
    first = client.post("/api/v1/messages", json={"text": RAW_E}, headers=auth)
    assert first.status_code == 200
    assert first.json()["type"] == "clarification"
    cid = first.json()["conversation_id"]
    clar_id = first.json()["clarification"]["id"]

    hydrated = client.get(f"/api/v1/conversations/{cid}", headers=auth)
    assert hydrated.json()["pending_clarification"]["id"] == clar_id

    answered = client.post(
        f"/api/v1/clarifications/{clar_id}/answer",
        json={"text": "o Corolla", "client_request_id": "clar-ans-1"},
        headers=auth,
    )
    assert answered.status_code == 200

    dup = client.post(
        f"/api/v1/clarifications/{clar_id}/answer",
        json={"text": "o Corolla", "client_request_id": "clar-ans-2"},
        headers=auth,
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "CLARIFICATION_ANSWERED"

    replay = client.post(
        f"/api/v1/clarifications/{clar_id}/answer",
        json={"text": "o Corolla", "client_request_id": "clar-ans-1"},
        headers=auth,
    )
    assert replay.status_code == 200
    assert replay.json()["message_id"] == answered.json()["message_id"]


def test_logout_login_preserves_conversation(tmp_path: Path) -> None:
    client = _client(tmp_path)
    reg = client.post(
        "/api/v1/auth/register",
        json={"username": "life_f", "password": "password123"},
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    sent = client.post("/api/v1/messages", json={"text": RAW_A}, headers=headers)
    cid = sent.json()["conversation_id"]
    client.post("/api/v1/auth/logout", headers=headers)
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "life_f", "password": "password123"},
    )
    headers2 = {"Authorization": f"Bearer {login.json()['access_token']}"}
    listed = client.get("/api/v1/conversations", headers=headers2)
    assert any(item["id"] == cid for item in listed.json())
    detail = client.get(f"/api/v1/conversations/{cid}", headers=headers2)
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) >= 2


def test_multi_session_same_user_reads(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post(
        "/api/v1/auth/register",
        json={"username": "life_g", "password": "password123"},
    )
    a = client.post(
        "/api/v1/auth/login",
        json={"username": "life_g", "password": "password123"},
    ).json()["access_token"]
    b = client.post(
        "/api/v1/auth/login",
        json={"username": "life_g", "password": "password123"},
    ).json()["access_token"]
    ha = {"Authorization": f"Bearer {a}"}
    hb = {"Authorization": f"Bearer {b}"}
    sent = client.post("/api/v1/messages", json={"text": RAW_A}, headers=ha)
    cid = sent.json()["conversation_id"]
    assert client.get(f"/api/v1/conversations/{cid}", headers=hb).status_code == 200


def test_knowledge_survives_new_conversation(tmp_path: Path) -> None:
    client = _client(tmp_path)
    auth = register_user(client, "life_h", "password123")
    client.post("/api/v1/messages", json={"text": RAW_A}, headers=auth)
    created = client.post("/api/v1/conversations", json={}, headers=auth)
    cid_b = created.json()["id"]
    ask = client.post(
        "/api/v1/messages",
        json={"conversation_id": cid_b, "text": RAW_F},
        headers=auth,
    )
    assert ask.status_code == 200
    assert ask.json()["operation"]["kind"] == "knowledge_query"


def test_engine_failure_no_false_commit(tmp_path: Path) -> None:
    client = make_client(tmp_path, {})
    auth = register_user(client, "life_i", "password123")
    r = client.post("/api/v1/messages", json={"text": "sem ir"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "unsupported"
    assert body.get("operation", {}).get("outcome") != "committed"
    cid = body["conversation_id"]
    msgs = client.get(f"/api/v1/conversations/{cid}", headers=auth).json()["messages"]
    assert any(m["role"] == "user" for m in msgs)
    assert any(m["role"] == "assistant" for m in msgs)


def test_safe_abstain_durable(tmp_path: Path) -> None:
    client = make_client(tmp_path, {})
    auth = register_user(client, "life_j", "password123")
    r = client.post("/api/v1/messages", json={"text": "xyz unsupported"}, headers=auth)
    cid = r.json()["conversation_id"]
    hydrated = client.get(f"/api/v1/conversations/{cid}", headers=auth).json()
    assert any(m["type"] == "unsupported" for m in hydrated["messages"])


def test_cross_user_lifecycle_blocked(tmp_path: Path) -> None:
    client = _client(tmp_path)
    a = register_user(client, "life_k", "password123")
    b = register_user(client, "life_l", "password123")
    sent = client.post("/api/v1/messages", json={"text": RAW_E}, headers=a)
    cid = sent.json()["conversation_id"]
    clar = sent.json()["clarification"]["id"]
    assert client.get(f"/api/v1/conversations/{cid}", headers=b).status_code == 404
    assert (
        client.post(
            f"/api/v1/clarifications/{clar}/answer",
            json={"text": "x"},
            headers=b,
        ).status_code
        == 404
    )
