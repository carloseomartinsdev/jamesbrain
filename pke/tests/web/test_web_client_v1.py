from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
CLIENT_JS = (ROOT / "web/assets/js/api/client.js").read_text(encoding="utf-8")
APP_JS = (ROOT / "web/assets/js/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web/assets/css/app.css").read_text(encoding="utf-8")


def test_renders_empty_state(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert "O que você quer lembrar, registrar ou descobrir?" in html
    assert 'data-testid="app-shell"' in html
    assert 'data-testid="composer"' in html
    assert 'data-testid="auth-gate"' in html
    assert "Nova conversa" in html
    assert "aria-live" in html


def test_settings_route(client: TestClient) -> None:
    r = client.get("/settings")
    assert r.status_code == 200
    assert "PKE" in r.text


def test_login_route(client: TestClient) -> None:
    r = client.get("/login")
    assert r.status_code == 200
    assert 'data-testid="auth-gate"' in r.text


def test_conversation_deep_link_shell(client: TestClient) -> None:
    r = client.get("/c/conv_example")
    assert r.status_code == 200
    assert 'id="message-list"' in r.text


def test_assets_and_client_module(client: TestClient) -> None:
    css = client.get("/assets/css/app.css")
    assert css.status_code == 200
    js = client.get("/assets/js/api/client.js")
    assert js.status_code == 200
    assert "sendMessage" in js.text
    assert "listConversations" in js.text
    assert "createConversation" in js.text
    assert "answerClarification" in js.text
    assert "getCurrentUser" in js.text
    assert "login" in js.text
    assert "logout" in js.text
    assert "sessionStorage" in js.text
    assert "Authorization" in js.text


def test_fetch_only_in_api_client() -> None:
    web_js = list((ROOT / "web/assets/js").rglob("*.js"))
    offenders = []
    for path in web_js:
        if path.name == "client.js" and path.parent.name == "api":
            continue
        text = path.read_text(encoding="utf-8")
        if "fetch(" in text:
            offenders.append(str(path))
    assert offenders == []
    assert "sendMessage" in CLIENT_JS
    assert "client_request_id" in CLIENT_JS


def test_mobile_sidebar_and_composer() -> None:
    assert "@media (max-width: 860px)" in CSS
    assert ".sidebar.open" in CSS
    assert "position: sticky" in CSS
    assert ":focus-visible" in CSS
    assert ".auth-gate" in CSS


def test_retry_and_clarification_ui_hooks() -> None:
    assert "Tentar de novo" in (ROOT / "web/assets/js/renderers/index.js").read_text(
        encoding="utf-8"
    )
    assert "clarification-card" in (ROOT / "web/assets/js/renderers/index.js").read_text(
        encoding="utf-8"
    )
    assert "data-retry" in APP_JS
    assert "Shift" in APP_JS or "shiftKey" in APP_JS


def test_auth_session_ux_hooks() -> None:
    assert "showAuthGate" in APP_JS
    assert "session expired" in APP_JS
    assert "draftBeforeAuth" in APP_JS
    assert "authenticating" in APP_JS
    assert "logout" in APP_JS
    assert "getStoredToken" in APP_JS


def test_lifecycle_reload_hooks() -> None:
    assert "pending_clarification" in APP_JS or "pendingClarification" in APP_JS
    assert "getConversation" in APP_JS
    assert "user_message_id" in APP_JS or "hydrated" in APP_JS


def test_resilience_error_hooks() -> None:
    assert "OPERATION_RECOVERY_REQUIRED" in CLIENT_JS or "recovery" in CLIENT_JS
    assert "409" in CLIENT_JS


def test_ux_logout_clears_state() -> None:
    assert "clearAuthenticatedUi" in APP_JS


def test_conversation_switching_urls(client: TestClient, auth: dict[str, str]) -> None:
    created = client.post("/api/v1/conversations", json={}, headers=auth)
    cid = created.json()["id"]
    page = client.get(f"/c/{cid}")
    assert page.status_code == 200
    assert "composer-input" in page.text


def test_web_can_roundtrip_message(client: TestClient, auth: dict[str, str]) -> None:
    page = client.get("/")
    assert "O que você quer registrar ou saber?" in page.text
    sent = client.post(
        "/api/v1/messages",
        json={"text": "Troquei o óleo do Corolla hoje por 320 reais."},
        headers=auth,
    )
    assert sent.status_code == 200
    assert sent.json()["type"] == "acknowledgement"


def test_unauthenticated_api_blocked(client: TestClient) -> None:
    assert client.get("/api/v1/conversations").status_code == 401
    assert client.post("/api/v1/messages", json={"text": "oi"}).status_code == 401
