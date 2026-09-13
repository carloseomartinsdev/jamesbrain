"""PKE API — read-only knowledge inspect endpoints."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from pke.application.clock import FixedClock
from pke.application.principal import PrincipalBindingService
from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.domain.entities import Entity
from pke.domain.ids import new_ulid
from pke.domain.measurements import Measurement
from pke.domain.relations import Relation
from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import Confidence, Qualifier, RawInput, Source, SourceKind
from pke.interpretation import FakeInterpreter
from pke.ontology import OntologyRegistry
from pke.ontology.learned import learned_concept_id
from pke.ontology.seeds import core_concept_id
from pke.persist import open_sqlite_uow
from pke.product.api.v1.app import create_app
from pke.product.runtime import ProductRuntime
from tests.api.conftest import auth_dev
from tests.integration.test_ingest import NOW


def _seed_family(db: Path, user_id: str = "u1") -> dict[str, str]:
    ids: dict[str, str] = {}
    with open_sqlite_uow(db) as uow:
        principal = PrincipalBindingService().ensure_principal_entity(uow, user_id, now=NOW)
        ids["actor"] = principal
        raw = uow.raw_inputs.add(
            RawInput(id=new_ulid(), user_id=user_id, text="seed", created_at=NOW)
        )
        src = Source(
            id=new_ulid(),
            user_id=user_id,
            kind=SourceKind.USER_STATEMENT,
            raw_input_id=raw.id,
        )
        uow.sources.add(src)
        ids["raw"] = raw.id
        ids["source"] = src.id or ""

        def add_ent(name: str, type_key: str) -> str:
            if type_key.startswith("entity.learned."):
                type_id = learned_concept_id(type_key)
            else:
                type_id = core_concept_id(type_key)
            ent = Entity(
                id=new_ulid(),
                user_id=user_id,
                type_id=type_id,
                canonical_name=name,
                created_at=NOW,
            )
            uow.entities.add(ent)
            rel = Relation(
                id=new_ulid(),
                user_id=user_id,
                from_id=principal,
                to_id=ent.id,
                concept_id=core_concept_id("relation.owns"),
                key="relation.owns",
                temporal=TemporalKnowledge.unknown(),
                observed_at=NOW,
                is_current=True,
                source=src,
                raw_input_id=raw.id,
                confidence=Confidence(score=0.9, qualifier=Qualifier.EXACT),
                created_at=NOW,
            )
            uow.relations.add(rel)
            return ent.id

        ids["luna"] = add_ent("Luna", "entity.learned.cat")
        ids["thor"] = add_ent("Thor", "entity.learned.dog")
        ids["orion"] = add_ent("Orion", "entity.learned.computer")
        ids["nala"] = add_ent("Nala", "entity.learned.cat")
        uow.attributes.add(
            EntityAttribute(
                id=new_ulid(),
                user_id=user_id,
                entity_id=ids["luna"],
                dimension_key="color",
                value_kind=AttributeValueKind.TEXT,
                text_value="black",
                temporal=TemporalKnowledge.unknown(),
                observed_at=NOW,
                is_current=True,
                source=src,
                raw_input_id=raw.id,
                created_at=NOW,
            )
        )
        for dim, value, unit in (("weight", "4", "kg"), ("height", "30", "cm")):
            uow.measurements.add(
                Measurement(
                    id=new_ulid() if dim != "weight" else "01M2B346C7XVAT4VN0AG6Q5EMT",
                    user_id=user_id,
                    entity_id=ids["luna"],
                    dimension_key=dim,
                    numeric_value=Decimal(value),
                    unit=unit,
                    temporal=TemporalKnowledge.unknown(),
                    observed_at=NOW,
                    source=src,
                    raw_input_id=raw.id,
                    confidence=Confidence(score=1.0, qualifier=Qualifier.EXACT),
                    created_at=NOW,
                )
            )
        uow.commit()
    return ids


def _client(tmp_path: Path, user_id: str = "u1") -> tuple[TestClient, dict[str, str], dict[str, str]]:
    knowledge = tmp_path / "knowledge.db"
    ids = _seed_family(knowledge, user_id)
    runtime = ProductRuntime.build(
        interpreter=FakeInterpreter({}),
        knowledge_db=knowledge,
        product_db=tmp_path / "product.db",
        clock=FixedClock(NOW),
        ontology=OntologyRegistry.with_core_seeds(),
        auth_mode="dev",
    )
    return TestClient(create_app(runtime)), auth_dev(user_id), ids


def test_knowledge_requires_auth(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    r = client.get("/api/v1/knowledge/graph")
    assert r.status_code == 401


def test_graph_root_and_owns(tmp_path: Path) -> None:
    client, auth, ids = _client(tmp_path)
    r = client.get("/api/v1/knowledge/graph", headers=auth)
    assert r.status_code == 200
    body = r.json()
    entities = [n for n in body["nodes"] if n["kind"] == "entity"]
    names = {n["canonical_name"] for n in entities}
    assert "Luna" in names
    owns = [e for e in body["edges"] if e["type"] == "relation.owns"]
    assert any(e["source"] == ids["actor"] and e["target"] == ids["luna"] for e in owns)
    luna = next(n for n in entities if n["id"] == ids["luna"])
    assert luna["type"] == "entity.learned.cat"
    assert body["truncated"] is False
    assert body["meta"]["root_entity_id"] == ids["actor"]
    assert body["meta"]["depth"] == 2


def test_graph_unknown_root(tmp_path: Path) -> None:
    client, auth, _ = _client(tmp_path)
    r = client.get("/api/v1/knowledge/graph", headers=auth, params={"root_entity_id": "01MISSINGENTITYID000000000"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "ENTITY_NOT_FOUND"


def test_entity_details_and_attributes(tmp_path: Path) -> None:
    client, auth, ids = _client(tmp_path)
    r = client.get(f"/api/v1/knowledge/entities/{ids['luna']}", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["entity_id"] == ids["luna"]
    assert body["canonical_name"] == "Luna"
    assert body["type"]["key"] == "entity.learned.cat"
    assert any(rel["type"] == "relation.owns" for rel in body["relations_incoming"])
    dims = {a["dimension_key"]: a["value"] for a in body["attributes"]}
    assert dims["color"] == "black"
    assert "weight" not in dims
    meas = {m["dimension_key"]: m for m in body["measurements"]}
    assert meas["weight"]["numeric_value"] == "4"
    assert meas["weight"]["unit"] == "kg"
    assert meas["weight"]["display_value"] == "4 kg"
    assert meas["height"]["display_value"] == "30 cm"
    assert body["raw"]["entity"]["id"] == ids["luna"]
    assert body["raw"]["measurements"][0]["dimension_key"] in {"weight", "height"}
    nala = client.get(f"/api/v1/knowledge/entities/{ids['nala']}", headers=auth).json()
    assert nala["canonical_name"] == "Nala"
    assert nala["measurements"] == []
    assert nala["attributes"] == []


def test_search_filter_and_isolation(tmp_path: Path) -> None:
    client, auth, ids = _client(tmp_path)
    r = client.get("/api/v1/knowledge/search", headers=auth, params={"q": "Luna"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["id"] == ids["luna"]
    typed = client.get(
        "/api/v1/knowledge/search",
        headers=auth,
        params={"q": "Thor", "type": "entity.learned.dog"},
    )
    assert typed.json()["items"][0]["canonical_name"] == "Thor"
    other = client.get("/api/v1/knowledge/search", headers=auth_dev("u2"), params={"q": "Luna"})
    assert other.status_code == 200
    assert other.json()["items"] == []


def test_invalid_id_rejected(tmp_path: Path) -> None:
    client, auth, _ = _client(tmp_path)
    r = client.get("/api/v1/knowledge/entities/../etc/passwd", headers=auth)
    assert r.status_code in {404, 422}
    r2 = client.get("/api/v1/knowledge/graph", headers=auth, params={"root_entity_id": "a b"})
    assert r2.status_code == 422


def test_write_methods_not_allowed(tmp_path: Path) -> None:
    client, auth, ids = _client(tmp_path)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        r = client.request(method, "/api/v1/knowledge/graph", headers=auth, json={})
        assert r.status_code == 405
        r2 = client.request(method, f"/api/v1/knowledge/entities/{ids['luna']}", headers=auth, json={})
        assert r2.status_code == 405
