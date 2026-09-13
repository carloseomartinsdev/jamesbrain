"""Named identity is primary; class/type hint is secondary. No linguistic rules."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pke.domain import ConceptRef, Entity
from pke.interpretation import EntityMention, MentionReferenceKind
from pke.ontology import OntologyRegistry, core_concept_id
from pke.ontology.learned import ensure_learned_entity_type, learned_concept_id
from pke.resolution import (
    EntityResolver,
    EvidenceKind,
    InMemoryEntityLookup,
    PersonalContext,
    ResolutionContext,
    ResolutionPurpose,
    ResolutionStatus,
    normalize_lexical,
)


def _learned(ontology: OntologyRegistry, *keys: str) -> None:
    for key in keys:
        ensure_learned_entity_type(ontology, key)


def _entity(
    user_id: str,
    name: str,
    type_id: str,
    *,
    entity_id: str | None = None,
) -> Entity:
    return Entity(
        id=entity_id or f"ent:{user_id}:{normalize_lexical(name)}:{type_id}",
        user_id=user_id,
        type_id=type_id,
        canonical_name=name,
        aliases=[],
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


def _ctx(*, purpose: ResolutionPurpose = ResolutionPurpose.QUERY) -> ResolutionContext:
    return ResolutionContext(
        user_id="u1",
        personal=PersonalContext(user_id="u1"),
        purpose=purpose,
    )


def _named(text: str, type_key: str | None = None) -> EntityMention:
    return EntityMention(
        text=text,
        type_hint=ConceptRef(key=type_key) if type_key else None,
        reference_kind=MentionReferenceKind.NAMED,
    )


def test_named_luna_cat_resolves_with_animal_hint(
    resolver: EntityResolver,
    lookup: InMemoryEntityLookup,
    ontology: OntologyRegistry,
) -> None:
    _learned(ontology, "entity.learned.cat", "entity.learned.animal")
    luna = _entity("u1", "Luna", learned_concept_id("entity.learned.cat"))
    lookup.add(luna)
    result = resolver.resolve(_named("Luna", "entity.learned.animal"), _ctx())
    assert result.status is ResolutionStatus.RESOLVED
    assert result.entity_id == luna.id
    assert "named_match_with_nonbinding_type_hint" in result.notes
    assert "type_hint_mismatch" in result.notes
    assert EvidenceKind.EXACT_CANONICAL_NAME in result.evidence
    assert EvidenceKind.TYPE_MATCH not in result.evidence


def test_named_luna_without_hint(
    resolver: EntityResolver,
    lookup: InMemoryEntityLookup,
    ontology: OntologyRegistry,
) -> None:
    _learned(ontology, "entity.learned.cat")
    luna = _entity("u1", "Luna", learned_concept_id("entity.learned.cat"))
    lookup.add(luna)
    result = resolver.resolve(_named("Luna"), _ctx())
    assert result.status is ResolutionStatus.RESOLVED
    assert result.entity_id == luna.id
    assert result.notes == ["named_exact_match"]


def test_named_luna_exact_cat_hint(
    resolver: EntityResolver,
    lookup: InMemoryEntityLookup,
    ontology: OntologyRegistry,
) -> None:
    _learned(ontology, "entity.learned.cat")
    luna = _entity("u1", "Luna", learned_concept_id("entity.learned.cat"))
    lookup.add(luna)
    result = resolver.resolve(_named("Luna", "entity.learned.cat"), _ctx())
    assert result.status is ResolutionStatus.RESOLVED
    assert result.entity_id == luna.id
    assert EvidenceKind.TYPE_MATCH in result.evidence
    assert result.notes == ["named_exact_match"]


def test_named_orion_computer_with_thing_hint(
    resolver: EntityResolver,
    lookup: InMemoryEntityLookup,
    ontology: OntologyRegistry,
) -> None:
    _learned(ontology, "entity.learned.computer")
    orion = _entity("u1", "Orion", learned_concept_id("entity.learned.computer"))
    lookup.add(orion)
    result = resolver.resolve(_named("Orion", "entity.thing"), _ctx())
    assert result.status is ResolutionStatus.RESOLVED
    assert result.entity_id == orion.id
    assert "named_match_with_nonbinding_type_hint" in result.notes


def test_named_unique_conflicting_hint_still_resolves(
    resolver: EntityResolver,
    lookup: InMemoryEntityLookup,
    ontology: OntologyRegistry,
) -> None:
    _learned(ontology, "entity.learned.company", "entity.learned.animal")
    luna = _entity("u1", "Luna", learned_concept_id("entity.learned.company"))
    lookup.add(luna)
    result = resolver.resolve(_named("Luna", "entity.learned.animal"), _ctx())
    assert result.status is ResolutionStatus.RESOLVED
    assert result.entity_id == luna.id
    assert "type_hint_mismatch" in result.notes


def test_named_ambiguous_without_hint(
    resolver: EntityResolver,
    lookup: InMemoryEntityLookup,
    ontology: OntologyRegistry,
) -> None:
    _learned(ontology, "entity.learned.project", "entity.learned.company")
    a = _entity(
        "u1",
        "Atlas",
        learned_concept_id("entity.learned.project"),
        entity_id="ent:atlas:project",
    )
    b = _entity(
        "u1",
        "Atlas",
        learned_concept_id("entity.learned.company"),
        entity_id="ent:atlas:company",
    )
    lookup.add(a)
    lookup.add(b)
    result = resolver.resolve(_named("Atlas"), _ctx())
    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.requires_clarification
    assert result.notes == ["named_multiple_candidates"]
    assert {c.entity_id for c in result.candidates} == {a.id, b.id}


def test_named_disambiguated_by_type_hint(
    resolver: EntityResolver,
    lookup: InMemoryEntityLookup,
    ontology: OntologyRegistry,
) -> None:
    _learned(ontology, "entity.learned.project", "entity.learned.company")
    a = _entity(
        "u1",
        "Atlas",
        learned_concept_id("entity.learned.project"),
        entity_id="ent:atlas:project",
    )
    b = _entity(
        "u1",
        "Atlas",
        learned_concept_id("entity.learned.company"),
        entity_id="ent:atlas:company",
    )
    lookup.add(a)
    lookup.add(b)
    result = resolver.resolve(_named("Atlas", "entity.learned.company"), _ctx())
    assert result.status is ResolutionStatus.RESOLVED
    assert result.entity_id == b.id
    assert result.notes == ["named_disambiguated_by_type"]


def test_named_hint_cannot_distinguish_stays_ambiguous(
    resolver: EntityResolver,
    lookup: InMemoryEntityLookup,
    ontology: OntologyRegistry,
) -> None:
    _learned(ontology, "entity.learned.project", "entity.learned.company", "entity.learned.animal")
    a = _entity(
        "u1",
        "Atlas",
        learned_concept_id("entity.learned.project"),
        entity_id="ent:atlas:project",
    )
    b = _entity(
        "u1",
        "Atlas",
        learned_concept_id("entity.learned.company"),
        entity_id="ent:atlas:company",
    )
    lookup.add(a)
    lookup.add(b)
    result = resolver.resolve(_named("Atlas", "entity.learned.animal"), _ctx())
    assert result.status is ResolutionStatus.AMBIGUOUS
    assert result.requires_clarification
    assert {c.entity_id for c in result.candidates} == {a.id, b.id}


def test_named_absence_is_unresolved(
    resolver: EntityResolver, ontology: OntologyRegistry
) -> None:
    _learned(ontology, "entity.learned.animal")
    result = resolver.resolve(_named("Apollo", "entity.learned.animal"), _ctx())
    assert result.status is ResolutionStatus.UNRESOLVED
    assert result.entity_id is None
    assert result.clarification_reason == "query_entity_not_found"


def test_named_uses_slot_text_not_raw_input(
    resolver: EntityResolver,
    lookup: InMemoryEntityLookup,
    ontology: OntologyRegistry,
) -> None:
    _learned(ontology, "entity.learned.cat", "entity.learned.animal")
    luna = _entity("u1", "Luna", learned_concept_id("entity.learned.cat"))
    lookup.add(luna)
    mention = EntityMention(
        text="Luna",
        type_hint=ConceptRef(key="entity.learned.animal"),
        reference_kind=MentionReferenceKind.NAMED,
    )
    result = resolver.resolve(mention, _ctx())
    assert result.status is ResolutionStatus.RESOLVED
    assert result.entity_id == luna.id
    assert result.original_text == "Luna"


def test_class_reference_stays_type_constraint(
    resolver: EntityResolver,
    lookup: InMemoryEntityLookup,
    ontology: OntologyRegistry,
) -> None:
    _learned(ontology, "entity.learned.cat")
    luna = _entity("u1", "Luna", learned_concept_id("entity.learned.cat"))
    lookup.add(luna)
    result = resolver.resolve(
        EntityMention(
            text="Luna",
            type_hint=ConceptRef(key="entity.learned.cat"),
            reference_kind=MentionReferenceKind.CLASS,
        ),
        _ctx(),
    )
    assert result.status is ResolutionStatus.UNRESOLVED
    assert result.entity_id is None
    assert result.clarification_reason == "class_is_type_constraint"


def test_possessive_still_requires_owned_type(
    resolver: EntityResolver,
    lookup: InMemoryEntityLookup,
    ontology: OntologyRegistry,
) -> None:
    _learned(ontology, "entity.learned.cat")
    luna = _entity("u1", "Luna", learned_concept_id("entity.learned.cat"))
    org = _entity("u1", "Acme", core_concept_id("entity.organization"))
    lookup.add(luna)
    lookup.add(org)
    result = resolver.resolve(
        EntityMention(
            text="gato",
            type_hint=ConceptRef(key="entity.learned.cat"),
            reference_kind=MentionReferenceKind.POSSESSIVE,
        ),
        ResolutionContext(
            user_id="u1",
            personal=PersonalContext(user_id="u1"),
            purpose=ResolutionPurpose.QUERY,
            owned_entity_ids=[org.id],
        ),
    )
    assert result.status is ResolutionStatus.UNRESOLVED
    assert result.clarification_reason == "possessive_no_match"
    result_ok = resolver.resolve(
        EntityMention(
            text="gato",
            type_hint=ConceptRef(key="entity.learned.cat"),
            reference_kind=MentionReferenceKind.POSSESSIVE,
        ),
        ResolutionContext(
            user_id="u1",
            personal=PersonalContext(user_id="u1"),
            purpose=ResolutionPurpose.QUERY,
            owned_entity_ids=[luna.id],
        ),
    )
    assert result_ok.status is ResolutionStatus.RESOLVED
    assert result_ok.entity_id == luna.id
