from pathlib import Path

from fastapi.testclient import TestClient

from jamescore.api.app import create_app
from jamescore.application.orchestrator import Orchestrator
from jamescore.application.store import ConversationStore
from jamescore.capabilities.social import SocialCapability
from jamescore.identity.assertion import mint_assertion
from jamescore.settings import Settings
from jamescore.tooling.registry import ToolRegistry


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


class _PkeStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def knowledge_graph(self, principal, **kwargs):
        self.calls.append(("graph", kwargs))
        return {
            "ok": True,
            "http": 200,
            "body": {
                "nodes": [
                    {
                        "id": "actor1",
                        "kind": "entity",
                        "label": "__principal__",
                        "type": "entity.person",
                        "canonical_name": "__principal__",
                    },
                    {
                        "id": "luna1",
                        "kind": "entity",
                        "label": "Luna",
                        "type": "entity.learned.cat",
                        "canonical_name": "Luna",
                    },
                ],
                "edges": [
                    {
                        "id": "rel1",
                        "source": "actor1",
                        "target": "luna1",
                        "type": "relation.owns",
                        "label": "owns",
                    }
                ],
                "truncated": False,
                "meta": {"root_entity_id": "actor1", "depth": kwargs.get("depth", 2)},
            },
        }

    def knowledge_entity(self, principal, entity_id, **kwargs):
        self.calls.append(("entity", {"entity_id": entity_id, **kwargs}))
        if entity_id == "missing":
            return {
                "ok": False,
                "http": 404,
                "error_code": "ENTITY_NOT_FOUND",
                "body": {"error": {"code": "ENTITY_NOT_FOUND", "message": "Entidade não encontrada."}},
            }
        return {
            "ok": True,
            "http": 200,
            "body": {
                "entity_id": entity_id,
                "canonical_name": "Luna",
                "type": {"id": "ext:entity.learned.cat", "key": "entity.learned.cat"},
                "raw": {"entity": {"id": entity_id}},
            },
        }

    def knowledge_search(self, principal, q, **kwargs):
        self.calls.append(("search", {"q": q, **kwargs}))
        items = []
        if "luna" in q.lower():
            items = [{"id": "luna1", "canonical_name": "Luna", "label": "Luna", "type": "entity.learned.cat"}]
        return {"ok": True, "http": 200, "body": {"items": items, "truncated": False}}


def _client(tmp_path: Path) -> tuple[TestClient, Settings, _PkeStub]:
    settings = _settings(tmp_path)
    stub = _PkeStub()
    app = create_app(settings)
    app.state.orchestrator = Orchestrator(
        store=ConversationStore(settings.db_path),
        pke=stub,  # type: ignore[arg-type]
        social=SocialCapability(),
        tooling=ToolRegistry(),
    )
    return TestClient(app), settings, stub


def test_knowledge_graph_requires_identity(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    r = client.get("/v1/knowledge/graph")
    assert r.status_code == 401


def test_knowledge_graph_proxies_pke(tmp_path: Path):
    client, settings, stub = _client(tmp_path)
    token = mint_assertion(settings, sub="1", display_name="Carlos")
    r = client.get(
        "/v1/knowledge/graph",
        headers={"Authorization": f"Bearer {token}"},
        params={"depth": 2},
    )
    assert r.status_code == 200
    body = r.json()
    assert any(n["canonical_name"] == "Luna" for n in body["nodes"])
    owns = [e for e in body["edges"] if e["type"] == "relation.owns"]
    assert owns[0]["source"] == "actor1"
    assert owns[0]["target"] == "luna1"
    assert stub.calls[0][0] == "graph"


def test_knowledge_entity_and_search(tmp_path: Path):
    client, settings, _ = _client(tmp_path)
    token = mint_assertion(settings, sub="1", display_name="Carlos")
    headers = {"Authorization": f"Bearer {token}"}
    entity = client.get("/v1/knowledge/entities/luna1", headers=headers)
    assert entity.status_code == 200
    assert entity.json()["canonical_name"] == "Luna"
    missing = client.get("/v1/knowledge/entities/missing", headers=headers)
    assert missing.status_code == 404
    found = client.get("/v1/knowledge/search", headers=headers, params={"q": "Luna"})
    assert found.json()["items"][0]["id"] == "luna1"
