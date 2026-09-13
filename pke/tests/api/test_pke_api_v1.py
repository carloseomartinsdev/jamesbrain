from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pke.interpretation.interpreter import InterpretationError
from pke.llm.errors import LlmProviderError
from pke.ontology import OntologyRegistry
from pke.persist.sqlite.tables import Base
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.product.conversation.store import PRODUCT_SCHEMA_VERSION
from tests.api.conftest import make_client, register_user
from tests.integration.test_ask import RAW_F
from tests.integration.test_ingest import RAW_A, RAW_D1, RAW_E


class ProviderDown:
    def interpret(self, raw: str, ctx: object) -> object:
        del raw, ctx
        raise InterpretationError("provider: down") from LlmProviderError("down")


def test_health(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0"}


def test_catalog_lists_core_and_trained(client: TestClient) -> None:
    r = client.get("/api/v1/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["core"] == 67
    assert body["counts"]["trained"] >= 1
    keys = {item["key"] for item in body["concepts"]}
    assert "relation.likes" in keys
    assert "relation.friend_of" in keys
    likes = next(item for item in body["concepts"] if item["key"] == "relation.likes")
    assert likes["source"] == "core"
    assert likes["extends_core"] is True
    assert "gosto de" in likes["lemmas"] or "fa de" in likes["lemmas"]
    friend = next(item for item in body["concepts"] if item["key"] == "relation.friend_of")
    assert friend["source"] == "trained"
    assert "amigo de" in friend["lemmas"]


def test_me_session_auth(client: TestClient, auth: dict[str, str]) -> None:
    r = client.get("/api/v1/me", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["auth_mode"] == "session"
    assert body["username"] == "alice"
    assert body["id"].startswith("usr_")
    assert "password" not in body
    assert "password_hash" not in body


def test_unauthenticated_message_rejected(client: TestClient) -> None:
    r = client.post("/api/v1/messages", json={"text": RAW_A})
    assert r.status_code == 401


def test_post_message_creates_conversation_and_acknowledges(
    client: TestClient, auth: dict[str, str]
) -> None:
    r = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "rid-1"},
        headers=auth,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "acknowledgement"
    assert body["status"] == "completed"
    assert body["operation"]["kind"] == "knowledge_write"
    assert body["operation"]["outcome"] == "committed"
    assert "Entendi" in body["text"]
    assert body["conversation_id"].startswith("conv_")
    assert body["message_id"].startswith("msg_")
    assert body["client_request_id"] == "rid-1"


def test_idempotent_retry_does_not_duplicate(client: TestClient, auth: dict[str, str]) -> None:
    payload = {"text": RAW_A, "client_request_id": "same-rid"}
    first = client.post("/api/v1/messages", json=payload, headers=auth).json()
    second = client.post("/api/v1/messages", json=payload, headers=auth).json()
    assert first["message_id"] == second["message_id"]
    listed = client.get(
        f"/api/v1/conversations/{first['conversation_id']}/messages", headers=auth
    ).json()
    user_msgs = [m for m in listed if m["role"] == "user"]
    assert len(user_msgs) == 1


def test_invalid_message(client: TestClient, auth: dict[str, str]) -> None:
    r = client.post("/api/v1/messages", json={"text": ""}, headers=auth)
    assert r.status_code == 422
    r2 = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "user_id": "attacker"},
        headers=auth,
    )
    assert r2.status_code == 422


def test_new_and_existing_conversation(client: TestClient, auth: dict[str, str]) -> None:
    created = client.post("/api/v1/conversations", json={}, headers=auth)
    assert created.status_code == 201
    cid = created.json()["id"]
    listed = client.get("/api/v1/conversations", headers=auth)
    assert listed.status_code == 200
    assert any(item["id"] == cid for item in listed.json())
    r = client.post(
        "/api/v1/messages",
        json={"conversation_id": cid, "text": RAW_A},
        headers=auth,
    )
    assert r.status_code == 200
    assert r.json()["conversation_id"] == cid


