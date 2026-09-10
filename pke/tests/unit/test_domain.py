from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pke.domain import (
    AnchorKind,
    ConceptKind,
    ConceptRef,
    ConceptScope,
    ConceptStatus,
    Confidence,
    Entity,
    EpistemicStatus,
    Event,
    EventStatus,
    Fact,
    Money,
    OntologyConcept,
    Qualifier,
    Recurrence,
    Relation,
    Source,
    SourceKind,
    State,
    TimePrecision,
    TimeValue,
    UserContext,
    new_ulid,
)


def _now() -> datetime:
    return datetime(2026, 9, 1, 12, tzinfo=UTC)


def _concept(
    key: str,
    kind: ConceptKind,
    *,
    scope: ConceptScope = ConceptScope.CORE,
    parent_id: str | None = None,
    owner_user_id: str | None = None,
    status: ConceptStatus = ConceptStatus.ACTIVE,
) -> OntologyConcept:
    return OntologyConcept(
        id=new_ulid(),
        key=key,
        kind=kind,
        scope=scope,
        status=status,
        parent_id=parent_id,
        owner_user_id=owner_user_id,
        created_at=_now(),
    )


def test_ulid_shape_and_uniqueness() -> None:
    a, b = new_ulid(), new_ulid()
    assert len(a) == 26
    assert a != b
    assert all(c in "0123456789ABCDEFGHJKMNPQRSTVWXYZ" for c in a)


def test_user_context_defaults_are_configurable_not_domain_assumptions() -> None:
    local = UserContext(user_id="u1")
    other = UserContext(user_id="u2", locale="en-US", timezone="UTC")
    assert local.locale == "pt-BR"
    assert local.timezone == "America/Fortaleza"
    assert other.locale == "en-US"
    assert other.timezone == "UTC"


def test_time_value_keeps_original_text_after_absolute_resolution() -> None:
    resolved = TimeValue(
        original_text="quinta-feira",
        interpretation="próxima quinta",
        date=date(2026, 9, 3),
        time_of_day=datetime(2026, 9, 3, 15).time(),
        precision=TimePrecision.MINUTE,
        timezone="America/Fortaleza",
        confidence=Confidence(score=1.0),
        reference_at=_now(),
        reference_timezone="America/Fortaleza",
    )
    assert resolved.original_text == "quinta-feira"
    assert resolved.date == date(2026, 9, 3)
    assert resolved.reference_at is not None


def test_time_value_does_not_embed_default_timezone() -> None:
    t = TimeValue(precision=TimePrecision.DAY, original_text="hoje", date=date(2026, 9, 1))
    assert t.timezone is None
    assert t.reference_timezone is None


def test_ontology_personal_requires_owner_user_id() -> None:
    with pytest.raises(ValidationError):
        _concept("entity.my_garage", ConceptKind.ENTITY_TYPE, scope=ConceptScope.PERSONAL)


def test_ontology_core_forbids_owner_user_id() -> None:
    with pytest.raises(ValidationError):
        _concept(
            "entity.vehicle",
            ConceptKind.ENTITY_TYPE,
            owner_user_id="u1",
        )


def test_ontology_hierarchy_does_not_require_entity_remodel() -> None:
    vehicle = _concept("entity.vehicle", ConceptKind.ENTITY_TYPE)
    automobile = _concept(
        "entity.automobile",
        ConceptKind.ENTITY_TYPE,
        parent_id=vehicle.id,
    )
    corolla = Entity(
        id=new_ulid(),
        user_id="u1",
        type_id=automobile.id,
        canonical_name="Corolla",
        created_at=_now(),
    )
    assert automobile.parent_id == vehicle.id
    assert corolla.type_id == automobile.id


def test_extended_candidate_and_domain_kind_exist_structurally() -> None:
    domain = _concept("domain.vehicle", ConceptKind.DOMAIN)
    future = _concept(
        "entity.toll_tag",
        ConceptKind.ENTITY_TYPE,
        scope=ConceptScope.EXTENDED,
        status=ConceptStatus.CANDIDATE,
    )
    assert domain.kind is ConceptKind.DOMAIN
    assert future.as_ref().concept_id == future.id


