"""Learned attribute dimensions — structured claims, not language tables."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.ask import AskService
from pke.application.ask_results import AskStatus
from pke.application.clock import FixedClock
from pke.application.ingest import IngestService
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.models import EntityMention, IngestIR, IngestIntent, IrAttribute
from pke.interpretation.semantic.attribute_registry import (
    alias_to_dimension_key,
    is_registered_dimension,
)
from pke.interpretation.semantic.learned_attribute import (
    bind_learned_attribute_dimensions,
    learned_attribute_key_from_predicate,
    resolve_dimension_identity,
)
from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticClaimKind,
    SemanticClaimOrigin,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.ontology.learned import hydrate_learned_attribute_dimensions, learned_concept_id
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.persist.sqlite.engine import create_sqlite_engine, sqlite_url
from pke.resolution.context import PersonalContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW

OPAQUE = "OPAQUE-LEARNED-ATTRIBUTE-001"
OPAQUE_QUERY = "OPAQUE-ATTRIBUTE-QUERY-001"


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = "u-learn-attr") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-learn-attr") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _named(text: str, *, kind: str = "thing", class_hint: str | None = None) -> SemanticEntityMention:
    return SemanticEntityMention(
        text=text,
        kind_hint=kind,  # type: ignore[arg-type]
        class_hint=class_hint,
        reference_kind="named",
        confidence=1.0,
    )


def _attr_claim(
    subject: SemanticEntityMention,
    *,
    predicate: str,
    value: str,
    predicate_key: str | None = None,
    value_key: str | None = None,
    origin: SemanticClaimOrigin = SemanticClaimOrigin.EXPLICIT,
) -> SemanticClaim:
    return SemanticClaim(
        kind=SemanticClaimKind.ATTRIBUTE,
        subject=subject,
        predicate=predicate,
        predicate_key=predicate_key,
        value_text=value,
        value_key=value_key,
        origin=origin,
        confidence=1.0,
    )


def _write_proposal(
    raw: str,
    *,
    subject: SemanticEntityMention,
    predicate: str,
    value: str,
    predicate_key: str | None = None,
    value_key: str | None = None,
) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=subject,
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            _attr_claim(
                subject,
                predicate=predicate,
                value=value,
                predicate_key=predicate_key,
                value_key=value_key,
            )
        ],
        confidence=1.0,
    )


def _query_proposal(
    raw: str,
    *,
    subject: SemanticEntityMention,
    predicate: str,
    predicate_key: str | None = None,
) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="query",
        primitive_hint="attribute",
        subject=subject,
        temporal=SemanticTime(),
        claims=[
            SemanticClaim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=subject,
                predicate=predicate,
                predicate_key=predicate_key,
                origin=SemanticClaimOrigin.EXPLICIT,
                confidence=1.0,
            )
        ],
        confidence=1.0,
    )


def _ingest(proposal: SemanticProposal, db: Path, ontology: OntologyRegistry, user: UserContext):
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    svc = IngestService(
        FakeInterpreter({proposal.raw_input: outcome.ir}),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    return svc.ingest(proposal.raw_input, user, _session(user.user_id)), outcome


def _ask(proposal: SemanticProposal, db: Path, ontology: OntologyRegistry, user: UserContext):
    outcome = proposal_to_query_ir(proposal)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    ask = AskService(
        FakeInterpreter({proposal.raw_input: outcome.query_ir}),  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    return ask.ask(proposal.raw_input, user, _session(user.user_id)), outcome


def test_unknown_attribute_dimension_can_be_learned() -> None:
    identity = resolve_dimension_identity(predicate="fur color", learn=True)
    assert identity is not None
    assert identity.key == "attribute.learned.fur_color"
    assert identity.source == "learned"
    assert is_registered_dimension("attribute.learned.fur_color")
    assert alias_to_dimension_key("color") == "color"
    assert identity.key != "color"


def test_learned_attribute_does_not_collapse_to_core_color() -> None:
    fur = resolve_dimension_identity(predicate="fur color", learn=True)
    core = resolve_dimension_identity(predicate="color", learn=True)
    assert fur is not None and core is not None
    assert fur.key == "attribute.learned.fur_color"
    assert core.key == "color"


def test_learned_attribute_is_materialized(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "learned-attr.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    luna = _named("Luna", kind="thing", class_hint="cat")
    result, outcome = _ingest(
        _write_proposal(
            "a luna tem pelos brancos", subject=luna, predicate="fur color", value="branco"
        ),
        db,
        ontology,
        user,
    )
    assert result.status is IngestStatus.COMMITTED, result.issues
    assert outcome.ir is not None and outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "attribute.learned.fur_color"
    assert outcome.ir.attribute.text_value == "branco"
    assert result.claims.received == 1
    assert result.claims.committed == 1
    assert result.claims.deferred == 0
    with open_sqlite_uow(db) as uow:
        attrs: list = []
        for entity in uow.entities.all_for_user(user.user_id):
            attrs.extend(uow.attributes.for_entity(user.user_id, entity.id))
        assert len(attrs) == 1
        assert attrs[0].dimension_key == "attribute.learned.fur_color"
        assert attrs[0].text_value == "branco"
        assert attrs[0].dimension_concept_id == learned_concept_id("attribute.learned.fur_color")
        uow.commit()


def test_learned_attribute_can_be_queried(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "learned-attr-q.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    luna = _named("Luna", kind="thing", class_hint="cat")
    written, _ = _ingest(
        _write_proposal(
            "a luna tem pelos brancos", subject=luna, predicate="fur color", value="branco"
        ),
        db,
        ontology,
        user,
    )
    assert written.status is IngestStatus.COMMITTED
    asked, q_out = _ask(
        _query_proposal("qual a cor dos pelos da luna?", subject=luna, predicate="fur color"),
        db,
        ontology,
        user,
    )
    assert q_out.query_ir is not None
    assert q_out.query_ir.query.attribute_dimension_key == "attribute.learned.fur_color"
    assert asked.status is AskStatus.ANSWERED
    assert asked.query_result is not None
    values = asked.query_result.attribute_values
    assert values and values[0].text_value == "branco"


def test_learned_attribute_reuses_existing_dimension(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "learned-attr-reuse.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    luna = _named("Luna", kind="thing", class_hint="cat")
    first, _ = _ingest(
        _write_proposal("fur one", subject=luna, predicate="fur color", value="branco"),
        db,
        ontology,
        user,
    )
    second, outcome = _ingest(
        _write_proposal("fur two", subject=luna, predicate="fur_color", value="white"),
        db,
        ontology,
        user,
    )
    assert first.status is IngestStatus.COMMITTED
    assert second.status is IngestStatus.COMMITTED
    assert outcome.ir is not None and outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "attribute.learned.fur_color"
    with open_sqlite_uow(db) as uow:
        current = []
        for entity in uow.entities.all_for_user(user.user_id):
            current.extend(
                a
                for a in uow.attributes.for_entity(user.user_id, entity.id)
                if a.dimension_key == "attribute.learned.fur_color" and a.is_current
            )
        assert len(current) == 1
        assert current[0].text_value == "white"
        uow.commit()


def test_learned_attribute_does_not_duplicate_dimension() -> None:
    first = resolve_dimension_identity(predicate="screen coating", learn=True)
    second = resolve_dimension_identity(predicate="screen coating", learn=True)
    assert first is not None and second is not None
    assert first.key == second.key == "attribute.learned.screen_coating"
    ontology = OntologyRegistry.with_core_seeds()
    ir = IngestIR(
        intent=IngestIntent.RECORD_ATTRIBUTE,
        raw_input="x",
        attribute=IrAttribute(
            subject=EntityMention(text="notebook"),
            dimension_key=first.key,
            value_kind="text",
            text_value="matte",
        ),
    )
    bind_learned_attribute_dimensions(ontology, ir)
    bind_learned_attribute_dimensions(ontology, ir)
    assert ontology.get_by_key(first.key) is not None
    matches = [c for c in ontology.concepts() if c.key == first.key]
    assert len(matches) == 1


def test_learned_attribute_does_not_require_raw_input(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "learned-attr-opaque.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    luna = _named("Luna", kind="thing", class_hint="cat")
    proposal = _write_proposal(OPAQUE, subject=luna, predicate="fur color", value="branco")
    result, outcome = _ingest(proposal, db, ontology, user)
    assert result.status is IngestStatus.COMMITTED, result.issues
    assert outcome.ir is not None
    assert outcome.ir.raw_input == OPAQUE
    assert outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "attribute.learned.fur_color"


def test_learned_attribute_is_language_independent(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "learned-attr-lang.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    luna = _named("Luna", kind="thing", class_hint="cat")
    for raw in ("a luna tem pelos brancos", "Luna has white fur", OPAQUE):
        proposal = _write_proposal(raw, subject=luna, predicate="fur color", value="branco")
        outcome = proposal_to_canonical_ir(proposal)
        assert outcome.ir is not None and outcome.ir.attribute is not None
        assert outcome.ir.attribute.dimension_key == "attribute.learned.fur_color"
    written, _ = _ingest(
        _write_proposal(OPAQUE, subject=luna, predicate="fur color", value="branco"),
        db,
        ontology,
        user,
    )
    assert written.status is IngestStatus.COMMITTED
    asked, _ = _ask(
        _query_proposal(OPAQUE_QUERY, subject=luna, predicate="fur color"),
        db,
        ontology,
        user,
    )
    assert asked.status is AskStatus.ANSWERED
    assert asked.query_result is not None
    assert asked.query_result.attribute_values[0].text_value == "branco"


def test_learned_attribute_generalizes_across_domains(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "learned-attr-gen.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    notebook = _named("notebook", kind="thing")
    result, outcome = _ingest(
        _write_proposal(
            "o notebook tem acabamento fosco",
            subject=notebook,
            predicate="screen coating",
            value="matte",
        ),
        db,
        ontology,
        user,
    )
    assert result.status is IngestStatus.COMMITTED, result.issues
    assert outcome.ir is not None and outcome.ir.attribute is not None
    assert outcome.ir.attribute.dimension_key == "attribute.learned.screen_coating"
    asked, _ = _ask(
        _query_proposal("screen coating?", subject=notebook, predicate="screen coating"),
        db,
        ontology,
        user,
    )
    assert asked.status is AskStatus.ANSWERED
    assert asked.query_result is not None
    assert asked.query_result.attribute_values[0].text_value == "matte"


def test_learned_attribute_hydrates_after_restart(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "learned-attr-hydrate.db")
    user = _user()
    ontology = OntologyRegistry.with_core_seeds()
    house = _named("casa", kind="place")
    result, _ = _ingest(
        _write_proposal(
            "minha casa tem telhado ceramico",
            subject=house,
            predicate="roof material",
            value="ceramic",
        ),
        db,
        ontology,
        user,
    )
    assert result.status is IngestStatus.COMMITTED
    key = "attribute.learned.roof_material"
    fresh = OntologyRegistry.with_core_seeds()
    assert fresh.get_by_key(key) is None
    engine = create_sqlite_engine(sqlite_url(db))
    n = hydrate_learned_attribute_dimensions(fresh, engine)
    assert n == 1
    restored = fresh.get_by_key(key)
    assert restored is not None
    assert restored.id == learned_concept_id(key)
    engine.dispose()


def test_slug_from_structured_predicate_not_raw_input() -> None:
    assert learned_attribute_key_from_predicate("fur color") == "attribute.learned.fur_color"
    assert learned_attribute_key_from_predicate("engine displacement") == (
        "attribute.learned.engine_displacement"
    )
    assert "pelos" not in (learned_attribute_key_from_predicate("fur color") or "")
