"""P4 — Product UX completion hooks and journey evidence."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.api.conftest import make_client, register_user
from tests.integration.test_ask import RAW_F, _query_ir
from tests.integration.test_ingest import RAW_A, RAW_E, ir_a, ir_e

ROOT = Path(__file__).resolve().parents[2]
APP_JS = (ROOT / "web/assets/js/app.js").read_text(encoding="utf-8")
CLIENT_JS = (ROOT / "web/assets/js/api/client.js").read_text(encoding="utf-8")
RENDERER = (ROOT / "web/assets/js/renderers/index.js").read_text(encoding="utf-8")
CSS = (ROOT / "web/assets/css/app.css").read_text(encoding="utf-8")
HTML = (ROOT / "web/index.html").read_text(encoding="utf-8")


def test_ux_rendering_authority_hooks() -> None:
    assert "data-role=\"unsupported\"" in RENDERER or 'data-role="unsupported"' in RENDERER
    assert "clar-text-form" in RENDERER
    assert "recovery" in RENDERER.lower()
    assert "technical-error" in RENDERER
    assert "OPERATION_RECOVERY_REQUIRED" in APP_JS
    assert "clearAuthenticatedUi" in APP_JS
    assert "state.sending" in APP_JS or "sending: false" in APP_JS


def test_no_engine_ir_in_web() -> None:
    offenders = []
    for path in (ROOT / "web").rglob("*"):
        if path.suffix not in {".js", ".html", ".css"}:
            continue
        text = path.read_text(encoding="utf-8")
        for token in (
            "SemanticProposal",
            "QueryIR",
            "ExecutionReadiness",
            "CapabilityStrategy",
            "PendingSemanticOperation",
            "ontology",
            "canonicalization",
        ):
            if token in text:
                offenders.append(f"{path.name}:{token}")
    assert offenders == []


def test_auth_and_shell_markup(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert 'data-testid="auth-gate"' in page.text
    assert "Entrar no PKE" in page.text
    assert "Nova conversa" in page.text
    assert 'for="composer-input"' in page.text
    assert "Pensando" in page.text


def test_journey_write_query_clarification_abstain(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        {
            RAW_A: ir_a(),
            RAW_E: ir_e(),
            RAW_F: _query_ir(),
        },
    )
    headers = register_user(client, "ux_a", "password123")

    # J3 write
    write = client.post("/api/v1/messages", json={"text": RAW_A}, headers=headers)
    assert write.status_code == 200
    assert write.json()["operation"]["outcome"] == "committed"
    assert "Registrei" in write.json()["text"]
    cid = write.json()["conversation_id"]

    # J4 query
    ask = client.post(
        "/api/v1/messages",
        json={"conversation_id": cid, "text": RAW_F},
        headers=headers,
    )
    assert ask.status_code == 200
    assert ask.json()["operation"]["kind"] == "knowledge_query"

    # J5 clarification
    clar = client.post("/api/v1/messages", json={"text": RAW_E}, headers=headers)
    assert clar.json()["type"] == "clarification"
    assert clar.json()["status"] == "clarification_required"
    clar_id = clar.json()["clarification"]["id"]
    hyd = client.get(
        f"/api/v1/conversations/{clar.json()['conversation_id']}", headers=headers
    )
    assert hyd.json()["pending_clarification"]["id"] == clar_id

    # J6 safe abstain
    abs_ = client.post("/api/v1/messages", json={"text": "xyzxyz"}, headers=headers)
    assert abs_.json()["type"] == "unsupported"
    assert abs_.json()["status"] == "completed"
    assert "segurança" in abs_.json()["text"].lower() or "interpret" in abs_.json()["text"].lower()


def test_journey_reload_and_user_isolation(tmp_path: Path) -> None:
    client = make_client(tmp_path, {RAW_A: ir_a()})
    a = register_user(client, "ux_b", "password123")
    sent = client.post("/api/v1/messages", json={"text": RAW_A}, headers=a)
    cid = sent.json()["conversation_id"]
    reloaded = client.get(f"/api/v1/conversations/{cid}", headers=a)
    assert len(reloaded.json()["messages"]) >= 2

    client.post("/api/v1/auth/logout", headers=a)
    b = register_user(client, "ux_c", "password123")
    assert client.get(f"/api/v1/conversations/{cid}", headers=b).status_code == 404
    listed = client.get("/api/v1/conversations", headers=b)
    assert listed.json() == [] or all(item["id"] != cid for item in listed.json())


def test_responsive_and_a11y_hooks() -> None:
    assert "@media (max-width: 860px)" in CSS
    assert ".sr-only" in CSS
    assert ":focus-visible" in CSS
    assert "aria-live" in HTML
    assert "aria-label" in HTML
    assert "Shift" in APP_JS or "shiftKey" in APP_JS
