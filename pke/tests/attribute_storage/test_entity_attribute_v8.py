"""I11.12.2 — EntityAttribute storage v8 persistence tests (AV / A8-P / PC)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from pke.application import FixedClock, IngestService, IngestStatus
from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.domain.ids import new_ulid
from pke.domain.temporal_knowledge import TemporalKnowledge, TemporalUnknownReason
from pke.domain.value_objects import Confidence, Source, SourceKind, UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_uow
from pke.persist.errors import StorageIntegrityError
from pke.persist.migrations.errors import MigrationFailed, UnsupportedSchemaVersion
from pke.persist.migrations.runner import (
    CURRENT_SCHEMA_VERSION,
    MigrationStep,
    read_schema_version,
    schemas_structurally_equal,
    upgrade_to_current,
)
from pke.persist.sqlite.engine import create_sqlite_engine, init_database, sqlite_url
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.ontology.seeds import CORE_SCHEMA_VERSION
from tests.attribute_design import as_fixtures as asf
from tests.attribute_design import fixtures as af
from tests.generalization_ingest.fixtures import benchmark_session, benchmark_user, fresh_db_path
from tests.integration.test_ingest import NOW


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _ingest(proposal, db: Path) -> object:
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    user = benchmark_user()
    svc = IngestService(
        FakeInterpreter({proposal.raw_input: outcome.ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    return svc.ingest(proposal.raw_input, user, benchmark_session()), user


def _attrs(db: Path, user_id: str):
    with open_sqlite_uow(db) as uow:
        out = []
        for e in uow.entities.all_for_user(user_id):
            out.extend(uow.attributes.for_entity(user_id, e.id))
        return out


# --- V8 migration ---


def test_v8_1_fresh_schema(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "f.db"))
    init_database(eng)
    assert read_schema_version(eng) == 11
    assert STORAGE_SCHEMA_VERSION == "11"
    assert CURRENT_SCHEMA_VERSION == 11
    with eng.connect() as conn:
        assert "entity_attributes" in {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }


def test_v8_2_v7_to_v8(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "m.db"))
    init_database(eng)
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM schema_meta"))
        conn.execute(
            text(
                "INSERT INTO schema_meta (storage_schema_version, core_schema_version) "
                "VALUES ('7', :c)"
            ),
            {"c": CORE_SCHEMA_VERSION},
        )
        conn.execute(text("DROP TABLE IF EXISTS entity_attributes"))
        conn.execute(text("DROP TABLE IF EXISTS measurements"))
    applied = upgrade_to_current(eng)
    assert "v7_to_v8" in applied
    assert "v8_to_v9" in applied
    assert read_schema_version(eng) == 11


def test_v8_3_noop(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "n.db"))
    init_database(eng)
    assert upgrade_to_current(eng) == []


def test_v8_4_future(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "x.db"))
    init_database(eng)
    with eng.begin() as conn:
        conn.execute(text("UPDATE schema_meta SET storage_schema_version='12'"))
    with pytest.raises(UnsupportedSchemaVersion):
        upgrade_to_current(eng)


def test_v8_5_failure_keeps_7(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "fail.db"))
    init_database(eng)
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM schema_meta"))
        conn.execute(
            text(
                "INSERT INTO schema_meta (storage_schema_version, core_schema_version) "
                "VALUES ('7', :c)"
            ),
            {"c": CORE_SCHEMA_VERSION},
        )
        conn.execute(text("DROP TABLE IF EXISTS entity_attributes"))
        conn.execute(text("DROP TABLE IF EXISTS measurements"))

    def boom(_e) -> None:
        raise RuntimeError("boom")

    with pytest.raises(MigrationFailed):
        upgrade_to_current(eng, steps=(MigrationStep(7, 8, boom, "boom"),), target=8)
    assert read_schema_version(eng) == 7


def test_v8_6_fresh_equals_migrated(tmp_path: Path) -> None:
    fresh = create_sqlite_engine(sqlite_url(tmp_path / "fr.db"))
    init_database(fresh)
    migrated = create_sqlite_engine(sqlite_url(tmp_path / "mg.db"))
    init_database(migrated)
    with migrated.begin() as conn:
        conn.execute(text("DELETE FROM schema_meta"))
        conn.execute(
            text(
                "INSERT INTO schema_meta (storage_schema_version, core_schema_version) "
                "VALUES ('7', :c)"
            ),
            {"c": CORE_SCHEMA_VERSION},
        )
        conn.execute(text("DROP TABLE IF EXISTS entity_attributes"))
        conn.execute(text("DROP TABLE IF EXISTS measurements"))
    upgrade_to_current(migrated)
    assert schemas_structurally_equal(fresh, migrated)


# --- AV persistence ---


@pytest.mark.parametrize(
    ("factory", "dim", "kind"),
    [
        (af.at1_corolla_silver, "color", AttributeValueKind.TEXT),
        (af.at2_house_area, "area", AttributeValueKind.NUMBER),
        (af.at3_notebook_weight, "weight", AttributeValueKind.NUMBER),
        (af.at8_joao_height, "height", AttributeValueKind.NUMBER),
        (af.at9_corolla_year, "model_year", AttributeValueKind.YEAR),
        (af.at12_tank_capacity_50, "capacity", AttributeValueKind.NUMBER),
    ],
    ids=["AV1", "AV2", "AV3", "AV4", "AV5", "AV6"],
)
def test_av_persist(factory, dim, kind, tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, dim)
    result, user = _ingest(factory(), db)
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization and result.materialization.attribute_ids
    attrs = _attrs(db, user.user_id)
    assert len(attrs) == 1
    assert attrs[0].dimension_key == dim
    assert attrs[0].value_kind is kind
    assert attrs[0].temporal.kind.value == "unknown"
    assert attrs[0].valid_from is None


def test_a8_p7_multiple_colors(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "multi")
    black = af.at1_corolla_silver().model_copy(
        update={"raw_input": "O Corolla é preto.", "attribute_expression": "preto"}
    )
    silver = af.at1_corolla_silver()
    r1, user = _ingest(black, db)
    r2, _ = _ingest(silver, db)
    assert r1.status is IngestStatus.COMMITTED
    assert r2.status is IngestStatus.COMMITTED
    attrs = _attrs(db, user.user_id)
    colors = [a for a in attrs if a.dimension_key == "color"]
    assert len(colors) == 2
    assert {a.text_value for a in colors} == {"preto", "prata"}
    current = [a for a in colors if a.is_current]
    closed = [a for a in colors if not a.is_current]
    assert len(current) == 1 and len(closed) == 1
    assert current[0].text_value == "prata"
    assert closed[0].text_value == "preto"
    assert current[0].supersedes_id == closed[0].id


def test_a8_p8_repeated_evidence(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "rep")
    p = af.at1_corolla_silver()
    r1, user = _ingest(p, db)
    # second ingest same value — new assertion (no dedup)
    r2, _ = _ingest(p.model_copy(update={"raw_input": "O Corolla é prata (de novo)."}), db)
    assert r1.status is IngestStatus.COMMITTED
    assert r2.status is IngestStatus.COMMITTED
    colors = [a for a in _attrs(db, user.user_id) if a.dimension_key == "color"]
    assert len(colors) == 2
    assert all(a.text_value == "prata" for a in colors)
    assert sum(1 for a in colors if a.is_current) == 1


def test_a8_p9_cross_user_rejected(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "xu")
    result, user = _ingest(af.at1_corolla_silver(), db)
    assert result.status is IngestStatus.COMMITTED
    attrs = _attrs(db, user.user_id)
    assert attrs
    other = UserContext(user_id="other-user", timezone="UTC")
    bad = attrs[0].model_copy(update={"user_id": other.user_id, "id": new_ulid()})
    with open_sqlite_uow(db) as uow:
        with pytest.raises(StorageIntegrityError):
            uow.attributes.add(bad)


def test_a8_p10_invalid_typed_slots() -> None:
    with pytest.raises(Exception):
        EntityAttribute(
            id=new_ulid(),
            user_id="u",
            entity_id="e",
            dimension_key="color",
            value_kind=AttributeValueKind.TEXT,
            text_value="prata",
            year_value=2020,
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            source=Source(id="s", user_id="u", kind=SourceKind.USER_STATEMENT),
        )


def test_a8_p11_historical_unknown_time(tmp_path: Path) -> None:
    proposal = af.at1_corolla_silver().model_copy(
        update={
            "raw_input": "O Corolla era preto.",
            "attribute_expression": "preto",
            "temporal": af.at1_corolla_silver().temporal.model_copy(
                update={"tense_evidence": "era"}
            ),
        }
    )
    db = fresh_db_path(tmp_path, "hist")
    result, user = _ingest(proposal, db)
    assert result.status is IngestStatus.COMMITTED
    attrs = _attrs(db, user.user_id)
    assert attrs[0].is_current is False
    assert attrs[0].valid_from is None
    assert attrs[0].temporal.kind.value in {"unknown", "partial"}


def test_a8_p12_classification_no_attribute(tmp_path: Path) -> None:
    proposal = af.at14_corolla_is_car()
    assert route_primitive(proposal)[0] is PrimitiveKind.TYPE
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is None
    db = fresh_db_path(tmp_path, "type")
    # cannot ingest without IR — ensure no accidental Attribute via empty path
    assert _attrs(db, benchmark_user().user_id) == []


@pytest.mark.parametrize(
    ("factory", "expected"),
    [
        (asf.as3_corolla_broken, PrimitiveKind.STATE),
        (asf.as4_corolla_broke, PrimitiveKind.EVENT),
        (asf.as5_corolla_belongs_joao, PrimitiveKind.RELATION),
        (asf.as7_tank_20_liters, PrimitiveKind.MEASUREMENT),
        (asf.as2_corolla_is_car, PrimitiveKind.TYPE),
    ],
    ids=["PC2", "PC7", "PC5", "PC4", "PC6"],
)
def test_pc_no_entity_attribute(factory, expected, tmp_path: Path) -> None:
    proposal = factory()
    prim, _ = route_primitive(proposal)
    assert prim is expected
    outcome = proposal_to_canonical_ir(proposal)
    if outcome.ir is not None:
        assert outcome.ir.attribute is None
        db = fresh_db_path(tmp_path, expected.value)
        result, user = _ingest(proposal, db)
        if result.status is IngestStatus.COMMITTED:
            assert _attrs(db, user.user_id) == []
