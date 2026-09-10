"""P3 — Product resilience, recovery & operational consistency."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from pke.application.clock import FixedClock
from pke.interpretation import FakeInterpreter
from pke.ontology import OntologyRegistry
from pke.product.api.v1.app import create_app
from pke.product.conversation.idempotency import IdempotencyStatus, message_fingerprint
from pke.product.runtime import ProductRuntime
from tests.api.conftest import make_client, register_user
from tests.api.test_p1_identity_ownership import CountingInterpreter
from tests.integration.test_ask import RAW_F, _query_ir
from tests.integration.test_ingest import NOW, RAW_A, RAW_E, ir_a, ir_e

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"


def _client(
    tmp_path: Path,
    *,
    interpreter=None,
    stale_seconds: int = 0,
) -> TestClient:
    return make_client(
        tmp_path,
        {RAW_A: ir_a(), RAW_E: ir_e(), RAW_F: _query_ir()},
        interpreter=interpreter,
        idempotency_stale_seconds=stale_seconds,
    )


def _force_in_progress(product_db: Path, user_id: str, client_request_id: str) -> None:
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
                (NOW - timedelta(seconds=10)).replace(microsecond=0).isoformat(),
                user_id,
                client_request_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_completed_survives_restart_replay(tmp_path: Path) -> None:
    spy = CountingInterpreter({RAW_A: ir_a()})
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
    auth = register_user(client, "res_a", "password123")
    first = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "restart-1"},
        headers=auth,
    )
    assert first.status_code == 200
    mid = first.json()["message_id"]
    calls = spy.calls

    # Simulate process restart: new runtime/store on same Product DB file.
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
    client2 = TestClient(create_app(runtime2))
    login = client2.post(
        "/api/v1/auth/login",
        json={"username": "res_a", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    second = client2.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "restart-1"},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["message_id"] == mid
    assert spy.calls == calls


def test_fingerprint_conflict_after_restart(tmp_path: Path) -> None:
    client = _client(tmp_path)
    auth = register_user(client, "res_b", "password123")
    client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "fp-1"},
        headers=auth,
    )
    conflict = client.post(
        "/api/v1/messages",
        json={"text": RAW_F, "client_request_id": "fp-1"},
        headers=auth,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    assert conflict.json()["error"]["retryable"] is False


def test_stale_in_progress_recovers_from_assistant_message(tmp_path: Path) -> None:
    spy = CountingInterpreter({RAW_A: ir_a()})
    client = _client(tmp_path, interpreter=spy, stale_seconds=0)
    auth = register_user(client, "res_c", "password123")
    sent = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "stale-ok"},
        headers=auth,
    )
    assert sent.status_code == 200
    user_id = client.get("/api/v1/me", headers=auth).json()["id"]
    mid = sent.json()["message_id"]
    calls = spy.calls
    _force_in_progress(tmp_path / "product.db", user_id, "stale-ok")
    replay = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "stale-ok"},
        headers=auth,
    )
    assert replay.status_code == 200
    assert replay.json()["message_id"] == mid
    assert spy.calls == calls


def test_stale_in_progress_ambiguous_blocks_engine(tmp_path: Path) -> None:
    spy = CountingInterpreter({RAW_A: ir_a()})
    product_db = tmp_path / "product.db"
    runtime = ProductRuntime.build(
        interpreter=spy,
        knowledge_db=tmp_path / "knowledge.db",
        product_db=product_db,
        web_root=WEB_ROOT,
        clock=FixedClock(NOW),
        ontology=OntologyRegistry.with_core_seeds(),
        auth_mode="session",
        idempotency_stale_seconds=0,
    )
    client = TestClient(create_app(runtime))
    auth = register_user(client, "res_d", "password123")
    user_id = client.get("/api/v1/me", headers=auth).json()["id"]
    # Claim without completing (crash window after guard, before/during Engine).
    fp = message_fingerprint(text=RAW_A, conversation_id=None)
    runtime.orchestrator._store.claim_idempotent(  # noqa: SLF001
        user_id,
        "stale-amb",
        request_fingerprint=fp,
        conversation_id=None,
    )
    _force_in_progress(product_db, user_id, "stale-amb")
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


def test_failed_before_engine_allows_safe_retry(tmp_path: Path) -> None:
    spy = CountingInterpreter({RAW_A: ir_a()})
    client = _client(tmp_path, interpreter=spy, stale_seconds=0)
    auth = register_user(client, "res_e", "password123")
    user_id = client.get("/api/v1/me", headers=auth).json()["id"]
    fp = message_fingerprint(text=RAW_A, conversation_id=None)
    store = client.app.state.runtime.orchestrator._store  # noqa: SLF001
    store.claim_idempotent(
        user_id, "fail-retry", request_fingerprint=fp, conversation_id=None
    )
    store.fail_idempotent(user_id, "fail-retry")
    before = spy.calls
    ok = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "fail-retry"},
        headers=auth,
    )
    assert ok.status_code == 200
    assert ok.json()["operation"]["outcome"] == "committed"
    assert spy.calls == before + 1


def test_product_db_unavailable_before_engine(tmp_path: Path) -> None:
    spy = CountingInterpreter({RAW_A: ir_a()})
    client = _client(tmp_path, interpreter=spy)
    auth = register_user(client, "res_f", "password123")
    before = spy.calls
    with patch.object(
        client.app.state.runtime.orchestrator._store,  # noqa: SLF001
        "ping",
        side_effect=OSError("db down"),
    ):
        r = client.post(
            "/api/v1/messages",
            json={"text": RAW_A, "client_request_id": "db-down"},
            headers=auth,
        )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "PRODUCT_UNAVAILABLE"
    assert r.json()["error"]["retryable"] is True
    assert spy.calls == before


def test_clarification_duplicate_after_crash_window(tmp_path: Path) -> None:
    client = _client(tmp_path, stale_seconds=0)
    auth = register_user(client, "res_g", "password123")
    first = client.post("/api/v1/messages", json={"text": RAW_E}, headers=auth)
    clar_id = first.json()["clarification"]["id"]
    ans = client.post(
        f"/api/v1/clarifications/{clar_id}/answer",
        json={"text": "o Corolla", "client_request_id": "clar-r1"},
        headers=auth,
    )
    assert ans.status_code == 200
    # Stale tab / second attempt
    again = client.post(
        f"/api/v1/clarifications/{clar_id}/answer",
        json={"text": "o Corolla", "client_request_id": "clar-r2"},
        headers=auth,
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CLARIFICATION_ANSWERED"


def test_cross_user_cannot_replay_idempotency(tmp_path: Path) -> None:
    client = _client(tmp_path)
    a = register_user(client, "res_h", "password123")
    b = register_user(client, "res_i", "password123")
    client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "shared-looking"},
        headers=a,
    )
    other = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "shared-looking"},
        headers=b,
    )
    assert other.status_code == 200
    cid_a = client.get("/api/v1/conversations", headers=a).json()[0]["id"]
    assert client.get(f"/api/v1/conversations/{cid_a}", headers=b).status_code == 404


def test_fresh_in_progress_is_retryable(tmp_path: Path) -> None:
    spy = CountingInterpreter({RAW_A: ir_a()})
    # Large stale window so in_progress is not treated as stale.
    client = _client(tmp_path, interpreter=spy, stale_seconds=3600)
    auth = register_user(client, "res_j", "password123")
    user_id = client.get("/api/v1/me", headers=auth).json()["id"]
    fp = message_fingerprint(text=RAW_A, conversation_id=None)
    client.app.state.runtime.orchestrator._store.claim_idempotent(  # noqa: SLF001
        user_id, "inflight-1", request_fingerprint=fp, conversation_id=None
    )
    before = spy.calls
    r = client.post(
        "/api/v1/messages",
        json={"text": RAW_A, "client_request_id": "inflight-1"},
        headers=auth,
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "IDEMPOTENCY_IN_PROGRESS"
    assert r.json()["error"]["retryable"] is True
    assert spy.calls == before
