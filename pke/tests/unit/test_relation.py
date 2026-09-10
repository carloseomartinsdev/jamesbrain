"""Testes unitários — Relation evolution (I11.5)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from pke.domain import (
    ConceptKind,
    Relation,
    TemporalKnowledge,
    TimePrecision,
    TimeValue,
    new_ulid,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.ontology.relation_metadata import canonical_endpoints
from pke.query.relation_resolver import RelationScope, filter_relations, resolve_relation_query

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 2, 12, 0, tzinfo=FORTALEZA)


def _relation(
    *,
    from_id: str,
    to_id: str,
    key: str = "relation.employed_by",
    is_current: bool = True,
    temporal: TemporalKnowledge | None = None,
) -> Relation:
    return Relation(
        id=new_ulid(),
        user_id="u1",
        from_id=from_id,
        to_id=to_id,
        concept_id=core_concept_id(key),
        key=key,
        temporal=temporal or TemporalKnowledge.partial_ongoing(),
        observed_at=NOW,
        is_current=is_current,
    )


def test_relation_concepts_are_relation_type_kind() -> None:
    registry = OntologyRegistry.with_core_seeds()
    employed = registry.get_by_key("relation.employed_by")
    assert employed is not None
    assert employed.kind is ConceptKind.RELATION_TYPE


def test_identity_key_distinguishes_objects() -> None:
    a = _relation(from_id="joao", to_id="acme")
    b = _relation(from_id="joao", to_id="beta")
    assert a.identity_key() != b.identity_key()


def test_no_auto_supersession_different_objects() -> None:
    acme = _relation(from_id="joao", to_id="acme")
    beta = _relation(from_id="joao", to_id="beta")
    current = filter_relations(
        [acme, beta],
        subject_id="joao",
        concept_ids={core_concept_id("relation.employed_by")},
        scope=RelationScope.CURRENT,
    )
    assert len(current) == 2


def test_termination_only_same_instance() -> None:
    acme = _relation(from_id="joao", to_id="acme", is_current=False)
    beta = _relation(from_id="joao", to_id="beta")
    current = filter_relations(
        [acme, beta],
        subject_id="joao",
        concept_ids={core_concept_id("relation.employed_by")},
        scope=RelationScope.CURRENT,
    )
    assert len(current) == 1
    assert current[0].to_id == "beta"


def test_symmetric_canonical_order() -> None:
    a, b = canonical_endpoints("zzz", "aaa", "relation.married_to")
    assert a == "aaa"
    assert b == "zzz"


def test_symmetric_query_without_duplicate_rows() -> None:
    rel = _relation(from_id="ana", to_id="joao", key="relation.married_to")
    answer = resolve_relation_query(
        [rel],
        subject_id="joao",
        object_id="ana",
        concept_ids={core_concept_id("relation.married_to")},
        scope=RelationScope.CURRENT,
        boolean_check=True,
    )
    assert answer.answer == "yes"


def test_historical_scope_excludes_current() -> None:
    old = _relation(from_id="joao", to_id="acme", is_current=False)
    pool = filter_relations(
        [old],
        subject_id="joao",
        concept_ids={core_concept_id("relation.employed_by")},
        scope=RelationScope.HISTORICAL,
    )
    assert len(pool) == 1


def test_partial_temporal_historical_not_current() -> None:
    past = _relation(
        from_id="joao",
        to_id="acme",
        is_current=False,
        temporal=TemporalKnowledge.partial_ongoing(original_text="2024"),
    )
    assert past.is_current is False
