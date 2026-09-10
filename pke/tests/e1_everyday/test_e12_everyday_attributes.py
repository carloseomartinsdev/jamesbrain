"""E1.2 — Everyday Attributes (name, brand, model) + vehicle ownership."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.ask import AskService
from pke.application.ask_results import AskStatus
from pke.application.clock import FixedClock
from pke.application.ingest import IngestService
from pke.application.results import IngestStatus
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.attribute_registry import (
    is_registered_dimension,
    registered_dimension_keys,
)
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.semantic.self_repair import apply_e1_self_repairs
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.ontology.seeds import core_concept_id
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.resolution.context import PersonalContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = "u-e12") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-e12") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _ingest_proposal(proposal: SemanticProposal, db: Path, user: UserContext):
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    svc = IngestService(
        FakeInterpreter({proposal.raw_input: outcome.ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    return svc.ingest(proposal.raw_input, user, _session(user.user_id)), outcome


def _ask_proposal(proposal: SemanticProposal, db: Path, user: UserContext):
    from pke.interpretation.semantic.self_repair import apply_e1_self_repairs

    repaired = apply_e1_self_repairs(proposal)
    outcome = proposal_to_query_ir(repaired)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    ask = AskService(
        FakeInterpreter({proposal.raw_input: outcome.query_ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    return ask.ask(proposal.raw_input, user, _session(user.user_id)), outcome


def _name_assert(raw: str | None = None, *, name: str = "Carlos") -> SemanticProposal:
    text = raw or f"Meu nome é {name}."
    return SemanticProposal(
        raw_input=text,
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text=name, kind_hint="person", reference_kind="named", confidence=1.0
        ),
        attribute_expression=f"name is {name}",
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )


def _vehicle_assert(raw: str, expr: str | None = None) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="carro", kind_hint="vehicle", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression=expr or raw,
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )


def test_e12_registry_controlled() -> None:
    from pke.interpretation.semantic.attribute_registry import get_dimension

    keys = registered_dimension_keys()
    assert "name" in keys and "brand" in keys and "model" in keys
    assert is_registered_dimension("name")
    assert not is_registered_dimension("favorite_color_hex")
    color = get_dimension("color")
    assert color is not None and color.singleton_current is True


def test_e12_c01_name_committed(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e12-c01")
    user = _user()
    result, outcome = _ingest_proposal(_name_assert(), db, user)
    assert result.status is IngestStatus.COMMITTED
    assert outcome.ir is not None and outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "name"
    assert outcome.ir.attribute.text_value == "Carlos"
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        attrs = uow.attributes.for_entity_dimension(
            user.user_id, binding.entity_id, "name"
        )
        assert len(attrs) == 1
        assert attrs[0].text_value == "Carlos"
        assert attrs[0].is_current is True
        uow.commit()


def test_e12_name_update_preserves_source_fk(tmp_path: Path) -> None:
    """Closing the previous singleton name must not blank source_id (FK)."""
    db = fresh_db_path(tmp_path, "e12-name-upd")
    user = _user()
    first, _ = _ingest_proposal(_name_assert(name="Carlos"), db, user)
    assert first.status is IngestStatus.COMMITTED
    second, _ = _ingest_proposal(_name_assert(name="Pedro"), db, user)
    assert second.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        attrs = uow.attributes.for_entity_dimension(
            user.user_id, binding.entity_id, "name"
        )
        assert len(attrs) == 2
        current = [a for a in attrs if a.is_current]
        closed = [a for a in attrs if not a.is_current]
        assert len(current) == 1 and len(closed) == 1
        assert current[0].text_value == "Pedro"
        assert closed[0].text_value == "Carlos"
        assert current[0].source is not None and current[0].source.id
        assert closed[0].source is not None and closed[0].source.id
        uow.commit()


@pytest.mark.parametrize(
    "raw",
    ["Qual é o meu nome?", "Como eu me chamo?"],
)
def test_e12_c02_name_query_cross_conversation(tmp_path: Path, raw: str) -> None:
    db = fresh_db_path(tmp_path, "e12-c02")
    user = _user()
    write, _ = _ingest_proposal(_name_assert(), db, user)
    assert write.status is IngestStatus.COMMITTED
    # Fresh session — no conversation history fallback
    query = SemanticProposal(
        raw_input=raw,
        utterance_kind="query",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="eu", kind_hint="person", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="nome",
        stable_property_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )
    ask_result, _ = _ask_proposal(query, db, user)
    assert ask_result.status is AskStatus.ANSWERED
    assert ask_result.query_result is not None
    values = ask_result.query_result.attribute_values
    assert values and values[0].text_value == "Carlos"


def test_e12_neg_named_event_not_self_name(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e12-neg-event")
    user = _user()
    proposal = SemanticProposal(
        raw_input="Eu vi Carlos ontem.",
        utterance_kind="assert",
        primitive_hint="event",
        subject=SemanticEntityMention(
            text="Carlos", kind_hint="person", reference_kind="named", confidence=1.0
        ),
        event_expression="viu Carlos",
        change_semantics=True,
        temporal=SemanticTime(original_text="ontem", relative_day="yesterday"),
        confidence=1.0,
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.subject is not None
    assert repaired.subject.reference_kind == "named"
    outcome = proposal_to_canonical_ir(proposal)
    # Must not become self.name attribute
    if outcome.ir is not None and getattr(outcome.ir, "attribute", None) is not None:
        assert outcome.ir.attribute.dimension_key != "name" or outcome.ir.attribute.subject.text != "eu"


def test_e12_neg_friend_name(tmp_path: Path) -> None:
    proposal = SemanticProposal(
        raw_input="O nome do meu amigo é João.",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="amigo", kind_hint="person", reference_kind="named", confidence=1.0
        ),
        attribute_expression="name is João",
        stable_property_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.subject is not None
    assert repaired.subject.reference_kind == "named"
    assert repaired.subject.text == "amigo"


def test_e12_c03_vehicle_brand(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e12-c03")
    user = _user()
    result, outcome = _ingest_proposal(
        _vehicle_assert("Meu carro é um Honda.", "Honda"), db, user
    )
    assert result.status is IngestStatus.COMMITTED
    assert outcome.ir is not None and outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "brand"
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        owns = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current
        ]
        assert len(owns) == 1
        vehicle_id = owns[0].to_id
        vehicle = uow.entities.get(user.user_id, vehicle_id)
        assert vehicle is not None
        assert vehicle.type_id in {
            core_concept_id("entity.vehicle"),
            core_concept_id("entity.automobile"),
        }
        brands = uow.attributes.for_entity_dimension(user.user_id, vehicle_id, "brand")
        assert brands and brands[0].text_value == "Honda"
        # Not flattened on principal
        principal_brands = uow.attributes.for_entity_dimension(
            user.user_id, binding.entity_id, "brand"
        )
        assert principal_brands == []
        uow.commit()


def test_e12_c04_brand_and_model(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e12-c04")
    user = _user()
    result, outcome = _ingest_proposal(
        _vehicle_assert("Meu carro é um Honda Civic.", "Honda Civic"), db, user
    )
    assert result.status is IngestStatus.COMMITTED
    assert outcome.ir is not None
    assert outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "brand"
    companion_dims = {a.dimension_key for a in outcome.ir.additional_attributes}
    assert "model" in companion_dims
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        owns = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current
        ]
        vehicle_id = owns[0].to_id
        brands = uow.attributes.for_entity_dimension(user.user_id, vehicle_id, "brand")
        models = uow.attributes.for_entity_dimension(user.user_id, vehicle_id, "model")
        assert brands[0].text_value == "Honda"
        assert models[0].text_value == "Civic"
        uow.commit()


def test_e12_c05_same_vehicle_color(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e12-c05")
    user = _user()
    r1, _ = _ingest_proposal(
        _vehicle_assert("Meu carro é um Honda Civic.", "Honda Civic"), db, user
    )
    assert r1.status is IngestStatus.COMMITTED
    r2, _ = _ingest_proposal(
        _vehicle_assert("Meu carro é vermelho.", "cor vermelho"), db, user
    )
    assert r2.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        owns = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current
        ]
        assert len(owns) == 1, "must enrich same vehicle Entity"
        vehicle_id = owns[0].to_id
        colors = uow.attributes.for_entity_dimension(user.user_id, vehicle_id, "color")
        assert colors and colors[0].text_value == "vermelho"
        vehicles = [
            e
            for e in uow.entities.all_for_user(user.user_id)
            if e.id != binding.entity_id
            and e.type_id
            in {
                core_concept_id("entity.vehicle"),
                core_concept_id("entity.automobile"),
            }
        ]
        assert len(vehicles) == 1
        uow.commit()


def test_e12_color_update_closes_previous(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e12-color-upd")
    user = _user()
    _ingest_proposal(_vehicle_assert("Meu carro é um Honda Civic.", "Honda Civic"), db, user)
    r1, _ = _ingest_proposal(
        _vehicle_assert("Meu carro é vermelho.", "cor vermelho"), db, user
    )
    r2, _ = _ingest_proposal(
        _vehicle_assert("Meu carro é azul.", "cor azul"), db, user
    )
    assert r1.status is IngestStatus.COMMITTED
    assert r2.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        owns = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current
        ]
        vehicle_id = owns[0].to_id
        colors = uow.attributes.for_entity_dimension(user.user_id, vehicle_id, "color")
        current = [a for a in colors if a.is_current]
        closed = [a for a in colors if not a.is_current]
        assert len(current) == 1 and len(closed) == 1
        assert current[0].text_value == "azul"
        assert closed[0].text_value == "vermelho"
        assert current[0].supersedes_id == closed[0].id
        uow.commit()
    query = SemanticProposal(
        raw_input="Qual é a cor do meu carro?",
        utterance_kind="query",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="carro", kind_hint="vehicle", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="cor",
        stable_property_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )
    ask_result, _ = _ask_proposal(query, db, user)
    assert ask_result.status is AskStatus.ANSWERED
    assert ask_result.query_result is not None
    values = ask_result.query_result.attribute_values
    assert len(values) == 1
    assert values[0].text_value == "azul"


def test_e12_c06_color_query(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e12-c06")
    user = _user()
    _ingest_proposal(_vehicle_assert("Meu carro é um Honda Civic.", "Honda Civic"), db, user)
    _ingest_proposal(_vehicle_assert("Meu carro é vermelho.", "cor vermelho"), db, user)
    query = SemanticProposal(
        raw_input="Qual é a cor do meu carro?",
        utterance_kind="query",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="carro", kind_hint="vehicle", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="cor",
        stable_property_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )
    ask_result, _ = _ask_proposal(query, db, user)
    assert ask_result.status is AskStatus.ANSWERED
    assert ask_result.query_result is not None
    assert ask_result.query_result.attribute_values[0].text_value == "vermelho"


def test_e12_c07_vehicle_identity_query(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e12-c07")
    user = _user()
    _ingest_proposal(_vehicle_assert("Meu carro é um Honda Civic.", "Honda Civic"), db, user)
    query = SemanticProposal(
        raw_input="Qual é o meu carro?",
        utterance_kind="query",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="carro", kind_hint="vehicle", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="marca",
        stable_property_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )
    ask_result, _ = _ask_proposal(query, db, user)
    assert ask_result.status is AskStatus.ANSWERED
    assert ask_result.query_result is not None
    label = ask_result.query_result.attribute_values[0].text_value
    assert label == "Honda Civic"


def test_e12_cross_user_isolation(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e12-xu")
    a = _user("u-a")
    b = _user("u-b")
    _ingest_proposal(_name_assert(), db, a)
    _ingest_proposal(_vehicle_assert("Meu carro é um Honda.", "Honda"), db, a)
    query = SemanticProposal(
        raw_input="Qual é o meu nome?",
        utterance_kind="query",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="eu", kind_hint="person", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="nome",
        stable_property_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )
    ask_b, _ = _ask_proposal(query, db, b)
    assert ask_b.status in {AskStatus.NO_RESULTS, AskStatus.REJECTED, AskStatus.UNSUPPORTED}
    if ask_b.query_result and ask_b.query_result.attribute_values:
        assert ask_b.query_result.attribute_values[0].text_value != "Carlos"


def test_e12_unknown_dimension_no_commit() -> None:
    proposal = SemanticProposal(
        raw_input="Meu aura é azul-cobalto.",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="eu", kind_hint="person", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="aura azul-cobalto",
        stable_property_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is None or outcome.ir.attribute is None
