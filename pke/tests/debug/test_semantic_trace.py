from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pke.application.results import ClaimTally, MaterializationResult
from pke.debug.semantic_trace import (
    compact_claim,
    format_entity_resolution,
    format_materialization,
    flush_entity_resolution_stage,
)
from pke.debug.trace_context import bind_trace, reset_trace
from pke.domain import ConceptRef, Entity
from pke.interpretation import EntityMention, MentionReferenceKind
from pke.interpretation.models import ClaimReport
from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticClaimKind,
    SemanticClaimOrigin,
    SemanticEntityMention,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.resolution import (
    EntityResolver,
    InMemoryEntityLookup,
    PersonalContext,
    ResolutionContext,
    ResolutionPurpose,
)
from pke.resolution.normalize import normalize_lexical


class _Repo:
    def __init__(self, items: list) -> None:
        self._items = {item.id: item for item in items}

    def get(self, user_id: str, item_id: str):
        return self._items.get(item_id)


class _Uow:
    def __init__(self, *, entities=(), relations=(), attributes=(), measurements=()) -> None:
        self.entities = _Repo(list(entities))
        self.relations = _Repo(list(relations))
        self.attributes = _Repo(list(attributes))
        self.measurements = _Repo(list(measurements))


def _entity(name: str, type_key: str, entity_id: str | None = None) -> Entity:
    return Entity(
        id=entity_id or f"ent:{normalize_lexical(name)}:{type_key}",
        user_id="u1",
        type_id=core_concept_id(type_key),
        canonical_name=name,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


def test_compact_claim_uses_trace_local_ids() -> None:
    claim = SemanticClaim(
        kind=SemanticClaimKind.CLASSIFICATION,
        subject=SemanticEntityMention(text="Luna", reference_kind="named"),
        class_hint="cat",
        origin=SemanticClaimOrigin.EXPLICIT,
        confidence=1.0,
    )
    row = compact_claim(claim, 1)
    assert row["claim_id"] == "c1"
    assert row["kind"] == "classification"
    assert row["class"] == "cat"
    assert row["origin"] == "explicit"


def test_entity_resolution_named_and_opaque_mention(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("PKE_REQUEST_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("PKE_REQUEST_LOG", "1")
    ontology = OntologyRegistry.with_core_seeds()
    lookup = InMemoryEntityLookup()
    luna = _entity("Luna", "entity.person")
    lookup.add(luna)
    resolver = EntityResolver(lookup, ontology)
    token = bind_trace(client_request_id="req-er-named")
    try:
        result = resolver.resolve(
            EntityMention(text="Luna", type_hint=ConceptRef(key="entity.person")),
            ResolutionContext(
                user_id="u1",
                personal=PersonalContext(user_id="u1"),
                purpose=ResolutionPurpose.QUERY,
            ),
        )
        flush_entity_resolution_stage()
    finally:
        reset_trace(token)
    text = next(tmp_path.glob("*_req-er-named.log")).read_text(encoding="utf-8")
    assert "stage=entity_resolution" in text
    assert '"strategy": "named_identity_primary"' in text
    assert '"outcome": "resolved"' in text
    assert luna.id in text
    assert "raw_input" not in text


def test_entity_resolution_ambiguous_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PKE_REQUEST_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("PKE_REQUEST_LOG", "1")
    ontology = OntologyRegistry.with_core_seeds()
    lookup = InMemoryEntityLookup()
    a = _entity("Luna", "entity.organization")
    b = Entity(
        id="ent:nala:entity.organization",
        user_id="u1",
        type_id=core_concept_id("entity.organization"),
        canonical_name="Nala",
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    lookup.add(a)
    lookup.add(b)
    resolver = EntityResolver(lookup, ontology)
    token = bind_trace(client_request_id="req-er-amb")
    try:
        result = resolver.resolve(
            EntityMention(
                text="empresa",
                type_hint=ConceptRef(key="entity.organization"),
                reference_kind=MentionReferenceKind.POSSESSIVE,
            ),
            ResolutionContext(
                user_id="u1",
                personal=PersonalContext(user_id="u1"),
                purpose=ResolutionPurpose.QUERY,
                principal_entity_id="01SELF",
                owned_entity_ids=[a.id, b.id],
            ),
        )
        body = format_entity_resolution(
            EntityMention(
                text="empresa",
                type_hint=ConceptRef(key="entity.organization"),
                reference_kind=MentionReferenceKind.POSSESSIVE,
            ),
            result,
            lookup,
            ontology,
            ResolutionContext(
                user_id="u1",
                personal=PersonalContext(user_id="u1"),
                purpose=ResolutionPurpose.QUERY,
                principal_entity_id="01SELF",
                owned_entity_ids=[a.id, b.id],
            ),
        )
        flush_entity_resolution_stage()
    finally:
        reset_trace(token)
    assert body["outcome"] == "ambiguous"
    assert body["candidate_count"] == 2
    assert body["strategy"] == "owned_entity_by_type"
    assert body["clarification_contract"] == "clarify.entity.which_one"
    names = {c["canonical_name"] for c in body["candidates"]}
    assert names == {"Luna", "Nala"}
    text = next(tmp_path.glob("*_req-er-amb.log")).read_text(encoding="utf-8")
    assert '"outcome": "ambiguous"' in text


def test_entity_resolution_no_match_distinct_from_unresolved() -> None:
    ontology = OntologyRegistry.with_core_seeds()
    lookup = InMemoryEntityLookup()
    org = _entity("Acme", "entity.organization")
    lookup.add(org)
    resolver = EntityResolver(lookup, ontology)
    mention = EntityMention(
        text="gato",
        type_hint=ConceptRef(key="entity.appliance"),
        reference_kind=MentionReferenceKind.POSSESSIVE,
    )
    context = ResolutionContext(
        user_id="u1",
        personal=PersonalContext(user_id="u1"),
        purpose=ResolutionPurpose.QUERY,
        owned_entity_ids=[org.id],
    )
    result = resolver.resolve(mention, context)
    body = format_entity_resolution(mention, result, lookup, ontology, context)
    assert body["outcome"] == "no_match"
    assert body["candidate_count"] == 0
    assert body["clarification_reason"] == "possessive_no_match"


def test_materialization_lists_objects_not_counts() -> None:
    ontology = OntologyRegistry.with_core_seeds()
    luna = _entity("Luna", "entity.person", "01LUNA")
    self_ent = _entity("__principal__", "entity.person", "01SELF")

    class Rel:
        def __init__(self) -> None:
            self.id = "01REL"
            self.from_id = "01SELF"
            self.to_id = "01LUNA"
            self.key = "relation.owns"

    result = MaterializationResult(
        created_entity_ids=["01LUNA"],
        reused_entity_ids=["01SELF"],
        relation_ids=["01REL"],
        claims=ClaimTally(received=2, valid=2, committed=2),
    )
    uow = _Uow(entities=[luna, self_ent], relations=[Rel()])
    ir = type("IR", (), {"claim_report": ClaimReport(received=2, derived_deferred=1)})()
    body = format_materialization(result, uow, "u1", ontology, ir)
    assert body["entities_created"][0]["canonical_name"] == "Luna"
    assert body["entities_reused"][0]["entity_id"] == "01SELF"
    assert body["relations_created"][0]["type"] == "relation.owns"
    assert body["relations_created"][0]["subject_id"] == "01SELF"
    assert any(item.get("reason") == "derived_not_materialized" for item in body["claim_results"])
    assert "entities_created" in body
    assert not isinstance(body["entities_created"], int)
