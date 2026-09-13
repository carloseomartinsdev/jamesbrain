"""Knowledge Inspector — persisted snapshot projection, no inference."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.domain.entities import Entity
from pke.domain.ids import new_ulid
from pke.domain.measurements import Measurement
from pke.domain.principal import PRINCIPAL_CANONICAL_NAME
from pke.domain.relations import Relation
from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import Source, SourceKind
from pke.ontology import OntologyRegistry
from pke.ontology.learned import learned_concept_id
from pke.ontology.seeds import core_concept_id
from pke.persist.snapshot import UserKnowledgeSnapshot
from pke.product.knowledge.inspector import KnowledgeInspector, KnowledgeNotFound

NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=dt.UTC)
USER = "u1"


class _Store:
    def __init__(self, snapshot: UserKnowledgeSnapshot) -> None:
        self.snapshot = snapshot

    def load_user_graph(self, user_id: str) -> UserKnowledgeSnapshot:
        assert user_id == self.snapshot.user_id
        return self.snapshot


def _entity(eid: str, name: str, type_id: str) -> Entity:
    return Entity(
        id=eid,
        user_id=USER,
        type_id=type_id,
        canonical_name=name,
        created_at=NOW,
    )


def _owns(from_id: str, to_id: str, *, current: bool = True, rid: str | None = None) -> Relation:
    return Relation(
        id=rid or new_ulid(),
        user_id=USER,
        from_id=from_id,
        to_id=to_id,
        concept_id=core_concept_id("relation.owns"),
        key="relation.owns",
        temporal=TemporalKnowledge.unknown(),
        observed_at=NOW,
        is_current=current,
        created_at=NOW,
    )


def _luna_snapshot() -> UserKnowledgeSnapshot:
    actor = _entity("actor1", PRINCIPAL_CANONICAL_NAME, core_concept_id("entity.person"))
    luna = _entity("luna1", "Luna", learned_concept_id("entity.learned.cat"))
    return UserKnowledgeSnapshot(
        user_id=USER,
        entities={actor.id: actor, luna.id: luna},
        relations=[_owns(actor.id, luna.id, rid="rel-owns-luna")],
        principal_entity_id=actor.id,
    )


def _inspector(snapshot: UserKnowledgeSnapshot) -> KnowledgeInspector:
    return KnowledgeInspector(_Store(snapshot), OntologyRegistry.with_core_seeds())


def test_graph_root_owns_luna() -> None:
    graph = _inspector(_luna_snapshot()).graph(USER, depth=2)
    entities = [n for n in graph.nodes if n.kind == "entity"]
    types = [n for n in graph.nodes if n.kind == "type"]
    owns = [e for e in graph.edges if e.kind == "relation"]
    assert {n.canonical_name for n in entities} == {PRINCIPAL_CANONICAL_NAME, "Luna"}
    assert len(owns) == 1
    assert owns[0].source == "actor1"
    assert owns[0].target == "luna1"
    assert owns[0].type == "relation.owns"
    assert owns[0].label == "owns"
    assert any(n.type == "entity.learned.cat" for n in entities)
    assert any(n.label == "entity.learned.cat" for n in types)
    assert graph.truncated is False
    assert graph.meta.root_entity_id == "actor1"


def test_graph_preserves_direction() -> None:
    graph = _inspector(_luna_snapshot()).graph(USER)
    owns = next(e for e in graph.edges if e.type == "relation.owns")
    assert owns.source == "actor1"
    assert owns.target == "luna1"


def test_depth_1_excludes_second_hop() -> None:
    actor = _entity("actor1", PRINCIPAL_CANONICAL_NAME, core_concept_id("entity.person"))
    luna = _entity("luna1", "Luna", learned_concept_id("entity.learned.cat"))
    house = _entity("house1", "Casa da Praia", core_concept_id("entity.place"))
    snap = UserKnowledgeSnapshot(
        user_id=USER,
        entities={actor.id: actor, luna.id: luna, house.id: house},
        relations=[_owns(actor.id, luna.id), _owns(luna.id, house.id, rid="rel-luna-house")],
        principal_entity_id=actor.id,
    )
    shallow = _inspector(snap).graph(USER, depth=1)
    names = {n.canonical_name for n in shallow.nodes if n.kind == "entity"}
    assert names == {PRINCIPAL_CANONICAL_NAME, "Luna"}
    deep = _inspector(snap).graph(USER, depth=2)
    names2 = {n.canonical_name for n in deep.nodes if n.kind == "entity"}
    assert "Casa da Praia" in names2


def test_incoming_and_outgoing_on_entity() -> None:
    detail = _inspector(_luna_snapshot()).entity(USER, "luna1")
    assert detail.canonical_name == "Luna"
    assert detail.type.key == "entity.learned.cat"
    assert detail.entity_id == "luna1"
    assert len(detail.relations_incoming) == 1
    assert detail.relations_incoming[0].type == "relation.owns"
    assert detail.relations_incoming[0].from_id == "actor1"
    assert detail.relations_outgoing == []
    assert any(item.key == "canonical_name" and item.value == "Luna" for item in detail.intrinsic)


def test_attribute_listing() -> None:
    snap = _luna_snapshot()
    luna = snap.entities["luna1"]
    src = Source(id="src1", user_id=USER, kind=SourceKind.USER_STATEMENT, raw_input_id=None)
    snap.attributes = [
        EntityAttribute(
            id="attr-weight",
            user_id=USER,
            entity_id=luna.id,
            dimension_key="weight",
            value_kind=AttributeValueKind.NUMBER,
            numeric_value="4.5",
            unit="kg",
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            is_current=True,
            source=src,
            created_at=NOW,
        ),
        EntityAttribute(
            id="attr-breed",
            user_id=USER,
            entity_id=luna.id,
            dimension_key="breed",
            value_kind=AttributeValueKind.TEXT,
            text_value="siamese",
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            is_current=True,
            source=src,
            created_at=NOW,
        ),
        EntityAttribute(
            id="attr-old-weight",
            user_id=USER,
            entity_id=luna.id,
            dimension_key="weight",
            value_kind=AttributeValueKind.NUMBER,
            numeric_value="4.0",
            unit="kg",
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            is_current=False,
            source=src,
            created_at=NOW,
        ),
    ]
    current = _inspector(snap).entity(USER, "luna1", current_only=True)
    keys = {a.dimension_key: a.value for a in current.attributes}
    assert keys["weight"] == "4.5 kg"
    assert keys["breed"] == "siamese"
    assert len(current.attributes) == 2
    history = _inspector(snap).entity(USER, "luna1", current_only=False)
    assert len(history.attributes) == 3


def test_measurement_listing_separate_from_attributes() -> None:
    snap = _luna_snapshot()
    luna = snap.entities["luna1"]
    src = Source(id="src1", user_id=USER, kind=SourceKind.USER_STATEMENT, raw_input_id=None)
    snap.attributes = [
        EntityAttribute(
            id="attr-color",
            user_id=USER,
            entity_id=luna.id,
            dimension_key="color",
            value_kind=AttributeValueKind.TEXT,
            text_value="black",
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            is_current=True,
            source=src,
            created_at=NOW,
        )
    ]
    snap.measurements = [
        Measurement(
            id="meas-weight",
            user_id=USER,
            entity_id=luna.id,
            dimension_key="weight",
            numeric_value=Decimal("4"),
            unit="kg",
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            source=src,
            created_at=NOW,
        ),
        Measurement(
            id="meas-height",
            user_id=USER,
            entity_id=luna.id,
            dimension_key="height",
            numeric_value=Decimal("30"),
            unit="cm",
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            source=src,
            created_at=NOW,
        ),
    ]
    detail = _inspector(snap).entity(USER, "luna1")
    assert {a.dimension_key: a.value for a in detail.attributes} == {"color": "black"}
    by_dim = {m.dimension_key: m for m in detail.measurements}
    assert by_dim["weight"].numeric_value == "4"
    assert by_dim["weight"].unit == "kg"
    assert by_dim["weight"].display_value == "4 kg"
    assert by_dim["height"].display_value == "30 cm"
    assert detail.raw["measurements"][0]["dimension_key"] in {"weight", "height"}
    assert "is_current" not in by_dim["weight"].model_dump()


def test_entity_without_measurements() -> None:
    actor = _entity("actor1", PRINCIPAL_CANONICAL_NAME, core_concept_id("entity.person"))
    nala = _entity("nala1", "Nala", learned_concept_id("entity.learned.cat"))
    snap = UserKnowledgeSnapshot(
        user_id=USER,
        entities={actor.id: actor, nala.id: nala},
        principal_entity_id=actor.id,
    )
    detail = _inspector(snap).entity(USER, "nala1")
    assert detail.measurements == []
    assert detail.attributes == []
    assert detail.states == []
    assert detail.events == []


def test_search_luna() -> None:
    found = _inspector(_luna_snapshot()).search(USER, "Luna")
    assert len(found.items) == 1
    assert found.items[0].id == "luna1"
    assert found.items[0].type == "entity.learned.cat"


def test_search_by_id_and_type() -> None:
    snap = _luna_snapshot()
    by_id = _inspector(snap).search(USER, "luna1")
    assert by_id.items[0].canonical_name == "Luna"
    by_type = _inspector(snap).search(USER, "learned.cat")
    assert any(item.id == "luna1" for item in by_type.items)


def test_unknown_entity() -> None:
    insp = _inspector(_luna_snapshot())
    try:
        insp.entity(USER, "missing")
        raise AssertionError("expected not found")
    except KnowledgeNotFound:
        pass
    try:
        insp.graph(USER, root_entity_id="missing")
        raise AssertionError("expected not found")
    except KnowledgeNotFound:
        pass


def test_current_only_hides_historical_relation() -> None:
    actor = _entity("actor1", PRINCIPAL_CANONICAL_NAME, core_concept_id("entity.person"))
    luna = _entity("luna1", "Luna", learned_concept_id("entity.learned.cat"))
    snap = UserKnowledgeSnapshot(
        user_id=USER,
        entities={actor.id: actor, luna.id: luna},
        relations=[_owns(actor.id, luna.id, current=False, rid="rel-old")],
        principal_entity_id=actor.id,
    )
    current = _inspector(snap).graph(USER, current_only=True)
    assert [e for e in current.edges if e.kind == "relation"] == []
    history = _inspector(snap).graph(USER, current_only=False)
    assert len([e for e in history.edges if e.kind == "relation"]) == 1


def test_limits_truncate(monkeypatch) -> None:
    import pke.product.knowledge.inspector as mod

    monkeypatch.setattr(mod, "MAX_GRAPH_NODES", 3)
    actor = _entity("actor1", PRINCIPAL_CANONICAL_NAME, core_concept_id("entity.person"))
    owned = [
        _entity(f"pet{i}", f"Pet{i}", learned_concept_id("entity.learned.cat")) for i in range(6)
    ]
    ents = {actor.id: actor, **{e.id: e for e in owned}}
    rels = [_owns(actor.id, e.id, rid=f"rel{i}") for i, e in enumerate(owned)]
    snap = UserKnowledgeSnapshot(
        user_id=USER,
        entities=ents,
        relations=rels,
        principal_entity_id=actor.id,
    )
    graph = _inspector(snap).graph(USER, depth=1)
    assert graph.truncated is True
    assert len(graph.nodes) <= 3


def test_does_not_invent_ontology_parent() -> None:
    graph = _inspector(_luna_snapshot()).graph(USER)
    labels = {e.type for e in graph.edges}
    assert "relation.isa" not in labels
    assert "pet" not in {n.label for n in graph.nodes}