def test_ownership_is_enforced(client: TestClient) -> None:
    a = register_user(client, "owner_a", "password123")
    b = register_user(client, "owner_b", "password123")
    r = client.post("/api/v1/messages", json={"text": RAW_A}, headers=a)
    cid = r.json()["conversation_id"]
    other = client.get(f"/api/v1/conversations/{cid}", headers=b)
    assert other.status_code == 404
    steal = client.post(
        "/api/v1/messages",
        json={"conversation_id": cid, "text": RAW_A},
        headers=b,
    )
    assert steal.status_code == 404
    messages = client.get(f"/api/v1/conversations/{cid}/messages", headers=b)
    assert messages.status_code == 404


def test_query_response(client: TestClient, auth: dict[str, str]) -> None:
    first = client.post("/api/v1/messages", json={"text": RAW_A}, headers=auth)
    cid = first.json()["conversation_id"]
    r = client.post(
        "/api/v1/messages",
        json={"conversation_id": cid, "text": RAW_F},
        headers=auth,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "answer"
    assert body["operation"]["kind"] == "knowledge_query"
    assert body["operation"]["outcome"] == "answered"
    assert "320" in body["text"] or "total" in body["text"].lower()


def test_write_response_does_not_claim_commit_on_failure(tmp_path: Path) -> None:
    client = make_client(tmp_path, {})
    headers = register_user(client, "solo", "password123")
    r = client.post("/api/v1/messages", json={"text": "texto sem IR"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "unsupported"
    assert "Registrei" not in body["text"]


def test_unsupported_rejected_ingest(client: TestClient, auth: dict[str, str]) -> None:
    r = client.post(
        "/api/v1/messages",
        json={"text": "Troquei o óleo do Corolla hoje por -320 reais."},
        headers=auth,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "unsupported"
    assert body["status"] == "completed"


def test_clarification_then_answer(client: TestClient, auth: dict[str, str]) -> None:
    r = client.post("/api/v1/messages", json={"text": RAW_E}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "clarification"
    assert body["status"] == "clarification_required"
    assert body["clarification"]["mode"] in {"text", "choice"}
    assert body.get("error") is None
    clar_id = body["clarification"]["id"]
    answered = client.post(
        f"/api/v1/clarifications/{clar_id}/answer",
        json={"text": "o Corolla", "client_request_id": "clar-1"},
        headers=auth,
    )
    assert answered.status_code == 200
    follow = answered.json()
    assert follow["type"] in {"acknowledgement", "answer", "clarification", "unsupported"}
    assert follow["type"] != "error"


def test_clarification_ownership(client: TestClient) -> None:
    a = register_user(client, "clar_a", "password123")
    b = register_user(client, "clar_b", "password123")
    r = client.post("/api/v1/messages", json={"text": RAW_E}, headers=a)
    clar_id = r.json()["clarification"]["id"]
    stolen = client.post(
        f"/api/v1/clarifications/{clar_id}/answer",
        json={"text": "hoje"},
        headers=b,
    )
    assert stolen.status_code == 404


def test_correction_response(client: TestClient, auth: dict[str, str]) -> None:
    first = client.post("/api/v1/messages", json={"text": RAW_D1}, headers=auth)
    cid = first.json()["conversation_id"]
    r = client.post(
        "/api/v1/messages",
        json={"conversation_id": cid, "text": RAW_E},
        headers=auth,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "acknowledgement"
    assert body["operation"]["kind"] == "knowledge_correction"
    assert body["operation"]["outcome"] == "committed"


def test_provider_failure_is_503(tmp_path: Path) -> None:
    client = make_client(tmp_path, interpreter=ProviderDown())  # type: ignore[arg-type]
    headers = register_user(client, "prov", "password123")
    r = client.post("/api/v1/messages", json={"text": "qualquer coisa"}, headers=headers)
    assert r.status_code == 503
    body = r.json()
    assert body["type"] == "error"
    assert body["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert "stack" not in str(body).lower()
    assert "Registrei" not in body["text"]


def test_core_schema_untouched() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert PRODUCT_SCHEMA_VERSION == "1.4"
    assert len(list(OntologyRegistry.with_core_seeds().concepts())) == 67
    # Knowledge may have isolation `users`; Product account tables must not live in Core ORM
    assert "conversations" not in Base.metadata.tables
    assert "messages" not in Base.metadata.tables
    assert "clarifications" not in Base.metadata.tables
    assert "sessions" not in Base.metadata.tables
    assert "idempotency" not in Base.metadata.tables
    assert "auth_events" not in Base.metadata.tables
    assert "product_schema_meta" not in Base.metadata.tables
