"""Named + non-binding class hint through query/measurement — no linguistic rules."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW
from tests.measurement_query import helpers as hq

from pke.application.ask import AskService
from pke.application.ask_results import AskStatus
from pke.application.clock import FixedClock
from pke.application.query_builder import QueryBuildError, ResolvedQueryBuilder
from pke.application.session import SessionContext
from pke.domain.entities import Entity
from pke.domain.ontology import ConceptRef
from pke.domain.value_objects import UserContext
from pke.interpretation import EntityMention, FakeInterpreter, MentionReferenceKind, QueryIR, QuerySpec
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.ontology.learned import ensure_learned_entity_type, learned_concept_id
from pke.persist import open_sqlite_read_store
from pke.resolution import InMemoryEntityLookup, PersonalContext

OPAQUE = "OPAQUE-NAMED-001"


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = "u-named") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-named") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _luna(user_id: str = "u-named") -> Entity:
    return Entity(
        id="ent-luna",
        user_id=user_id,
        type_id=learned_concept_id("entity.learned.cat"),
        canonical_name="Luna",
        aliases=[],
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def test_query_builder_named_animal_hint_resolves_cat() -> None:
    ontology = OntologyRegistry.with_core_seeds()
    ensure_learned_entity_type(ontology, "entity.learned.cat")
    ensure_learned_entity_type(ontology, "entity.learned.animal")
    lookup = InMemoryEntityLookup()
    luna = _luna()
    lookup.add(luna)
    ir = QueryIR(
        raw_input=OPAQUE,
        query=QuerySpec(
            intent="measurement",
            entities=[
                EntityMention(
                    text="Luna",
                    type_hint=ConceptRef(key="entity.learned.animal"),
                    reference_kind=MentionReferenceKind.NAMED,
                )
            ],
            entity_association="subject",
            measurement_dimension_key="weight",
            measurement_query_mode="latest_observation",
            hierarchy="exact",
        ),
    )
    spec = ResolvedQueryBuilder(ontology).build(
        ir,
        _user(),
        _session(),
        lookup,
        now=NOW,
    )
    assert spec.entity_ids == [luna.id]
    assert spec.hierarchy.value == "exact"


def test_query_builder_opaque_raw_input_uses_slot_text() -> None:
    ontology = OntologyRegistry.with_core_seeds()
    ensure_learned_entity_type(ontology, "entity.learned.cat")
    ensure_learned_entity_type(ontology, "entity.learned.animal")
    lookup = InMemoryEntityLookup()
    luna = _luna()
    lookup.add(luna)
    ir = QueryIR(
        raw_input=OPAQUE,
        query=QuerySpec(
            intent="attribute",
            entities=[
                EntityMention(
                    text="Luna",
                    type_hint=ConceptRef(key="entity.learned.animal"),
                    reference_kind=MentionReferenceKind.NAMED,
                )
            ],
            entity_association="subject",
            attribute_dimension_key="name",
            attribute_query_mode="value_lookup",
        ),
    )
    spec = ResolvedQueryBuilder(ontology).build(ir, _user(), _session(), lookup, now=NOW)
    assert spec.entity_ids == [luna.id]


def test_query_builder_named_absence_does_not_create() -> None:
    ontology = OntologyRegistry.with_core_seeds()
    ensure_learned_entity_type(ontology, "entity.learned.animal")
    ir = QueryIR(
        raw_input=OPAQUE,
        query=QuerySpec(
            intent="measurement",
            entities=[
                EntityMention(
                    text="Apollo",
                    type_hint=ConceptRef(key="entity.learned.animal"),
                    reference_kind=MentionReferenceKind.NAMED,
                )
            ],
            entity_association="subject",
            measurement_dimension_key="weight",
            measurement_query_mode="latest_observation",
        ),
    )
    with pytest.raises(QueryBuildError) as exc:
        ResolvedQueryBuilder(ontology).build(
            ir, _user(), _session(), InMemoryEntityLookup(), now=NOW
        )
    assert exc.value.code == "entity.unresolved"


def test_measurement_named_luna_animal_hint_answers_weight(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "named-weight.db")
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    ensure_learned_entity_type(ontology, "entity.learned.cat")
    uid, eid = hq.seed_entity(
        db,
        name="Luna",
        type_id=learned_concept_id("entity.learned.cat"),
    )
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="weight",
        numeric_value=Decimal("4.5"),
        unit="kg",
        observed_at=NOW,
    )
    proposal = SemanticProposal(
        raw_input=OPAQUE,
        utterance_kind="query",
        primitive_hint="measurement",
        subject=SemanticEntityMention(
            text="Luna",
            kind_hint="thing",
            class_hint="animal",
            reference_kind="named",
            confidence=1.0,
        ),
        measurement_expression="peso",
        measurable_dimension_key="weight",
        measurement_semantics=True,
        confidence=1.0,
    )
    q_out = proposal_to_query_ir(proposal)
    assert q_out.query_ir is not None, (q_out.status, q_out.notes)
    mention = q_out.query_ir.query.entities[0]
    assert mention.reference_kind is MentionReferenceKind.NAMED
    assert mention.text == "Luna"
    assert mention.type_hint is not None
    assert mention.type_hint.key == "entity.learned.animal"
    opaque = q_out.query_ir.model_copy(update={"raw_input": OPAQUE})
    ask = AskService(
        FakeInterpreter({OPAQUE: opaque}),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    answered = ask.ask(
        OPAQUE,
        UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW),
        _session(uid),
    )
    assert answered.status is AskStatus.ANSWERED, (answered.status, answered.issues)
    assert answered.query_result is not None
    assert answered.query_result.measurement_values
    value = answered.query_result.measurement_values[0].numeric_value
    assert Decimal(str(value)) == Decimal("4.5")
    assert "entity.unresolved" not in [i.code for i in answered.issues]


def test_class_query_does_not_resolve_named_luna() -> None:
    ontology = OntologyRegistry.with_core_seeds()
    ensure_learned_entity_type(ontology, "entity.learned.cat")
    lookup = InMemoryEntityLookup()
    luna = _luna()
    lookup.add(luna)
    ir = QueryIR(
        raw_input=OPAQUE,
        query=QuerySpec(
            intent="relation",
            entities=[
                EntityMention(
                    text="gata",
                    type_hint=ConceptRef(key="entity.learned.cat"),
                    reference_kind=MentionReferenceKind.CLASS,
                )
            ],
            entity_association="relation_object",
            relation_types=[ConceptRef(key="relation.owns")],
            relation_query_kind="current_boolean",
        ),
    )
    spec = ResolvedQueryBuilder(ontology).build(ir, _user(), _session(), lookup, now=NOW)
    assert spec.entity_ids == []
    assert spec.object_entity_type_ids == [learned_concept_id("entity.learned.cat")]
