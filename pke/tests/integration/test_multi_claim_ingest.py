"""ADR 0086 — Semantic decomposition & multi-claim ingest.

Interpreter-supplied claims; Engine does not re-read raw_input or learn Portuguese.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.clock import FixedClock
from pke.application.ingest import IngestService
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.claims import relation_key_from_predicate
from pke.interpretation.semantic.models import (
    PrimitiveKind,
    SemanticClaim,
    SemanticClaimKind,
    SemanticClaimOrigin,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.router import collect_assertions
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.ontology.learned import learned_concept_id
from pke.ontology.seeds import core_concept_id
from pke.persist import open_sqlite_uow
from pke.resolution.context import PersonalContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW

OPAQUE = "OPAQUE-MULTICLAIM-001"


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = "u-mc") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-mc") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _self() -> SemanticEntityMention:
    return SemanticEntityMention(
        text="self", kind_hint="person", reference_kind="contextual", confidence=1.0
    )


def _named(
    text: str,
    *,
    kind: str | None = "thing",
    class_hint: str | None = None,
) -> SemanticEntityMention:
    return SemanticEntityMention(
        text=text,
        kind_hint=kind,  # type: ignore[arg-type]
        class_hint=class_hint,
        reference_kind="named",
        confidence=1.0,
    )


def _possessed(
    text: str,
    *,
    kind: str | None = "thing",
    class_hint: str | None = None,
) -> SemanticEntityMention:
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


def test_relation_key_owns_is_canonical() -> None:
    assert relation_key_from_predicate("owns") == "relation.owns"
    assert relation_key_from_predicate("relation.owns") == "relation.owns"


def test_collect_assertions_keeps_measurement_beside_relation() -> None:
    proposal = SemanticProposal(
        raw_input="house area",
        primitive_hint="relation",
        subject=_self(),
        object=_possessed("house", class_hint="house"),
        relation_expression="owns",
        link_semantics=True,
        measurement_semantics=True,
        measurable_dimension_key="area",
        measurement_numeric_value="200",
        measurement_unit="m²",
        temporal=_ongoing(),
    )
    kinds = {f.primitive for f in collect_assertions(proposal)}
    assert PrimitiveKind.RELATION in kinds
    assert PrimitiveKind.MEASUREMENT in kinds


def luna_proposal(raw: str) -> SemanticProposal:
    luna = _named("Luna", class_hint="cat")
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="assert",
        primitive_hint="relation",
        subject=_self(),
        object=luna,
        relation_expression="owns",
        link_semantics=True,
        classification_semantics=True,
        temporal=_ongoing(),
        claims=[
            _claim(kind=SemanticClaimKind.ENTITY, subject=luna),
            _claim(
                kind=SemanticClaimKind.CLASSIFICATION,
                subject=luna,
                class_hint="cat",
            ),
            _claim(
                kind=SemanticClaimKind.RELATION,
                predicate="owns",
                subject=_self(),
                object=luna,
            ),
            _claim(
                kind=SemanticClaimKind.INTRINSIC_PROPERTY,
                subject=luna,
                dimension="name",
                value_text="Luna",
            ),
            _claim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=luna,
                dimension="sex",
                value_text="female",
            ),
        ],
    )


def _attrs(uow, user_id: str, entity_id: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for row in uow.attributes.for_entity(user_id, entity_id):
        if row.is_current:
            out[row.dimension_key] = row.text_value
    return out


@pytest.mark.parametrize(
    "raw",
    [
        "Minha gata se chama Luna.",
        "My cat is called Luna.",
        "Mi gata se llama Luna.",
    ],
)
def test_a_luna_pt_en_es(tmp_path: Path, raw: str) -> None:
    db = fresh_db_path(tmp_path, "mc-luna")
    user = _user("u-luna")
    result, outcome = _ingest(luna_proposal(raw), db, user)
    assert result.status is IngestStatus.COMMITTED
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.owns"
    dims = {a.dimension_key for a in [outcome.ir.attribute, *outcome.ir.additional_attributes] if a}
    assert "sex" in dims
    assert "name" not in dims
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        owns = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current
        ]
        assert len(owns) == 1
        luna = uow.entities.get(user.user_id, owns[0].to_id)
        assert luna is not None
        assert luna.canonical_name == "Luna"
        assert luna.type_id == learned_concept_id("entity.learned.cat")
        attrs = _attrs(uow, user.user_id, luna.id)
        assert attrs.get("sex") == "female"
        assert "name" not in attrs
        uow.commit()


def test_opaque_raw_input_same_claims(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mc-opaque")
    user = _user("u-opaque")
    proposal = luna_proposal("Minha gata se chama Luna.")
    live = proposal_to_canonical_ir(proposal)
    opaque = proposal_to_canonical_ir(proposal.model_copy(update={"raw_input": OPAQUE}))
    assert live.ir is not None and opaque.ir is not None
    assert live.ir.relation is not None and opaque.ir.relation is not None
    assert live.ir.relation.type.key == opaque.ir.relation.type.key
    live_dims = sorted(
        a.dimension_key
        for a in [live.ir.attribute, *live.ir.additional_attributes]
        if a is not None
    )
    opaque_dims = sorted(
        a.dimension_key
        for a in [opaque.ir.attribute, *opaque.ir.additional_attributes]
        if a is not None
    )
    assert live_dims == opaque_dims
    result, _ = _ingest(proposal, db, user, opaque=True)
    assert result.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        owns = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current
        ]
        luna = uow.entities.get(user.user_id, owns[0].to_id)
        assert luna is not None and luna.canonical_name == "Luna"
        assert _attrs(uow, user.user_id, luna.id).get("sex") == "female"
        uow.commit()


def test_b_vehicle_model_not_identity(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mc-car")
    user = _user("u-car")
    car = _possessed("car", kind="vehicle", class_hint="automobile")
    proposal = SemanticProposal(
        raw_input="Meu carro é um Civic azul.",
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
            _claim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=car,
                dimension="model",
                value_text="Civic",
            ),
            _claim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=car,
                dimension="color",
                value_text="blue",
            ),
        ],
    )
    result, outcome = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED
    assert outcome.ir is not None
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        owns = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current
        ]
        vehicle = uow.entities.get(user.user_id, owns[0].to_id)
        assert vehicle is not None
        assert vehicle.canonical_name != "Civic"
        assert vehicle.type_id in {
            core_concept_id("entity.automobile"),
            core_concept_id("entity.vehicle"),
        }
        attrs = _attrs(uow, user.user_id, vehicle.id)
        assert attrs.get("model") == "Civic"
        assert attrs.get("color") == "blue"
        uow.commit()


@pytest.mark.parametrize(
    "raw",
    ["Meu carro é azul.", "My car is blue.", "Mi coche es azul."],
)
def test_car_color_pt_en_es(tmp_path: Path, raw: str) -> None:
    db = fresh_db_path(tmp_path, "mc-car-color")
    user = _user("u-car-color")
    car = _possessed("car", kind="vehicle", class_hint="automobile")
    proposal = SemanticProposal(
        raw_input=raw,
        primitive_hint="attribute",
        subject=_self(),
        object=car,
        relation_expression="owns",
        link_semantics=True,
        temporal=_ongoing(),
        claims=[
            _claim(kind=SemanticClaimKind.RELATION, predicate="owns", subject=_self(), object=car),
            _claim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=car,
                dimension="color",
                value_text="blue",
            ),
        ],
    )
    result, _ = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        owns = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current
        ]
        vehicle = uow.entities.get(user.user_id, owns[0].to_id)
        assert _attrs(uow, user.user_id, vehicle.id).get("color") == "blue"
        uow.commit()


def test_c_person_profession(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mc-carlos")
    user = _user("u-carlos")
    carlos = _named("Carlos", kind="person", class_hint="person")
    proposal = SemanticProposal(
        raw_input="Meu irmão Carlos é médico.",
        primitive_hint="relation",
        subject=carlos,
        object=_self(),
        relation_expression="sibling of",
        link_semantics=True,
        classification_semantics=True,
        temporal=_ongoing(),
        claims=[
            _claim(kind=SemanticClaimKind.CLASSIFICATION, subject=carlos, class_hint="person"),
            _claim(
                kind=SemanticClaimKind.RELATION,
                predicate="sibling of",
                subject=carlos,
                object=_self(),
            ),
            _claim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=carlos,
                dimension="profession",
                value_text="doctor",
            ),
        ],
    )
    result, outcome = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED
    assert outcome.ir is not None
    rel = outcome.ir.relation
    assert rel is not None
    assert "sibling" in rel.type.key
    with open_sqlite_uow(db) as uow:
        people = [
            e
            for e in uow.entities.all_for_user(user.user_id)
            if e.canonical_name == "Carlos"
        ]
        assert people
        attrs = _attrs(uow, user.user_id, people[0].id)
        assert attrs.get("profession") == "doctor"
        uow.commit()


def test_d_house_measurement_and_location(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mc-house")
    user = _user("u-house")
    house = _possessed("house", class_hint="house")
    place = _named("Fortaleza", kind="place", class_hint="place")
    proposal = SemanticProposal(
        raw_input="Tenho uma casa de 200 m² em Fortaleza.",
        primitive_hint="relation",
        subject=_self(),
        object=house,
        relation_expression="owns",
        link_semantics=True,
        classification_semantics=True,
        temporal=_ongoing(),
        claims=[
            _claim(kind=SemanticClaimKind.CLASSIFICATION, subject=house, class_hint="house"),
            _claim(kind=SemanticClaimKind.RELATION, predicate="owns", subject=_self(), object=house),
            _claim(
                kind=SemanticClaimKind.MEASUREMENT,
                subject=house,
                dimension="area",
                numeric_value="200",
                unit="m²",
            ),
            _claim(
                kind=SemanticClaimKind.RELATION,
                predicate="located in",
                subject=house,
                object=place,
            ),
        ],
    )
    result, outcome = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED
    assert outcome.ir is not None
    assert outcome.ir.measurement is not None
    assert outcome.ir.measurement.dimension_key == "area"
    extra_rel = {r.type.key for r in outcome.ir.additional_relations}
    assert any("located" in k for k in extra_rel | {outcome.ir.relation.type.key})
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        owns = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current
        ]
        entity = uow.entities.get(user.user_id, owns[0].to_id)
        meas = uow.measurements.for_entity(user.user_id, entity.id)
        assert meas and str(meas[0].numeric_value) in {"200", "200.0"}
        uow.commit()


def test_e_company_acme(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mc-acme")
    user = _user("u-acme")
    acme = _named("Acme", kind="organization", class_hint="company")
    place = _named("Fortaleza", kind="place", class_hint="place")
    proposal = SemanticProposal(
        raw_input="Minha empresa se chama Acme e fica em Fortaleza.",
        primitive_hint="relation",
        subject=acme,
        object=place,
        relation_expression="located in",
        link_semantics=True,
        classification_semantics=True,
        temporal=_ongoing(),
        claims=[
            _claim(kind=SemanticClaimKind.CLASSIFICATION, subject=acme, class_hint="company"),
            _claim(
                kind=SemanticClaimKind.INTRINSIC_PROPERTY,
                subject=acme,
                dimension="name",
                value_text="Acme",
            ),
            _claim(
                kind=SemanticClaimKind.RELATION,
                predicate="located in",
                subject=acme,
                object=place,
            ),
            _claim(
                kind=SemanticClaimKind.RELATION,
                predicate="owns",
                subject=_self(),
                object=acme,
            ),
        ],
    )
    result, _ = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        found = [e for e in uow.entities.all_for_user(user.user_id) if e.canonical_name == "Acme"]
        assert found
        assert found[0].type_id == learned_concept_id("entity.learned.company")
        uow.commit()


def test_f_device_memory(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mc-nb")
    user = _user("u-nb")
    device = _possessed("notebook", class_hint="computer")
    proposal = SemanticProposal(
        raw_input="Meu notebook é um MacBook Pro cinza com 16 GB de memória.",
        primitive_hint="attribute",
        subject=_self(),
        object=device,
        relation_expression="owns",
        link_semantics=True,
        temporal=_ongoing(),
        claims=[
            _claim(kind=SemanticClaimKind.CLASSIFICATION, subject=device, class_hint="computer"),
            _claim(kind=SemanticClaimKind.RELATION, predicate="owns", subject=_self(), object=device),
            _claim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=device,
                dimension="model",
                value_text="MacBook Pro",
            ),
            _claim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=device,
                dimension="color",
                value_text="gray",
            ),
            _claim(
                kind=SemanticClaimKind.MEASUREMENT,
                subject=device,
                dimension="memory_capacity",
                numeric_value="16",
                unit="GB",
            ),
        ],
    )
    result, _ = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        owns = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.key == "relation.owns" and r.is_current
        ]
        ent = uow.entities.get(user.user_id, owns[0].to_id)
        attrs = _attrs(uow, user.user_id, ent.id)
        assert attrs.get("model") == "MacBook Pro"
        assert attrs.get("color") == "gray"
        meas = uow.measurements.for_entity(user.user_id, ent.id)
        assert meas and str(meas[0].numeric_value) in {"16", "16.0"}
        uow.commit()


def test_unknown_synthesizer(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mc-syn")
    user = _user("u-syn")
    aurora = _named("Aurora", class_hint="synthesizer")
    proposal = SemanticProposal(
        raw_input="Meu sintetizador se chama Aurora e é vermelho.",
        primitive_hint="relation",
        subject=_self(),
        object=aurora,
        relation_expression="owns",
        link_semantics=True,
        temporal=_ongoing(),
        claims=[
            _claim(kind=SemanticClaimKind.CLASSIFICATION, subject=aurora, class_hint="synthesizer"),
            _claim(kind=SemanticClaimKind.RELATION, predicate="owns", subject=_self(), object=aurora),
            _claim(
                kind=SemanticClaimKind.INTRINSIC_PROPERTY,
                subject=aurora,
                dimension="name",
                value_text="Aurora",
            ),
            _claim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=aurora,
                dimension="color",
                value_text="red",
            ),
        ],
    )
    result, _ = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        found = [e for e in uow.entities.all_for_user(user.user_id) if e.canonical_name == "Aurora"]
        assert found
        assert found[0].type_id == learned_concept_id("entity.learned.synthesizer")
        assert _attrs(uow, user.user_id, found[0].id).get("color") == "red"
        uow.commit()


def test_unknown_drone(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mc-drone")
    user = _user("u-drone")
    atlas = _named("Atlas", class_hint="drone")
    proposal = SemanticProposal(
        raw_input="Meu drone Atlas pesa 850 gramas e é preto.",
        primitive_hint="relation",
        subject=_self(),
        object=atlas,
        relation_expression="owns",
        link_semantics=True,
        temporal=_ongoing(),
        claims=[
            _claim(kind=SemanticClaimKind.CLASSIFICATION, subject=atlas, class_hint="drone"),
            _claim(kind=SemanticClaimKind.RELATION, predicate="owns", subject=_self(), object=atlas),
            _claim(
                kind=SemanticClaimKind.MEASUREMENT,
                subject=atlas,
                dimension="weight",
                numeric_value="850",
                unit="g",
            ),
            _claim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=atlas,
                dimension="color",
                value_text="black",
            ),
        ],
    )
    result, _ = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED
    assert result.claims.rejected == 0
    with open_sqlite_uow(db) as uow:
        found = [e for e in uow.entities.all_for_user(user.user_id) if e.canonical_name == "Atlas"]
        assert found
        assert found[0].type_id == learned_concept_id("entity.learned.drone")
        assert _attrs(uow, user.user_id, found[0].id).get("color") == "black"
        meas = uow.measurements.for_entity(user.user_id, found[0].id)
        assert meas
        uow.commit()


def test_assumed_not_persisted(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mc-assumed")
    user = _user("u-assumed")
    luna = _named("Luna", class_hint="cat")
    proposal = SemanticProposal(
        raw_input="Luna é uma gata.",
        primitive_hint="type",
        subject=luna,
        classification_semantics=True,
        temporal=_ongoing(),
        claims=[
            _claim(kind=SemanticClaimKind.ENTITY, subject=luna),
            _claim(kind=SemanticClaimKind.CLASSIFICATION, subject=luna, class_hint="cat"),
            _claim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=luna,
                dimension="color",
                value_text="has_fur",
                origin=SemanticClaimOrigin.ASSUMED,
            ),
        ],
    )
    result, _ = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED
    assert result.claims.rejected >= 1
    with open_sqlite_uow(db) as uow:
        found = [e for e in uow.entities.all_for_user(user.user_id) if e.canonical_name == "Luna"]
        assert found
        assert found[0].type_id == learned_concept_id("entity.learned.cat")
        assert "color" not in _attrs(uow, user.user_id, found[0].id)
        uow.commit()


@pytest.mark.xfail(reason="ADR 0086: ontology hierarchy deferred — cat ⊂ animal not materialized")
def test_derived_subclass_not_this_increment(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mc-derived")
    user = _user("u-derived")
    result, _ = _ingest(luna_proposal("Minha gata se chama Luna."), db, user)
    assert result.status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        found = [e for e in uow.entities.all_for_user(user.user_id) if e.canonical_name == "Luna"]
        assert found
        assert found[0].type_id == learned_concept_id("entity.learned.animal")
        uow.commit()
