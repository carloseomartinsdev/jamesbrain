"""ADR 0093 — Graph Semantic Core: domain-general primitives, not domain fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.ask_results import AskStatus
from pke.application.clock import FixedClock
from pke.application.ingest import IngestService
from pke.application.results import IngestStatus
from pke.domain.ontology import ConceptRef
from pke.domain.value_objects import EventStatus
from pke.domain.temporal_knowledge import OccurrenceStatus
from pke.interpretation import FakeInterpreter
from pke.interpretation.models import (
    EntityMention,
    IngestIntent,
    IngestIR,
    IrEvent,
    IrTime,
    MentionReferenceKind,
    QueryIR,
    QuerySpec,
)
from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticClaimKind,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.ontology.graph_semantic_core import GraphPrimitive, graph_primitive_for_claim
from pke.ontology.relation_metadata import (
    RelationConceptMetadata,
    RelationDirectionality,
    clear_learned_relation_metadata,
    register_learned_relation_metadata,
)
from pke.persist import open_sqlite_uow
from tests.discourse.test_cross_turn_reference_resolution import (
    _actor,
    _attr_texts,
    _continue_attr,
    _focus_ids,
    _harness,
    _ir_from_proposal,
    _named,
    _possessed,
    _register_write,
    _session,
)
from tests.discourse.test_discourse_write_followups import (
    _continue_write,
    _owned_named,
)
from tests.e1_everyday.test_identity_role_naming import (
    _ingest as _identity_ingest,
    _named as _id_named,
    _possessed as _id_possessed,
    _user as _id_user,
)
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW

SRC = Path(__file__).resolve().parents[2] / "src" / "pke"
OPAQUE_ENTITY = "OPAQUE-GSC-ENTITY"
OPAQUE_CLASS = "OPAQUE-GSC-CLASSIFICATION"
OPAQUE_PROP = "OPAQUE-GSC-PROPERTY"
OPAQUE_REL = "OPAQUE-GSC-RELATION"
OPAQUE_EVENT = "OPAQUE-GSC-EVENT"
OPAQUE_MEAS = "OPAQUE-GSC-MEASUREMENT"


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    yield
    clear_learned_relation_metadata()


def test_claim_kinds_map_to_graph_primitives() -> None:
    assert graph_primitive_for_claim(SemanticClaimKind.ENTITY) is GraphPrimitive.ENTITY
    assert (
        graph_primitive_for_claim(SemanticClaimKind.CLASSIFICATION)
        is GraphPrimitive.CLASSIFICATION
    )
    assert graph_primitive_for_claim(SemanticClaimKind.ATTRIBUTE) is GraphPrimitive.PROPERTY
    assert (
        graph_primitive_for_claim(SemanticClaimKind.INTRINSIC_PROPERTY)
        is GraphPrimitive.PROPERTY
    )
    assert graph_primitive_for_claim(SemanticClaimKind.RELATION) is GraphPrimitive.RELATION
    assert graph_primitive_for_claim(SemanticClaimKind.EVENT) is GraphPrimitive.EVENT
    assert graph_primitive_for_claim(SemanticClaimKind.MEASUREMENT) is GraphPrimitive.MEASUREMENT
    assert graph_primitive_for_claim(SemanticClaimKind.STATE) is None


@pytest.mark.parametrize(
    ("name", "class_hint"),
    [
        ("Casa da Praia", "house"),
        ("Luna", "cat"),
        ("Atlas", "computer"),
        ("Nimbus", "camera"),
        ("Aurora", "synthesizer"),
    ],
)
def test_owned_object_same_relation_primitive(
    tmp_path: Path, name: str, class_hint: str
) -> None:
    db = fresh_db_path(tmp_path, f"owns-{class_hint}")
    user = _id_user(f"u-owns-{class_hint}")
    proposal = _owned_named(f"eu tenho {name}", name, class_hint)
    result, outcome = _identity_ingest(proposal, db, user, opaque=True)
    assert result.status is IngestStatus.COMMITTED, result.issues
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.owns"
    with open_sqlite_uow(db) as uow:
        names = {e.canonical_name for e in uow.entities.all_for_user(user.user_id)}
        assert name in names
        assert class_hint not in names
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        rels = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.is_current and r.key == "relation.owns"
        ]
        assert any(
            uow.entities.get(user.user_id, r.to_id)
            and uow.entities.get(user.user_id, r.to_id).canonical_name == name
            for r in rels
        )
        uow.commit()


@pytest.mark.parametrize(
    ("name", "class_hint", "dimension", "value"),
    [
        ("Casa da Praia", "house", "bedrooms", "3"),
        ("Atlas", "computer", "memory", "32 GB"),
        ("Luna", "cat", "age", "4"),
        ("Acme", "organization", "headcount", "12"),
        ("Aurora", "synthesizer", "keys", "61"),
    ],
)
def test_property_same_primitive(
    tmp_path: Path, name: str, class_hint: str, dimension: str, value: str
) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, f"prop-{class_hint}")
    session = _session(user.user_id)
    seed = f"seed {name}"
    write = f"set {dimension}"
    query = f"get {dimension}"
    _register_write(interpreter, _owned_named(seed, name, class_hint))
    interpreter.on(write, _continue_write(dimension, value))
    interpreter.on(query, _continue_attr(dimension))
    first = ingest.ingest(seed, user, session)
    assert first.status is IngestStatus.COMMITTED, first.issues
    second = ingest.ingest(write, user, session)
    assert second.status is IngestStatus.COMMITTED, second.issues
    asked = ask.ask(query, user, session)
    assert asked.status is AskStatus.ANSWERED, (asked.status, asked.issues)
    assert _attr_texts(asked) == [value]


@pytest.mark.parametrize(
    ("noun", "lemma", "person"),
    [
        ("contador", "accountant", "Angelo"),
        ("advogada", "lawyer", "Marina"),
        ("arquiteto", "architect", "Paulo"),
        ("luthier", "luthier", "Renato"),
    ],
)
def test_professional_role_same_primitive(
    tmp_path: Path, noun: str, lemma: str, person: str
) -> None:
    db = fresh_db_path(tmp_path, f"role-{lemma}")
    user = _id_user(f"u-role-{lemma}")
    role = _id_possessed(noun, class_hint=lemma)
    named = _id_named(person)
    proposal = SemanticProposal(
        raw_input=OPAQUE_REL,
        utterance_kind="assert",
        primitive_hint="relation",
        subject=role,
        object=named,
        relation_expression="named",
        link_semantics=True,
        classification_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=role),
            SemanticClaim(
                kind=SemanticClaimKind.CLASSIFICATION, subject=role, class_hint=lemma
            ),
            SemanticClaim(
                kind=SemanticClaimKind.RELATION,
                predicate="named",
                subject=role,
                object=named,
            ),
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=named),
        ],
        confidence=1.0,
    )
    result, outcome = _identity_ingest(proposal, db, user, opaque=True)
    assert result.status is IngestStatus.COMMITTED, result.issues
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert "named" not in outcome.ir.relation.type.key
    assert lemma in outcome.ir.relation.type.key
    with open_sqlite_uow(db) as uow:
        people = [
            e
            for e in uow.entities.all_for_user(user.user_id)
            if e.canonical_name == person
        ]
        names = {e.canonical_name for e in uow.entities.all_for_user(user.user_id)}
        assert people, names
        assert noun not in names
        assert lemma not in names
        professions = [
            a.text_value
            for a in uow.attributes.for_entity(user.user_id, people[0].id)
            if a.is_current and a.dimension_key == "profession"
        ]
        assert professions == [lemma]
        uow.commit()


def test_profession_without_role_relation_is_not_principal_link(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "prof-only")
    user = _id_user("u-prof-only")
    angelo = _id_named("Angelo")
    proposal = SemanticProposal(
        raw_input=OPAQUE_PROP,
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=angelo,
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=angelo),
            SemanticClaim(
                kind=SemanticClaimKind.CLASSIFICATION, subject=angelo, class_hint="person"
            ),
            SemanticClaim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=angelo,
                dimension="profession",
                value_text="accountant",
            ),
        ],
        confidence=1.0,
    )
    result, _ = _identity_ingest(proposal, db, user, opaque=True)
    assert result.status is IngestStatus.COMMITTED, result.issues
    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        people = [
            e
            for e in uow.entities.all_for_user(user.user_id)
            if e.canonical_name == "Angelo"
        ]
        assert people
        if binding is not None:
            rels = [
                r
                for r in uow.relations.for_entity(user.user_id, binding.entity_id)
                if r.is_current and "accountant" in r.key
            ]
            assert rels == []
        professions = [
            a.text_value
            for a in uow.attributes.for_entity(user.user_id, people[0].id)
            if a.is_current and a.dimension_key == "profession"
        ]
        assert professions == ["accountant"]
        uow.commit()


def test_luthier_discourse_reuses_entity(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "gsc-luthier")
    session = _session(user.user_id)
    role = _id_possessed("luthier", class_hint="luthier")
    named = _id_named("Renato")
    seed = SemanticProposal(
        raw_input="seed luthier",
        utterance_kind="assert",
        primitive_hint="relation",
        subject=role,
        object=named,
        relation_expression="named",
        link_semantics=True,
        classification_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=role),
            SemanticClaim(
                kind=SemanticClaimKind.CLASSIFICATION, subject=role, class_hint="luthier"
            ),
            SemanticClaim(
                kind=SemanticClaimKind.RELATION,
                predicate="named",
                subject=role,
                object=named,
            ),
        ],
        confidence=1.0,
    )
    _register_write(interpreter, seed)
    interpreter.on("qual o nome dele?", _continue_attr("name"))
    interpreter.on("ele trabalha em Fortaleza", _continue_write("work_location", "Fortaleza"))
    written = ingest.ingest("seed luthier", user, session)
    assert written.status is IngestStatus.COMMITTED, written.issues
    focus = _focus_ids(session)
    assert len(focus) == 1
    asked = ask.ask("qual o nome dele?", user, session)
    assert asked.status is AskStatus.ANSWERED, (asked.status, asked.issues)
    assert _attr_texts(asked) == ["Renato"]
    located = ingest.ingest("ele trabalha em Fortaleza", user, session)
    assert located.status is IngestStatus.COMMITTED, located.issues
    interpreter.on("onde trabalha?", _continue_attr("work_location"))
    loc = ask.ask("onde trabalha?", user, session)
    assert loc.status is AskStatus.ANSWERED, (loc.status, loc.issues)
    assert _attr_texts(loc) == ["Fortaleza"]
    assert _focus_ids(session) == focus


def test_pt_en_es_same_graph_structure() -> None:
    payloads = (
        "eu tenho uma casa chamada Casa da Praia",
        "I have a house called Casa da Praia",
        "tengo una casa llamada Casa da Praia",
    )
    keys = []
    for raw in payloads:
        proposal = _owned_named(raw, "Casa da Praia", "house")
        outcome = proposal_to_canonical_ir(proposal)
        assert outcome.ir is not None
        assert outcome.ir.relation is not None
        keys.append(
            (
                outcome.ir.relation.type.key,
                outcome.ir.relation.object.text if outcome.ir.relation.object else None,
            )
        )
    assert len(set(keys)) == 1
    assert keys[0][0] == "relation.owns"


def test_adversarial_theremin_is_owned_instance(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "gsc-theremin")
    session = _session(user.user_id)
    seed = "seed theremin"
    _register_write(interpreter, _owned_named(seed, "Ether", "theremin"))
    interpreter.on("fabricado", _continue_write("manufactured_year", "2024"))
    first = ingest.ingest(seed, user, session)
    assert first.status is IngestStatus.COMMITTED, first.issues
    second = ingest.ingest("fabricado", user, session)
    assert second.status is IngestStatus.COMMITTED, second.issues
    ether_id = _focus_ids(session)[0]
    interpreter.register(
        "OPAQUE-OWNER",
        QueryIR(
            raw_input="OPAQUE-OWNER",
            query=QuerySpec(
                intent="relation",
                entities=[
                    EntityMention(
                        text="Ether",
                        known_entity_id=ether_id,
                        reference_kind=MentionReferenceKind.NAMED,
                    )
                ],
                entity_association="relation_subject",
                relation_types=[ConceptRef(key="relation.owned_by")],
            ),
        ),
    )
    owner = ask.ask("OPAQUE-OWNER", user, session)
    assert owner.status is AskStatus.ANSWERED, (owner.status, owner.issues)
    assert owner.query_result is not None
    rels = owner.query_result.current_relations
    assert rels
    assert rels[0].relation_key == "relation.owns"
    assert rels[0].object_entity_id == ether_id
    assert rels[0].subject_entity_id != ether_id


def test_inverse_employment_query(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "gsc-employs")
    session = _session(user.user_id)
    carlos = _named("Carlos", class_hint="person", kind="person")
    acme = _named("Acme", class_hint="organization")
    seed = SemanticProposal(
        raw_input="seed acme",
        utterance_kind="assert",
        primitive_hint="relation",
        subject=carlos,
        object=acme,
        relation_expression="employed_by",
        link_semantics=True,
        classification_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=carlos),
            SemanticClaim(
                kind=SemanticClaimKind.CLASSIFICATION, subject=carlos, class_hint="person"
            ),
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=acme),
            SemanticClaim(
                kind=SemanticClaimKind.CLASSIFICATION,
                subject=acme,
                class_hint="organization",
            ),
            SemanticClaim(
                kind=SemanticClaimKind.RELATION,
                predicate="employed_by",
                subject=carlos,
                object=acme,
            ),
        ],
        confidence=1.0,
    )
    _register_write(interpreter, seed)
    written = ingest.ingest("seed acme", user, session)
    assert written.status is IngestStatus.COMMITTED, written.issues
    interpreter.register(
        "OPAQUE-EMPLOYS",
        QueryIR(
            raw_input="OPAQUE-EMPLOYS",
            query=QuerySpec(
                intent="relation",
                entities=[
                    EntityMention(
                        text="Acme",
                        type_hint=ConceptRef(key="entity.organization"),
                        reference_kind=MentionReferenceKind.NAMED,
                    )
                ],
                entity_association="relation_subject",
                relation_types=[ConceptRef(key="relation.employs")],
            ),
        ),
    )
    asked = ask.ask("OPAQUE-EMPLOYS", user, session)
    assert asked.status is AskStatus.ANSWERED, (asked.status, asked.issues)
    assert asked.query_result is not None
    rels = asked.query_result.current_relations
    assert rels
    assert rels[0].relation_key == "relation.employed_by"


def test_undirected_learned_relation_both_ends(tmp_path: Path) -> None:
    register_learned_relation_metadata(
        "relation.learned.connected_to",
        RelationConceptMetadata(
            meaning="undirected connection fixture",
            direction="a -- b",
            directionality=RelationDirectionality.UNDIRECTED,
        ),
    )
    db = fresh_db_path(tmp_path, "undirected")
    user = _id_user("u-undirected")
    a = _id_named("NodeA")
    b = _id_named("NodeB")
    proposal = SemanticProposal(
        raw_input=OPAQUE_REL,
        utterance_kind="assert",
        primitive_hint="relation",
        subject=a,
        object=b,
        relation_expression="connected_to",
        link_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=a),
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=b),
            SemanticClaim(
                kind=SemanticClaimKind.RELATION,
                predicate="connected_to",
                subject=a,
                object=b,
            ),
        ],
        confidence=1.0,
    )
    result, _ = _identity_ingest(proposal, db, user, opaque=True)
    assert result.status is IngestStatus.COMMITTED, result.issues
    with open_sqlite_uow(db) as uow:
        a_id = next(
            e.id for e in uow.entities.all_for_user(user.user_id) if e.canonical_name == "NodeA"
        )
        b_id = next(
            e.id for e in uow.entities.all_for_user(user.user_id) if e.canonical_name == "NodeB"
        )
        rels = [r for r in uow.relations.for_entity(user.user_id, a_id) if r.is_current]
        assert len(rels) == 1
        assert rels[0].key == "relation.learned.connected_to"
        pool = list(rels)
        concept = rels[0].concept_id
        uow.commit()
    from pke.query.relation_resolver import RelationScope, resolve_relation_query

    yes = resolve_relation_query(
        pool,
        subject_id=b_id,
        object_id=a_id,
        concept_ids={concept},
        scope=RelationScope.CURRENT,
        boolean_check=True,
    )
    assert yes.answer == "yes"


def test_two_houses_possessive_is_ambiguous(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "gsc-card")
    session = _session(user.user_id)
    _register_write(interpreter, _owned_named("house1", "Casa da Praia", "house"))
    _register_write(interpreter, _owned_named("house2", "Casa da Serra", "house"))
    ingest.ingest("house1", user, session)
    ingest.ingest("house2", user, session)
    interpreter.on("minha casa", _possessive_name_query)
    asked = ask.ask("minha casa", user, session)
    assert asked.status is AskStatus.NEEDS_CLARIFICATION
    assert asked.clarification is not None
    assert asked.clarification.clarification_key == "clarify.entity.which_one"
    assert len(asked.clarification.candidate_entity_ids) == 2


def _possessive_name_query(ctx) -> QueryIR:
    del ctx
    proposal = SemanticProposal(
        raw_input="",
        utterance_kind="query",
        primitive_hint="attribute",
        subject=_possessed("casa", class_hint="house"),
        attribute_expression="name",
        stable_property_semantics=True,
        discourse_decision="new_topic",
        temporal=SemanticTime(),
        confidence=1.0,
    )
    return _ir_from_proposal(proposal)


def test_opaque_primitives_execute(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "opaque-prim")
    user = _id_user("u-opaque-prim")
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)

    house = _owned_named(OPAQUE_ENTITY, "Casa da Praia", "house")
    r1, _ = _identity_ingest(house, db, user, opaque=True)
    assert r1.status is IngestStatus.COMMITTED, r1.issues

    luna = _owned_named(OPAQUE_CLASS, "Luna", "cat")
    r2, out2 = _identity_ingest(luna, db, _id_user("u-opaque-class"), opaque=True)
    assert r2.status is IngestStatus.COMMITTED, r2.issues
    assert out2.ir is not None
    types = [
        e.type_hint.key
        for e in (out2.ir.entities_mentioned or [])
        if e.type_hint is not None
    ]
    assert any("cat" in key for key in types)

    atlas = _owned_named("seed atlas", "Atlas", "computer")
    user_p = _id_user("u-opaque-prop")
    dbp = fresh_db_path(tmp_path, "opaque-prop")
    r3, _ = _identity_ingest(atlas, dbp, user_p)
    assert r3.status is IngestStatus.COMMITTED
    model = SemanticProposal(
        raw_input=OPAQUE_PROP,
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=_named("Atlas", class_hint="computer"),
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=_named("Atlas", class_hint="computer"),
                dimension="model",
                value_text="ThinkPad T14",
            )
        ],
        confidence=1.0,
    )
    r4, _ = _identity_ingest(model, dbp, user_p, opaque=True)
    assert r4.status is IngestStatus.COMMITTED, r4.issues
    with open_sqlite_uow(dbp) as uow:
        atlas_e = next(
            e for e in uow.entities.all_for_user(user_p.user_id) if e.canonical_name == "Atlas"
        )
        models = [
            a.text_value
            for a in uow.attributes.for_entity(user_p.user_id, atlas_e.id)
            if a.is_current and a.dimension_key == "model"
        ]
        names = {e.canonical_name for e in uow.entities.all_for_user(user_p.user_id)}
        assert models == ["ThinkPad T14"]
        assert "ThinkPad T14" not in names
        uow.commit()

    svc = IngestService(
        FakeInterpreter(
            {
                OPAQUE_EVENT: IngestIR(
                    intent=IngestIntent.RECORD_EVENT,
                    raw_input=OPAQUE_EVENT,
                    event=IrEvent(
                        type=ConceptRef(key="event.intent"),
                        status=EventStatus.COMPLETED,
                        time=IrTime(
                            original_text="",
                            occurrence_status=OccurrenceStatus.HAPPENED,
                        ),
                    ),
                )
            }
        ),
        ontology,
        lambda: open_sqlite_uow(fresh_db_path(tmp_path, "opaque-event")),
        FixedClock(NOW),
    )
    ev = svc.ingest(OPAQUE_EVENT, _id_user("u-ev"), _session("u-ev"))
    assert ev.status is IngestStatus.COMMITTED, ev.issues

    car = _possessed("carro", class_hint="automobile", kind="vehicle")
    meas = SemanticProposal(
        raw_input=OPAQUE_MEAS,
        utterance_kind="assert",
        primitive_hint="measurement",
        subject=car,
        measurement_semantics=True,
        measurable_dimension_key="odometer",
        measurement_numeric_value="50000",
        measurement_unit="km",
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=car),
            SemanticClaim(
                kind=SemanticClaimKind.CLASSIFICATION, subject=car, class_hint="automobile"
            ),
            SemanticClaim(
                kind=SemanticClaimKind.RELATION,
                predicate="owns",
                subject=_actor(),
                object=car,
            ),
            SemanticClaim(
                kind=SemanticClaimKind.MEASUREMENT,
                subject=car,
                dimension="odometer",
                numeric_value="50000",
                unit="km",
            ),
        ],
        confidence=1.0,
    )
    r5, _ = _identity_ingest(meas, fresh_db_path(tmp_path, "opaque-meas"), _id_user("u-meas"), opaque=True)
    assert r5.status is IngestStatus.COMMITTED, r5.issues


def test_graph_core_has_no_adversarial_domain_branches() -> None:
    forbidden = ("theremin", "luthier", "synthesizer", "casa da praia")
    skip_names = {"prompts_v4.py", "prompts_v5.py"}
    hits: list[str] = []
    for path in SRC.rglob("*.py"):
        if path.name in skip_names:
            continue
        text = path.read_text(encoding="utf-8").casefold()
        for word in forbidden:
            if word in text:
                hits.append(f"{path.relative_to(SRC)}:{word}")
    assert hits == []


def test_value_is_not_entity_thinkpad(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "value-not-entity")
    user = _id_user("u-value")
    atlas = _owned_named("seed", "Atlas", "computer")
    r1, _ = _identity_ingest(atlas, db, user)
    assert r1.status is IngestStatus.COMMITTED
    model = SemanticProposal(
        raw_input="OPAQUE-MODEL",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=_named("Atlas", class_hint="computer"),
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=_named("Atlas", class_hint="computer"),
                dimension="model",
                value_text="ThinkPad T14",
            )
        ],
        confidence=1.0,
    )
    r2, _ = _identity_ingest(model, db, user, opaque=True)
    assert r2.status is IngestStatus.COMMITTED, r2.issues
    with open_sqlite_uow(db) as uow:
        names = {e.canonical_name for e in uow.entities.all_for_user(user.user_id)}
        assert "ThinkPad T14" not in names
        uow.commit()
