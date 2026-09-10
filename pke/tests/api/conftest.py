from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pke.application.clock import FixedClock
from pke.interpretation import FakeInterpreter
from pke.ontology import OntologyRegistry
from pke.product.api.v1.app import create_app
from pke.product.runtime import ProductRuntime
from tests.integration.test_ask import RAW_F, _query_ir
from tests.integration.test_ingest import (
    NOW,
    RAW_A,
    RAW_D1,
    RAW_E,
    RAW_NO_TIME,
    ir_a,
    ir_d1,
    ir_e,
    ir_negative,
    ir_no_time,
)

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"


def make_client(
    tmp_path: Path,
    responses: dict | None = None,
    *,
    auth_mode: str = "session",
    session_ttl_seconds: int | None = None,
    interpreter=None,
    idempotency_stale_seconds: int | None = None,
) -> TestClient:
    interp = interpreter if interpreter is not None else FakeInterpreter(responses or {})
    runtime = ProductRuntime.build(
        interpreter=interp,
        knowledge_db=tmp_path / "knowledge.db",
        product_db=tmp_path / "product.db",
        web_root=WEB_ROOT,
        clock=FixedClock(NOW),
        ontology=OntologyRegistry.with_core_seeds(),
        debug_ui=True,
        auth_mode=auth_mode,
        session_ttl_seconds=session_ttl_seconds,
        idempotency_stale_seconds=idempotency_stale_seconds,
    )
    return TestClient(create_app(runtime))


def register_user(
    client: TestClient,
    username: str = "alice",
    password: str = "password123",
    display_name: str | None = None,
) -> dict[str, str]:
    body = {"username": username, "password": password}
    if display_name:
        body["display_name"] = display_name
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def auth_dev(user_id: str = "u1") -> dict[str, str]:
    return {"Authorization": f"Bearer dev:{user_id}"}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return make_client(
        tmp_path,
        {
            RAW_A: ir_a(),
            RAW_NO_TIME: ir_no_time(),
            "Troquei o óleo do Corolla. hoje": ir_a("Troquei o óleo do Corolla. hoje"),
            RAW_D1: ir_d1(),
            RAW_E: ir_e(),
            f"{RAW_E} o Corolla": ir_d1(),
            RAW_F: _query_ir(),
            "Troquei o óleo do Corolla hoje por -320 reais.": ir_negative(),
        },
    )


@pytest.fixture
def auth(client: TestClient) -> dict[str, str]:
    return register_user(client, "alice", "password123")
