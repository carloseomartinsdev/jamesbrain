from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pke.domain import ConceptRef, Entity
from pke.interpretation import EntityMention, MentionReferenceKind
from pke.ontology import ConceptKindError, ConceptNotFoundError, OntologyRegistry, core_concept_id
from pke.resolution import (
    EntityResolver,
    EvidenceKind,
    ForeignEntityError,
    InMemoryEntityLookup,
    PersonalContext,
    ResolutionContext,
    ResolutionPurpose,
    ResolutionStatus,
    normalize_lexical,
)


def _entity(
    user_id: str,
    name: str,
    type_key: str,
    *,
    aliases: list[str] | None = None,
) -> Entity:
    return Entity(
        id=f"ent:{user_id}:{normalize_lexical(name)}:{type_key}",
        user_id=user_id,
        type_id=core_concept_id(type_key),
        canonical_name=name,
        aliases=aliases or [],
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def lookup() -> InMemoryEntityLookup:
    return InMemoryEntityLookup()


@pytest.fixture
def resolver(lookup: InMemoryEntityLookup, ontology: OntologyRegistry) -> EntityResolver:
    return EntityResolver(lookup, ontology)


def _ctx(
    user_id: str = "u1",
    personal: PersonalContext | None = None,
    *,
    purpose: ResolutionPurpose = ResolutionPurpose.INGEST,
) -> ResolutionContext:
    return ResolutionContext(
        user_id=user_id,
        personal=personal or PersonalContext(user_id=user_id),
        purpose=purpose,
    )


def _named(
    text: str,
    type_key: str | None = None,
    *,
    known_id: str | None = None,
) -> EntityMention:
    return EntityMention(
        text=text,
        type_hint=ConceptRef(key=type_key) if type_key else None,
        known_entity_id=known_id,
    )


def test_canonical_name_exact(resolver: EntityResolver, lookup: InMemoryEntityLookup) -> None:
    car = _entity("u1", "Corolla", "entity.automobile")
    lookup.add(car)
    result = resolver.resolve(_named("Corolla", "entity.automobile"), _ctx())
    assert result.status is ResolutionStatus.RESOLVED
    assert result.entity_id == car.id
    assert EvidenceKind.EXACT_CANONICAL_NAME in result.evidence


def test_canonical_name_case_insensitive(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    car = _entity("u1", "Corolla", "entity.automobile")
    lookup.add(car)
    result = resolver.resolve(_named("COROLLA", "entity.automobile"), _ctx())
    assert result.entity_id == car.id
    assert result.original_text == "COROLLA"
    assert car.canonical_name == "Corolla"


def test_alias_exact(resolver: EntityResolver, lookup: InMemoryEntityLookup) -> None:
    car = _entity("u1", "Corolla", "entity.automobile", aliases=["meu corolla"])
    lookup.add(car)
    result = resolver.resolve(_named("meu corolla", "entity.automobile"), _ctx())
    assert result.status is ResolutionStatus.RESOLVED
    assert EvidenceKind.EXACT_ALIAS in result.evidence


def test_type_hint_filters_incompatible(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    person = _entity("u1", "João", "entity.person")
    shop = _entity("u1", "João", "entity.organization")
    lookup.add(person)
    lookup.add(shop)
    result = resolver.resolve(_named("João", "entity.person"), _ctx())
    assert result.status is ResolutionStatus.RESOLVED
    assert result.entity_id == person.id


def test_child_type_matches_parent_hint(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    car = _entity("u1", "Corolla", "entity.automobile")
    lookup.add(car)
    result = resolver.resolve(_named("Corolla", "entity.vehicle"), _ctx())
    assert result.entity_id == car.id
    assert EvidenceKind.TYPE_DESCENDANT_MATCH in result.evidence


def test_explicit_id(resolver: EntityResolver, lookup: InMemoryEntityLookup) -> None:
    car = _entity("u1", "Corolla", "entity.automobile")
    lookup.add(car)
    result = resolver.resolve(_named("x", "entity.automobile", known_id=car.id), _ctx())
    assert result.status is ResolutionStatus.RESOLVED
    assert EvidenceKind.EXPLICIT_ID in result.evidence


def test_explicit_id_other_user_rejected(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    other = _entity("u2", "Corolla", "entity.automobile")
    lookup.add(other)
    with pytest.raises(ForeignEntityError):
        resolver.resolve(_named("Corolla", known_id=other.id), _ctx("u1"))


def test_create_candidate_when_type_clear_and_no_match(resolver: EntityResolver) -> None:
    result = resolver.resolve(_named("Corolla", "entity.automobile"), _ctx())
    assert result.status is ResolutionStatus.CREATE_CANDIDATE
    assert result.create_canonical_name == "Corolla"
    assert result.create_type_id == core_concept_id("entity.automobile")
    assert result.entity_id is None


def test_query_purpose_does_not_create_candidate(resolver: EntityResolver) -> None:
    result = resolver.resolve(
        _named("Corolla", "entity.automobile"),
        _ctx(purpose=ResolutionPurpose.QUERY),
    )
    assert result.status is ResolutionStatus.UNRESOLVED
    assert result.entity_id is None
    assert result.create_canonical_name is None
    assert result.clarification_reason == "query_entity_not_found"


def test_two_equivalent_candidates_ambiguous(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    a = _entity("u1", "João", "entity.person")
    b = Entity(
        id="ent:u1:joao:coworker",
        user_id="u1",
        type_id=core_concept_id("entity.person"),
        canonical_name="João",
        aliases=["Joao da Silva"],
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    # two people both matching "João" via canonical (same normalized name)
    # use distinct ids but same canonical — lookup returns both
    lookup.add(a)
    lookup.add(b)
    result = resolver.resolve(_named("João", "entity.person"), _ctx())
    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.requires_clarification
    assert len(result.candidates) == 2


def test_recent_context_resolves_unique_contextual(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    car = _entity("u1", "Corolla", "entity.automobile")
    lookup.add(car)
    personal = PersonalContext(user_id="u1")
    personal.record_mention(car)
    aliases_before = list(car.aliases)
    mention = EntityMention(
        text="o carro",
        type_hint=ConceptRef(key="entity.vehicle"),
        reference_kind=MentionReferenceKind.CONTEXTUAL,
    )
    result = resolver.resolve(mention, _ctx(personal=personal))
    assert result.status is ResolutionStatus.RESOLVED
    assert result.entity_id == car.id
    assert EvidenceKind.CONTEXTUAL_REFERENCE in result.evidence
    assert result.suggested_alias is None
    assert car.aliases == aliases_before


def test_recent_context_does_not_force_named_ambiguity(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    joao_a = _entity("u1", "João", "entity.person")
    joao_b = Entity(
        id="ent:u1:joao-b:entity.person",
        user_id="u1",
        type_id=core_concept_id("entity.person"),
        canonical_name="João",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    lookup.add(joao_a)
    lookup.add(joao_b)
    personal = PersonalContext(user_id="u1")
    personal.record_mention(joao_a)
    result = resolver.resolve(_named("João", "entity.person"), _ctx(personal=personal))
    assert result.status is ResolutionStatus.AMBIGUOUS


def test_alias_user_a_hidden_from_b(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    car = _entity("u1", "Corolla", "entity.automobile", aliases=["relampago"])
    lookup.add(car)
    result = resolver.resolve(_named("relampago", "entity.automobile"), _ctx("u2"))
    assert result.status is ResolutionStatus.CREATE_CANDIDATE
    assert result.entity_id is None


def test_o_carro_does_not_become_permanent_alias(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    car = _entity("u1", "Corolla", "entity.automobile")
    lookup.add(car)
    personal = PersonalContext(user_id="u1")
    personal.record_mention(car)
    resolver.resolve(
        EntityMention(
            text="o carro",
            type_hint=ConceptRef(key="entity.vehicle"),
            reference_kind=MentionReferenceKind.CONTEXTUAL,
        ),
        _ctx(personal=personal),
    )
    assert "o carro" not in car.aliases
    assert normalize_lexical("o carro") not in personal.confirmed_aliases


def test_canonical_original_preserved_on_create(resolver: EntityResolver) -> None:
    result = resolver.resolve(_named("Corólla", "entity.automobile"), _ctx())
    assert result.create_canonical_name == "Corólla"
    assert result.original_text == "Corólla"


def test_evidence_recorded(resolver: EntityResolver, lookup: InMemoryEntityLookup) -> None:
    car = _entity("u1", "Corolla", "entity.automobile")
    lookup.add(car)
    result = resolver.resolve(_named("Corolla", "entity.automobile"), _ctx())
    assert EvidenceKind.UNIQUE_CANDIDATE in result.evidence
    assert EvidenceKind.TYPE_MATCH in result.evidence


def test_unknown_type_hint_rejected(resolver: EntityResolver) -> None:
    with pytest.raises(ConceptNotFoundError):
        resolver.resolve(_named("X", "entity.unicorn"), _ctx())


def test_non_entity_type_hint_rejected(resolver: EntityResolver) -> None:
    with pytest.raises(ConceptKindError):
        resolver.resolve(_named("X", "event.appointment"), _ctx())


def test_resolver_does_not_persist(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    before = len(lookup)
    resolver.resolve(_named("Corolla", "entity.automobile"), _ctx())
    assert len(lookup) == before == 0


def test_resolver_source_does_not_import_interpreter() -> None:
    source = Path(__file__).parents[2].joinpath("src/pke/resolution/entities.py").read_text(
        encoding="utf-8"
    )
    assert "from pke.interpretation.interpreter" not in source
    assert "FakeInterpreter" not in source


def test_resolver_does_not_mutate_ontology(
    resolver: EntityResolver, ontology: OntologyRegistry
) -> None:
    before = [c.id for c in ontology.concepts()]
    frozen = ontology.core_frozen
    resolver.resolve(_named("Corolla", "entity.automobile"), _ctx())
    assert [c.id for c in ontology.concepts()] == before
    assert ontology.core_frozen is frozen is True


def test_contextual_two_vehicles_remain_ambiguous(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    a = _entity("u1", "Corolla", "entity.automobile")
    b = Entity(
        id="ent:u1:civic:entity.automobile",
        user_id="u1",
        type_id=core_concept_id("entity.automobile"),
        canonical_name="Civic",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    lookup.add(a)
    lookup.add(b)
    personal = PersonalContext(user_id="u1")
    personal.record_mention(a)
    personal.record_mention(b)
    result = resolver.resolve(
        EntityMention(
            text="o carro",
            type_hint=ConceptRef(key="entity.vehicle"),
            reference_kind=MentionReferenceKind.CONTEXTUAL,
        ),
        _ctx(personal=personal),
    )
    assert result.status is ResolutionStatus.AMBIGUOUS


def test_possessive_owned_vehicle_skips_lexeme_whitelist(
    resolver: EntityResolver, lookup: InMemoryEntityLookup
) -> None:
    car = _entity("u1", "Corolla", "entity.automobile")
    lookup.add(car)
    result = resolver.resolve(
        EntityMention(
            text="meu carro",
            type_hint=ConceptRef(key="entity.vehicle"),
            reference_kind=MentionReferenceKind.POSSESSIVE,
        ),
        ResolutionContext(
            user_id="u1",
            personal=PersonalContext(user_id="u1"),
            purpose=ResolutionPurpose.QUERY,
            owned_vehicle_entity_ids=[car.id],
        ),
    )
    assert result.status is ResolutionStatus.RESOLVED
    assert result.entity_id == car.id
    assert EvidenceKind.OWNED_BY_PRINCIPAL in result.evidence


def test_normalize_is_predictable() -> None:
    assert normalize_lexical("  Corolla. ") == "corolla"
    assert normalize_lexical("José") == "jose"
    assert normalize_lexical("corolla") == normalize_lexical("COROLLA")