def test_event_and_relation_reference_concept_ids() -> None:
    from pke.domain.temporal_knowledge import TemporalKnowledge

    type_id = new_ulid()
    action_id = new_ulid()
    rel_type_id = new_ulid()
    domain_id = new_ulid()
    event = Event(
        id=new_ulid(),
        user_id="u1",
        type_id=type_id,
        action_id=action_id,
        actor_id=new_ulid(),
        time=TimeValue(precision=TimePrecision.DAY, original_text="hoje"),
        status=EventStatus.COMPLETED,
        raw_input_id=new_ulid(),
        domain_ids=[domain_id],
    )
    rel = Relation(
        id=new_ulid(),
        user_id="u1",
        from_id=event.actor_id,
        to_id=new_ulid(),
        concept_id=rel_type_id,
        key="relation.owns",
        temporal=TemporalKnowledge.partial_ongoing(),
        observed_at=_now(),
        created_at=_now(),
    )
    assert event.domain_ids == [domain_id]
    assert rel.concept_id == rel_type_id


def test_fact_supersession_preserves_history() -> None:
    amount = _concept("attribute.amount", ConceptKind.ATTRIBUTE)
    old = Fact(
        id=new_ulid(),
        user_id="u1",
        about_kind=AnchorKind.EVENT,
        about_id=new_ulid(),
        concept_id=amount.id,
        key=amount.key,
        value=Money(amount=Decimal("180"), currency="BRL"),
        qualifier=Qualifier.APPROXIMATELY,
        epistemic_status=EpistemicStatus.UNCERTAIN,
        source=Source(user_id="u1", kind=SourceKind.USER_STATEMENT, raw_input_id=new_ulid()),
        confidence=Confidence(score=0.4, qualifier=Qualifier.APPROXIMATELY),
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    at = datetime(2026, 9, 1, 12, tzinfo=UTC)
    historic = old.mark_superseded(at)
    correction = Fact(
        id=new_ulid(),
        user_id="u1",
        about_kind=old.about_kind,
        about_id=old.about_id,
        concept_id=amount.id,
        key=amount.key,
        value=Money(amount=Decimal("186.50"), currency="BRL"),
        qualifier=Qualifier.EXACT,
        epistemic_status=EpistemicStatus.EXPLICIT,
        source=Source(user_id="u1", kind=SourceKind.CORRECTION, raw_input_id=new_ulid()),
        confidence=Confidence(score=1.0),
        supersedes_id=old.id,
        created_at=at,
    )
    assert old.is_current
    assert not historic.is_current
    assert historic.value == old.value
    assert correction.supersedes_id == old.id
    with pytest.raises(ValueError, match="já foi substituído"):
        historic.mark_superseded(at)


def test_fact_rejects_free_text_key() -> None:
    with pytest.raises(ValidationError):
        Fact(
            id=new_ulid(),
            user_id="u1",
            about_kind=AnchorKind.EVENT,
            about_id=new_ulid(),
            concept_id=new_ulid(),
            key="valor em reais",
            value=10,
            source=Source(user_id="u1", kind=SourceKind.USER_STATEMENT),
            confidence=Confidence(score=1.0),
            created_at=_now(),
        )


def test_state_is_temporally_bounded_and_dimension_backed() -> None:
    from pke.domain.temporal_knowledge import TemporalKnowledge

    dim = _concept("state.operational_condition", ConceptKind.STATE_DIMENSION)
    val = _concept("state.value.broken", ConceptKind.STATE_VALUE, parent_id=dim.id)
    observed = datetime(2026, 9, 2, tzinfo=UTC)
    state = State(
        id=new_ulid(),
        user_id="u1",
        entity_id=new_ulid(),
        dimension_id=dim.id,
        dimension_key=dim.key,
        value_concept_id=val.id,
        value_key=val.key,
        temporal=TemporalKnowledge.partial_ongoing(),
        observed_at=observed,
        valid_to=datetime(2026, 9, 10, tzinfo=UTC),
        is_current=False,
    )
    assert state.valid_to is not None
    assert state.dimension_id == dim.id
    assert state.is_current is False


def test_recurrence_is_not_locked_to_monthly() -> None:
    Recurrence(freq="monthly", by_monthday=10)
    weekly = Recurrence(freq="weekly", interval=2, by_weekday=3)
    assert weekly.by_monthday is None
    with pytest.raises(ValidationError):
        Recurrence(freq="monthly", by_monthday=32)


def test_concept_ref_is_identity_not_user_text() -> None:
    ref = ConceptRef(key="entity.vehicle")
    assert ref.concept_id is None
    with pytest.raises(ValidationError):
        ConceptRef(key="o carro")
