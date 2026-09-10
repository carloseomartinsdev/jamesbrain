"""Testes unitários — Relation lifecycle helpers (I11.5.1)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from pke.domain import Confidence, TemporalKnowledge, TimePrecision, TimeValue, new_ulid
from pke.domain.relation_lifecycle import (
    relation_calendar_endpoint,
    relation_calendar_start,
    termination_calendar_known,
)
from pke.domain.relations import Relation, RelationTerminationEvidence
from pke.domain.value_objects import Source, SourceKind
from pke.ontology import core_concept_id

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 2, 12, 0, tzinfo=FORTALEZA)


def _base_relation() -> Relation:
    return Relation(
        id=new_ulid(),
        user_id="u1",
        from_id="joao",
        to_id="acme",
        concept_id=core_concept_id("relation.employed_by"),
        key="relation.employed_by",
        temporal=TemporalKnowledge.partial_ongoing(),
        observed_at=NOW,
    )


def test_apply_termination_preserves_assertion_provenance() -> None:
    rel = _base_relation()
    assertion_raw = "raw-a"
    rel = rel.model_copy(
        update={
            "raw_input_id": assertion_raw,
            "source": Source(
                id=new_ulid(),
                user_id="u1",
                kind=SourceKind.USER_STATEMENT,
                raw_input_id=assertion_raw,
            ),
        }
    )
    term_at = dt.datetime(2026, 9, 3, 12, 0, tzinfo=FORTALEZA)
    evidence = RelationTerminationEvidence(
        temporal=TemporalKnowledge.partial_ongoing(tense_evidence="past"),
        observed_at=term_at,
        source=Source(
            id=new_ulid(),
            user_id="u1",
            kind=SourceKind.USER_STATEMENT,
            raw_input_id="raw-b",
        ),
        raw_input_id="raw-b",
        confidence=Confidence(score=1.0),
    )
    ended = rel.apply_termination(evidence)
    assert ended.raw_input_id == assertion_raw
    assert ended.termination_raw_input_id == "raw-b"
    assert ended.is_current is False
    assert ended.valid_to is None


def test_calendar_endpoint_from_exact_date() -> None:
    temporal = TemporalKnowledge.from_calendar(
        TimeValue(
            original_text="2026-08-15",
            date=dt.date(2026, 8, 15),
            precision=TimePrecision.DAY,
        )
    )
    endpoint = relation_calendar_endpoint(temporal)
    assert endpoint is not None
    assert endpoint.date() == dt.date(2026, 8, 15)
    assert termination_calendar_known(temporal)


def test_no_calendar_start_from_partial_assertion() -> None:
    assert relation_calendar_start(TemporalKnowledge.partial_ongoing()) is None
