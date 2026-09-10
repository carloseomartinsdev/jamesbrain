from pathlib import Path

from fastapi.testclient import TestClient

from jamescore.api.app import create_app
from jamescore.identity.assertion import mint_assertion
from jamescore.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        http_host="127.0.0.1",
        http_port=8010,
        data_dir=tmp_path,
        assertion_secret="test-secret",
        assertion_iss="james-portal",
        assertion_aud="jamescore",
        pke_api_url="http://127.0.0.1:9",
        pke_timeout_seconds=1.0,
        pke_auth_prefix="dev:james-",
    )


def test_identity_required(tmp_path: Path):
    client = TestClient(create_app(_settings(tmp_path)))
    r = client.post("/v1/turns", json={"text": "Oi"})
    assert r.status_code == 401


def test_identity_rejects_tampering(tmp_path: Path):
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings))
    token = mint_assertion(settings, sub="1", display_name="Carlos")
    bad = token[:-2] + ("0" if token[-1] != "0" else "1")
    r = client.post("/v1/turns", json={"text": "Oi"}, headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_body_user_id_is_not_identity(tmp_path: Path):
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings))
    token = mint_assertion(settings, sub="7", display_name="Ana")
    r = client.post(
        "/v1/turns",
        json={"text": "Oi", "user_id": "999"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == "answer"
    assert "999" not in (body.get("text") or "")


def test_social_only_does_not_need_pke(tmp_path: Path):
    settings = _settings(tmp_path)
    client = TestClient(create_app(settings))
    token = mint_assertion(settings, sub="1", display_name="Carlos")
    r = client.post("/v1/turns", json={"text": "Olá."}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == "answer"
    assert body["james_conversation_id"]
    assert body.get("trace") is None
