"""ADR 0090 — owned-object semantic decomposition (domain-independent)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.ask import AskService
from pke.application.ask_results import AskStatus
from pke.application.clock import FixedClock
from pke.application.ingest import IngestService
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticClaimKind,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.owned_object import identity_mentions
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.semantic.self_repair import apply_e1_self_repairs, last_applied_repairs
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.ontology.learned import learned_concept_id
from pke.ontology.seeds import core_concept_id
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.resolution.context import PersonalContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW

OPAQUE = "OPAQUE-OWNED-OBJECT-001"


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = "u-owned") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-owned") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _self() -> SemanticEntityMention:
    return SemanticEntityMention(
        text="self", kind_hint="person", reference_kind="contextual", confidence=1.0
    )


def _named(text: str, *, kind: str | None = "thing", class_hint: str | None = None):
    return SemanticEntityMention(
        text=text,
        kind_hint=kind,  # type: ignore[arg-type]
        class_hint=class_hint,
        reference_kind="named",
        confidence=1.0,
    )


def _possessed(text: str, *, kind: str | None = "thing", class_hint: str | None = None):
    return SemanticEntityMention(
        text=text,
        kind_hint=kind,  # type: ignore[arg-type]
        class_hint=class_hint,
        reference_kind="possessive",
        confidence=1.0,
    )


def _ongoing() -> SemanticTime:
    return SemanticTime(occurrence_aspect="ongoing")


def _claim(**kwargs: object) -> SemanticClaim:
    return SemanticClaim.model_validate(kwargs)


def _owned_copula(
    *,
    raw: str,
    noun: str,
    class_hint: str,
    kind: str | None = "thing",
    dimension: str,
    value: str,
    extra_claims: list[SemanticClaim] | None = None,
    object_named: SemanticEntityMention | None = None,
) -> SemanticProposal:
    owned = _possessed(noun, kind=kind, class_hint=class_hint)
    claims = [
        _claim(kind=SemanticClaimKind.CLASSIFICATION, subject=owned, class_hint=class_hint),
        _claim(kind=SemanticClaimKind.RELATION, predicate="owns", subject=_self(), object=owned),
        _claim(
            kind=SemanticClaimKind.ATTRIBUTE,
            subject=owned,
            dimension=dimension,
            value_text=value,
        ),
        *(extra_claims or []),
    ]
    mentioned = [object_named] if object_named is not None else []
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=_self(),
        object=object_named or owned,
        entities_mentioned=mentioned,
        relation_expression="owns",
        link_semantics=True,
        classification_semantics=True,
        temporal=_ongoing(),
        claims=claims,
    )


def _ingest(proposal: SemanticProposal, db: Path, user: UserContext, *, opaque: bool = False):
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    ir = outcome.ir
    raw = OPAQUE if opaque else proposal.raw_input
    if opaque:
        ir = ir.model_copy(update={"raw_input": OPAQUE})
    ontology = OntologyRegistry.with_core_seeds()
    svc = IngestService(
        FakeInterpreter({raw: ir}),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    return svc.ingest(raw, user, _session(user.user_id)), outcome


def _ask(proposal: SemanticProposal, db: Path, user: UserContext):
    outcome = proposal_to_query_ir(proposal)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    ask = AskService(
        FakeInterpreter({proposal.raw_input: outcome.query_ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    return ask.ask(proposal.raw_input, user, _session(user.user_id)), outcome


def _attrs(uow, user_id: str, entity_id: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for row in uow.attributes.for_entity(user_id, entity_id):
        if row.is_current:
            out[row.dimension_key] = row.text_value
    return out


def _owned_of_type(uow, user_id: str, type_ids: set[str]) -> list:
    binding = uow.principal_bindings.get(user_id)
    assert binding is not None
    owns = [
        r
        for r in uow.relations.for_entity(user_id, binding.entity_id)
        if r.key == "relation.owns" and r.is_current
    ]
    found = []
    for rel in owns:
        entity = uow.entities.get(user_id, rel.to_id)
        if entity is not None and entity.type_id in type_ids:
            found.append((entity, rel))
    return found, binding


def _car_proposal(raw: str, *, value: str = "City") -> SemanticProposal:
    city = _named("City", kind="vehicle", class_hint="vehicle")
    return _owned_copula(
        raw=raw,
        noun="carro",
        class_hint="automobile",
        kind="vehicle",
        dimension="model",
        value=value,
        object_named=city,
    )


def test_repair_skips_when_claims_exist() -> None:
    proposal = _car_proposal("meu carro é um City")
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.claims == proposal.claims
    assert repaired.primitive_hint == proposal.primitive_hint
    assert "vehicle_attribute_repair" not in last_applied_repairs()
    texts = {m.text for m in identity_mentions(repaired)}
    assert "carro" in texts
    assert "City" not in texts


def test_city_is_not_an_identity_mention() -> None:
    proposal = _car_proposal("meu carro é um City")
    assert {m.text for m in identity_mentions(proposal)} == {"carro", "self"}


def test_no_existing_car_creates_owned_model(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "owned-city")
    user = _user("u-city")
    result, outcome = _ingest(_car_proposal("meu carro é um City"), db, user)
    assert result.status is IngestStatus.COMMITTED, result.issues
    assert outcome.ir is not None
    mentioned = {e.text.casefold() for e in outcome.ir.entities_mentioned}
    assert "city" not in mentioned
    assert "carro" in mentioned
    mat = result.materialization
    assert mat is not None
    tally = result.claims
    assert tally.received == 3
    assert tally.valid == 3
    assert tally.committed == 3
    assert tally.deferred == 0
    with open_sqlite_uow(db) as uow:
        cars, binding = _owned_of_type(
            uow, user.user_id, {core_concept_id("entity.automobile"), core_concept_id("entity.vehicle")}
        )
        created = [eid for eid in mat.created_entity_ids if eid != binding.entity_id]
        assert len(created) == 1
        assert len(mat.relation_ids) >= 1
        assert len(mat.attribute_ids) == 1
        assert len(cars) == 1
        car, _rel = cars[0]
        assert car.canonical_name.lower() not in {"carro", "city"}
        assert car.canonical_name.startswith("owned:")
        assert car.type_id == core_concept_id("entity.automobile")
        assert _attrs(uow, user.user_id, car.id).get("model") == "City"
        names = [e.canonical_name for e in uow.entities.all_for_user(user.user_id)]
        assert "City" not in names
        uow.commit()


def test_existing_unique_car_is_reused(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "owned-reuse")
    user = _user("u-reuse")
    first, _ = _ingest(_car_proposal("meu carro é um City"), db, user)
    assert first.status is IngestStatus.COMMITTED
    second, _ = _ingest(
        _owned_copula(
            raw="meu carro é azul",
            noun="carro",
            class_hint="automobile",
            kind="vehicle",
            dimension="color",
            value="blue",
        ),
        db,
        user,
    )
    assert second.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        cars, _binding = _owned_of_type(
            uow, user.user_id, {core_concept_id("entity.automobile")}
        )
        assert len(cars) == 1
        car = cars[0][0]
        assert first.materialization is not None
        assert car.id in first.materialization.created_entity_ids
        assert second.materialization is not None
        assert car.id in second.materialization.reused_entity_ids
        attrs = _attrs(uow, user.user_id, car.id)
        assert attrs.get("model") == "City"
        assert attrs.get("color") == "blue"
        uow.commit()


def test_two_cars_do_not_update_arbitrarily(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "owned-two")
    user = _user("u-two")
    for name in ("CarA", "CarB"):
        named = _named(name, kind="vehicle", class_hint="automobile")
        proposal = SemanticProposal(
            raw_input=f"eu tenho um carro chamado {name}",
            utterance_kind="assert",
            primitive_hint="relation",
            subject=_self(),
            object=named,
            relation_expression="owns",
            link_semantics=True,
            temporal=_ongoing(),
            claims=[
                _claim(kind=SemanticClaimKind.CLASSIFICATION, subject=named, class_hint="automobile"),
                _claim(
                    kind=SemanticClaimKind.RELATION,
                    predicate="owns",
                    subject=_self(),
                    object=named,
                ),
                _claim(
                    kind=SemanticClaimKind.INTRINSIC_PROPERTY,
                    subject=named,
                    dimension="name",
                    value_text=name,
                ),
            ],
        )
        written, _ = _ingest(proposal, db, user)
        assert written.status is IngestStatus.COMMITTED, written.issues
    third, _ = _ingest(_car_proposal("meu carro é um City"), db, user)
    assert third.status in {IngestStatus.NEEDS_CLARIFICATION, IngestStatus.REJECTED}
    assert third.materialization is None
    with open_sqlite_uow(db) as uow:
        cars, _binding = _owned_of_type(
            uow, user.user_id, {core_concept_id("entity.automobile")}
        )
        assert len(cars) == 2
        for entity, _rel in cars:
            assert _attrs(uow, user.user_id, entity.id).get("model") != "City"
        uow.commit()


@pytest.mark.parametrize(
    ("raw", "noun", "class_hint", "dimension", "value", "type_key"),
    [
        ("Meu notebook é um ThinkPad.", "notebook", "computer", "model", "ThinkPad", "entity.learned.computer"),
        ("Minha câmera é uma Canon.", "camera", "camera", "brand", "Canon", "entity.learned.camera"),
        (
            "Meu sintetizador é um Minilogue.",
            "sintetizador",
            "synthesizer",
            "model",
            "Minilogue",
            "entity.learned.synthesizer",
        ),
    ],
)
def test_owned_object_unknown_domains(
    tmp_path: Path,
    raw: str,
    noun: str,
    class_hint: str,
    dimension: str,
    value: str,
    type_key: str,
) -> None:
    db = fresh_db_path(tmp_path, f"owned-{class_hint}")
    user = _user(f"u-{class_hint}")
    result, _ = _ingest(
        _owned_copula(
            raw=raw,
            noun=noun,
            class_hint=class_hint,
            dimension=dimension,
            value=value,
        ),
        db,
        user,
    )
    assert result.status is IngestStatus.COMMITTED, result.issues
    with open_sqlite_uow(db) as uow:
        owned, _binding = _owned_of_type(uow, user.user_id, {learned_concept_id(type_key)})
        assert len(owned) == 1
        entity = owned[0][0]
        assert entity.type_id == learned_concept_id(type_key)
        assert entity.canonical_name.casefold() not in {noun.casefold(), value.casefold()}
        assert _attrs(uow, user.user_id, entity.id).get(dimension) == value
        uow.commit()


@pytest.mark.parametrize(
    "raw",
    ["Meu carro é um City.", "My car is a City.", "Mi coche es un City."],
)
def test_owned_car_pt_en_es(tmp_path: Path, raw: str) -> None:
    db = fresh_db_path(tmp_path, "owned-lang")
    user = _user("u-lang")
    result, outcome = _ingest(_car_proposal(raw), db, user)
    assert result.status is IngestStatus.COMMITTED
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.owns"
    assert outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "model"
    assert outcome.ir.attribute.text_value == "City"
    with open_sqlite_uow(db) as uow:
        cars, _ = _owned_of_type(uow, user.user_id, {core_concept_id("entity.automobile")})
        assert len(cars) == 1
        assert _attrs(uow, user.user_id, cars[0][0].id).get("model") == "City"
        uow.commit()


def test_opaque_raw_input_same_graph(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "owned-opaque")
    user = _user("u-opaque")
    proposal = _car_proposal("meu carro é um City")
    live = proposal_to_canonical_ir(proposal)
    opaque = proposal_to_canonical_ir(proposal.model_copy(update={"raw_input": OPAQUE}))
    assert live.ir is not None and opaque.ir is not None
    assert live.ir.relation is not None and opaque.ir.relation is not None
    assert live.ir.relation.type.key == opaque.ir.relation.type.key
    assert live.ir.attribute is not None and opaque.ir.attribute is not None
    assert live.ir.attribute.dimension_key == opaque.ir.attribute.dimension_key
    result, _ = _ingest(proposal, db, user, opaque=True)
    assert result.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        cars, _ = _owned_of_type(uow, user.user_id, {core_concept_id("entity.automobile")})
        assert len(cars) == 1
        assert _attrs(uow, user.user_id, cars[0][0].id).get("model") == "City"
        uow.commit()


def test_identity_reuse_model_color_measurement(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "owned-seq")
    user = _user("u-seq")
    r1, _ = _ingest(_car_proposal("meu carro é um City"), db, user)
    r2, _ = _ingest(
        _owned_copula(
            raw="meu carro é azul",
            noun="carro",
            class_hint="automobile",
            kind="vehicle",
            dimension="color",
            value="blue",
        ),
        db,
        user,
    )
    car = _possessed("carro", kind="vehicle", class_hint="automobile")
    r3, _ = _ingest(
        SemanticProposal(
            raw_input="meu carro tem 50 mil km",
            utterance_kind="assert",
            primitive_hint="measurement",
            subject=car,
            object=car,
            measurement_semantics=True,
            measurable_dimension_key="odometer",
            measurement_numeric_value="50000",
            measurement_unit="km",
            temporal=_ongoing(),
            claims=[
                _claim(kind=SemanticClaimKind.CLASSIFICATION, subject=car, class_hint="automobile"),
                _claim(kind=SemanticClaimKind.RELATION, predicate="owns", subject=_self(), object=car),
                _claim(
                    kind=SemanticClaimKind.MEASUREMENT,
                    subject=car,
                    dimension="odometer",
                    numeric_value="50000",
                    unit="km",
                ),
            ],
        ),
        db,
        user,
    )
    assert r1.status is IngestStatus.COMMITTED
    assert r2.status is IngestStatus.COMMITTED
    assert r3.status is IngestStatus.COMMITTED, r3.issues
    with open_sqlite_uow(db) as uow:
        cars, binding = _owned_of_type(uow, user.user_id, {core_concept_id("entity.automobile")})
        assert len(cars) == 1
        entity = cars[0][0]
        owns = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current and r.to_id == entity.id
        ]
        assert len(owns) == 1
        attrs = _attrs(uow, user.user_id, entity.id)
        assert attrs.get("model") == "City"
        assert attrs.get("color") == "blue"
        meas = uow.measurements.for_entity(user.user_id, entity.id)
        assert meas and str(meas[0].numeric_value) in {"50000", "50000.0"}
        uow.commit()


def test_query_owns_and_model_same_entity(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "owned-query")
    user = _user("u-query")
    written, _ = _ingest(_car_proposal("meu carro é um City"), db, user)
    assert written.status is IngestStatus.COMMITTED
    owns_query = SemanticProposal(
        raw_input="eu tenho um carro?",
        utterance_kind="query",
        primitive_hint="relation",
        subject=_self(),
        object=SemanticEntityMention(
            text="carro",
            kind_hint="vehicle",
            reference_kind="class",
            class_hint="automobile",
            confidence=1.0,
        ),
        relation_expression="owns",
        link_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )
    answered, _ = _ask(owns_query, db, user)
    assert answered.status is AskStatus.ANSWERED, (answered.status, answered.issues)
    assert answered.query_result is not None
    assert answered.query_result.relation_answer == "yes"
    model_query = SemanticProposal(
        raw_input="qual o modelo do meu carro?",
        utterance_kind="query",
        primitive_hint="attribute",
        subject=_possessed("carro", kind="vehicle", class_hint="automobile"),
        attribute_expression="modelo",
        stable_property_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )
    model_asked, _ = _ask(model_query, db, user)
    assert model_asked.status is AskStatus.ANSWERED, (model_asked.status, model_asked.issues)
    assert model_asked.query_result is not None
    values = model_asked.query_result.attribute_values
    assert values and values[0].text_value == "City"
    with open_sqlite_uow(db) as uow:
        cars, _ = _owned_of_type(uow, user.user_id, {core_concept_id("entity.automobile")})
        assert len(cars) == 1
        assert cars[0][0].id in model_asked.resolved_entity_ids
        uow.commit()


def test_multi_claim_city_azul_same_entity(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "owned-blue")
    user = _user("u-blue")
    car = _possessed("carro", kind="vehicle", class_hint="automobile")
    proposal = SemanticProposal(
        raw_input="meu carro é um City azul",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=_self(),
        object=car,
        relation_expression="owns",
        link_semantics=True,
        classification_semantics=True,
        temporal=_ongoing(),
        claims=[
            _claim(kind=SemanticClaimKind.CLASSIFICATION, subject=car, class_hint="automobile"),
            _claim(kind=SemanticClaimKind.RELATION, predicate="owns", subject=_self(), object=car),
            _claim(kind=SemanticClaimKind.ATTRIBUTE, subject=car, dimension="model", value_text="City"),
            _claim(kind=SemanticClaimKind.ATTRIBUTE, subject=car, dimension="color", value_text="blue"),
        ],
    )
    result, _ = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        cars, _ = _owned_of_type(uow, user.user_id, {core_concept_id("entity.automobile")})
        assert len(cars) == 1
        attrs = _attrs(uow, user.user_id, cars[0][0].id)
        assert attrs.get("model") == "City"
        assert attrs.get("color") == "blue"
        uow.commit()
