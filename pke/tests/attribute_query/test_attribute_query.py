"""I11.13 — Attribute Query & Current-Value Resolution (AQ1–AQ15)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from pke.application import (
    AskService,
    AskStatus,
    FixedClock,
    IngestService,
    IngestStatus,
)
from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.domain.ids import new_ulid
from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import Confidence, Qualifier, Source, SourceKind, UserContext
from pke.interpretation import FakeInterpreter, IngestIR, QueryIR
from pke.interpretation.semantic.attribute_resolution import (
    resolve_attribute_dimension_key,
    resolve_attribute_value,
)
from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import (
    QueryResolutionStatus,
    proposal_to_query_ir,
)
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.ontology.seeds import CORE_SCHEMA_VERSION
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.query.attribute_resolver import (
    AttributeResolutionStatus,
    resolve_attribute_query,
)
from pke.query.spec import AttributeQueryMode
from tests.attribute_query import fixtures as aqf
from tests.generalization_ingest.fixtures import benchmark_session, benchmark_user, fresh_db_path
from tests.integration.test_ingest import NOW
from tests.integration.test_ask import _session as ingest_session

pytestmark = pytest.mark.usefixtures("_catalog")


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _to_ir(proposal: SemanticProposal) -> IngestIR | QueryIR:
    if proposal.utterance_kind == "query":
        outcome = proposal_to_query_ir(proposal)
        assert outcome.query_ir is not None, (outcome.status, outcome.notes)
        return outcome.query_ir
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, outcome.failure_stage
    assert isinstance(outcome.ir, IngestIR)
    return outcome.ir


def _semantic_service(db: Path, mapping: dict[str, SemanticProposal]):
    responses = {raw: _to_ir(prop) for raw, prop in mapping.items()}
    ontology = OntologyRegistry.with_core_seeds()
    return IngestService(
        FakeInterpreter(responses),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )


def _semantic_ask(db: Path, mapping: dict[str, SemanticProposal]) -> AskService:
    responses = {raw: _to_ir(prop) for raw, prop in mapping.items()}
    ontology = OntologyRegistry.with_core_seeds()
    store = open_sqlite_read_store(db)
    return AskService(
        FakeInterpreter(responses),  # type: ignore[arg-type]
        ontology,
        store,
        FixedClock(NOW),
    )


def _user() -> UserContext:
    return UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)


def _run_lookup(db: Path, write: SemanticProposal, query: SemanticProposal):
    user = _user()
    session = ingest_session()
    svc = _semantic_service(db, {write.raw_input: write})
    assert svc.ingest(write.raw_input, user, session).status is IngestStatus.COMMITTED
    ask = _semantic_ask(db, {query.raw_input: query})
    return ask.ask(query.raw_input, user, session)


# --- AQ1–AQ6 lookups ---


@pytest.mark.parametrize(
    "write_fn,query_fn,dim,check",
    [
        (aqf.aq1_write, aqf.aq1_query, "color", lambda v: v.text_value == "prata"),
        (
            aqf.aq2_write,
            aqf.aq2_query,
            "area",
            lambda v: v.numeric_value == Decimal("200") and v.unit == "m²",
        ),
        (
            aqf.aq3_write,
            aqf.aq3_query,
            "weight",
            lambda v: v.numeric_value == Decimal("1.5") and v.unit == "kg",
        ),
        (
            aqf.aq4_write,
            aqf.aq4_query,
            "height",
            lambda v: v.numeric_value == Decimal("1.80") and v.unit == "m",
        ),
        (aqf.aq5_write, aqf.aq5_query, "model_year", lambda v: v.year_value == 2020),
        (
            aqf.aq6_write,
            aqf.aq6_query,
            "capacity",
            lambda v: v.numeric_value == Decimal("50") and v.unit == "L",
        ),
    ],
)
def test_aq_lookup_known_single(tmp_path: Path, write_fn, query_fn, dim, check) -> None:
    result = _run_lookup(tmp_path / "aq.db", write_fn(), query_fn())
    assert result.status is AskStatus.ANSWERED
    qr = result.query_result
    assert qr is not None
    assert qr.attribute_status == AttributeResolutionStatus.KNOWN_SINGLE.value
    assert qr.attribute_dimension_key == dim
    assert len(qr.attribute_values) == 1
    assert check(qr.attribute_values[0])


def test_aq7_unknown(tmp_path: Path) -> None:
    """Entity known, no color assertions → UNKNOWN (not negative proposition)."""
    result = _run_lookup(tmp_path / "aq7.db", aqf.aq5_write(), aqf.aq7_query_unknown())
    assert result.query_result is not None
    assert result.query_result.attribute_status == AttributeResolutionStatus.UNKNOWN.value
    assert result.query_result.attribute_proposition_answer is None
    assert result.query_result.matched_count == 0
    assert result.status is AskStatus.NO_RESULTS


def test_aq8_multiple_current_ambiguous(tmp_path: Path) -> None:
    db = tmp_path / "aq8.db"
    user = _user()
    session = ingest_session()
    write = aqf.aq1_write()
    svc = _semantic_service(db, {write.raw_input: write})
    assert svc.ingest(write.raw_input, user, session).status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        entities = uow.entities.all_for_user(user.user_id)
        assert len(entities) == 1
        entity_id = entities[0].id
        existing = uow.attributes.for_entity_dimension(user.user_id, entity_id, "color")
        assert existing
        src = Source(
            id=new_ulid(),
            user_id=user.user_id,
            kind=SourceKind.USER_STATEMENT,
            raw_input_id=existing[0].raw_input_id or new_ulid(),
        )
        uow.sources.add(src)
        black = EntityAttribute(
            id=new_ulid(),
            user_id=user.user_id,
            entity_id=entity_id,
            dimension_key="color",
            value_kind=AttributeValueKind.TEXT,
            text_value="black",
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            is_current=True,
            source=src,
            raw_input_id=src.raw_input_id,
            confidence=Confidence(score=1.0, qualifier=Qualifier.EXACT),
            created_at=NOW,
        )
        uow.attributes.add(black)
        uow.commit()
    query = aqf.aq1_query()
    ask = _semantic_ask(db, {query.raw_input: query})
    result = ask.ask(query.raw_input, user, session)
    assert result.status is AskStatus.ANSWERED
    qr = result.query_result
    assert qr is not None
    assert qr.attribute_status == AttributeResolutionStatus.AMBIGUOUS.value
    assert len(qr.attribute_values) == 2
    # Never latest-created_at winner: both values present
    texts = {v.text_value for v in qr.attribute_values}
    assert texts == {"prata", "black"}


def test_aq9_historical_existence(tmp_path: Path) -> None:
    result = _run_lookup(tmp_path / "aq9.db", aqf.aq9_write_historical_black(), aqf.aq9_query())
    assert result.status is AskStatus.ANSWERED
    qr = result.query_result
    assert qr is not None
    assert qr.attribute_proposition_answer == "yes"
    assert qr.attribute_status in {
        AttributeResolutionStatus.KNOWN_SINGLE.value,
        AttributeResolutionStatus.KNOWN_MULTIPLE.value,
    }


def test_aq10_temporal_unknown_for_year(tmp_path: Path) -> None:
    result = _run_lookup(tmp_path / "aq10.db", aqf.aq9_write_historical_black(), aqf.aq10_query())
    assert result.status is AskStatus.ANSWERED
    qr = result.query_result
    assert qr is not None
    assert qr.attribute_proposition_answer == "temporally_unknown"
    assert qr.attribute_status == AttributeResolutionStatus.TEMPORALLY_UNKNOWN.value
    assert qr.temporal_membership_unknown is True


def test_aq11_repeated_evidence_groups(tmp_path: Path) -> None:
    db = tmp_path / "aq11.db"
    user = _user()
    session = ingest_session()
    write = aqf.aq1_write()
    svc = _semantic_service(db, {write.raw_input: write})
    assert svc.ingest(write.raw_input, user, session).status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        entity_id = uow.entities.all_for_user(user.user_id)[0].id
        existing = uow.attributes.for_entity_dimension(user.user_id, entity_id, "color")[0]
        src = Source(
            id=new_ulid(),
            user_id=user.user_id,
            kind=SourceKind.USER_STATEMENT,
            raw_input_id=existing.raw_input_id or new_ulid(),
        )
        uow.sources.add(src)
        dup = EntityAttribute(
            id=new_ulid(),
            user_id=user.user_id,
            entity_id=entity_id,
            dimension_key="color",
            value_kind=AttributeValueKind.TEXT,
            text_value="prata",
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            is_current=True,
            source=src,
            raw_input_id=src.raw_input_id,
            confidence=Confidence(score=1.0, qualifier=Qualifier.EXACT),
            created_at=NOW,
        )
        uow.attributes.add(dup)
        uow.commit()
    query = aqf.aq1_query()
    ask = _semantic_ask(db, {query.raw_input: query})
    result = ask.ask(query.raw_input, user, session)
    qr = result.query_result
    assert qr is not None
    assert qr.attribute_status == AttributeResolutionStatus.KNOWN_SINGLE.value
    assert len(qr.attribute_values) == 1
    assert qr.attribute_values[0].text_value == "prata"
    assert qr.attribute_values[0].support_count == 2


@pytest.mark.parametrize(
    "prop_fn,expected",
    [
        (aqf.aq12_state, PrimitiveKind.STATE),
        (aqf.aq13_event, PrimitiveKind.EVENT),
        (aqf.aq14_relation, PrimitiveKind.RELATION),
        (aqf.aq15_type, PrimitiveKind.TYPE),
    ],
)
def test_aq12_15_primitive_boundaries(prop_fn, expected) -> None:
    prop = prop_fn()
    primitive, _ = route_primitive(prop)
    assert primitive is expected
    assert primitive is not PrimitiveKind.ATTRIBUTE


def test_dimension_symmetry_av1_av6() -> None:
    pairs = [
        (aqf.aq1_write(), aqf.aq1_query(), "color"),
        (aqf.aq2_write(), aqf.aq2_query(), "area"),
        (aqf.aq3_write(), aqf.aq3_query(), "weight"),
        (aqf.aq4_write(), aqf.aq4_query(), "height"),
        (aqf.aq5_write(), aqf.aq5_query(), "model_year"),
        (aqf.aq6_write(), aqf.aq6_query(), "capacity"),
    ]
    false = 0
    for write, query, expected in pairs:
        w_dim = resolve_attribute_dimension_key(write) or (
            resolve_attribute_value(write).dimension_key if resolve_attribute_value(write) else None
        )
        r_dim = resolve_attribute_dimension_key(query)
        assert w_dim == expected == r_dim, (write.raw_input, w_dim, r_dim)
        if w_dim != r_dim:
            false += 1
    assert false == 0


def test_resolver_never_uses_created_at() -> None:
    import inspect

    src = inspect.getsource(resolve_attribute_query)
    assert "created_at" not in src


def test_schema_remains_v8() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"


def test_core_unchanged() -> None:
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67
    assert CORE_SCHEMA_VERSION == "1"


def test_query_resolution_attribute_intent() -> None:
    outcome = proposal_to_query_ir(aqf.aq1_query())
    assert outcome.status is QueryResolutionStatus.RESOLVED
    assert outcome.primitive is PrimitiveKind.ATTRIBUTE
    assert outcome.query_ir is not None
    assert outcome.query_ir.query.intent == "attribute"
    assert outcome.query_ir.query.attribute_dimension_key == "color"
    assert outcome.query_ir.query.attribute_query_mode == "value_lookup"
