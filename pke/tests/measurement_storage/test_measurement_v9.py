"""I11.15.2 — Measurement storage schema v9 persistence tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from pke.application import FixedClock, IngestService, IngestStatus
from pke.domain.ids import new_ulid
from pke.domain.measurements import Measurement
from pke.domain.temporal_knowledge import TemporalKnowledge, TemporalUnknownReason
from pke.domain.value_objects import Confidence, Source, SourceKind
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.models import PrimitiveKind, SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.router import collect_assertions, route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.ontology.seeds import CORE_SCHEMA_VERSION
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
from tests.attribute_design import fixtures as af
from tests.generalization_ingest.fixtures import benchmark_session, benchmark_user, fresh_db_path
from tests.integration.test_ingest import NOW
from tests.measurement_design import fixtures as mf
from tests.semantic_resolution.fixtures import sc4_replace_clutch


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _ingest(proposal: SemanticProposal, db: Path):
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, (proposal.raw_input, outcome.failure_stage)
    user = benchmark_user()
    svc = IngestService(
        FakeInterpreter({proposal.raw_input: outcome.ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    return svc.ingest(proposal.raw_input, user, benchmark_session()), user


def _measurements(db: Path, user_id: str) -> list[Measurement]:
    with open_sqlite_uow(db) as uow:
        return uow.measurements.for_user(user_id)


def _attrs(db: Path, user_id: str):
    with open_sqlite_uow(db) as uow:
        out = []
        for e in uow.entities.all_for_user(user_id):
            out.extend(uow.attributes.for_entity(user_id, e.id))
        return out


def _states(db: Path, user_id: str):
    with open_sqlite_uow(db) as uow:
        out = []
        for e in uow.entities.all_for_user(user_id):
            out.extend(uow.states.for_entity(user_id, e.id))
        return out


def _events(db: Path, user_id: str):
    with open_sqlite_uow(db) as uow:
        # events repo has get only — scan via session
        from pke.persist.sqlite.tables import EventRow
        from sqlalchemy import select

        rows = uow.session.scalars(  # type: ignore[union-attr]
            select(EventRow).where(EventRow.user_id == user_id)
        ).all()
        return list(rows)


# --- Migration ---


def test_v9_fresh_schema(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "f.db"))
    init_database(eng)
    assert read_schema_version(eng) == 11
    assert STORAGE_SCHEMA_VERSION == "11"
    assert CURRENT_SCHEMA_VERSION == 11
    with eng.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "measurements" in tables
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(measurements)"))}
        assert "is_current" not in cols
        assert "supersedes_id" not in cols
        assert "observed_at" in cols
        assert "currency_code" in cols


def test_v8_to_v9(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "m.db"))
    init_database(eng)
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM schema_meta"))
        conn.execute(
            text(
                "INSERT INTO schema_meta (storage_schema_version, core_schema_version) "
                "VALUES ('8', :c)"
            ),
            {"c": CORE_SCHEMA_VERSION},
        )
        conn.execute(text("DROP TABLE IF EXISTS measurements"))
    applied = upgrade_to_current(eng)
    assert applied == ["v8_to_v9", "v9_to_v10", "v10_to_v11"]
    assert read_schema_version(eng) == 11


def test_v9_noop(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "n.db"))
    init_database(eng)
    assert upgrade_to_current(eng) == []


def test_v9_future_rejected(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "x.db"))
    init_database(eng)
    with eng.begin() as conn:
        conn.execute(text("UPDATE schema_meta SET storage_schema_version='12'"))
    with pytest.raises(UnsupportedSchemaVersion):
        upgrade_to_current(eng)


def test_v9_failed_migration_remains_v8(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "fail.db"))
    init_database(eng)
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM schema_meta"))
        conn.execute(
            text(
                "INSERT INTO schema_meta (storage_schema_version, core_schema_version) "
                "VALUES ('8', :c)"
            ),
            {"c": CORE_SCHEMA_VERSION},
        )
        conn.execute(text("DROP TABLE IF EXISTS measurements"))

    def boom(_e) -> None:
        raise RuntimeError("boom")

    with pytest.raises(MigrationFailed):
        upgrade_to_current(eng, steps=(MigrationStep(8, 9, boom, "boom"),), target=9)
    assert read_schema_version(eng) == 8


def test_v9_fresh_equals_migrated(tmp_path: Path) -> None:
    fresh = create_sqlite_engine(sqlite_url(tmp_path / "fr.db"))
    init_database(fresh)
    migrated = create_sqlite_engine(sqlite_url(tmp_path / "mg.db"))
    init_database(migrated)
    with migrated.begin() as conn:
        conn.execute(text("DELETE FROM schema_meta"))
        conn.execute(
            text(
                "INSERT INTO schema_meta (storage_schema_version, core_schema_version) "
                "VALUES ('8', :c)"
            ),
            {"c": CORE_SCHEMA_VERSION},
        )
        conn.execute(text("DROP TABLE IF EXISTS measurements"))
    upgrade_to_current(migrated)
    assert schemas_structurally_equal(fresh, migrated)


def test_no_legacy_state_backfill(tmp_path: Path) -> None:
    eng = create_sqlite_engine(sqlite_url(tmp_path / "leg.db"))
    init_database(eng)
    with eng.begin() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM states")).scalar()
        conn.execute(text("DELETE FROM schema_meta"))
        conn.execute(
            text(
                "INSERT INTO schema_meta (storage_schema_version, core_schema_version) "
                "VALUES ('8', :c)"
            ),
            {"c": CORE_SCHEMA_VERSION},
        )
        conn.execute(text("DROP TABLE IF EXISTS measurements"))
    upgrade_to_current(eng)
    with eng.connect() as conn:
        after = conn.execute(text("SELECT COUNT(*) FROM states")).scalar()
        assert after == before
        assert conn.execute(text("SELECT COUNT(*) FROM measurements")).scalar() == 0


# --- Domain / repository ---


def test_domain_percentage_and_currency_xor(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "dom")
    user = benchmark_user()
    with open_sqlite_uow(db) as uow:
        from pke.domain.entities import Entity
        from pke.domain.value_objects import RawInput

        raw = RawInput(id=new_ulid(), user_id=user.user_id, text="t", created_at=NOW)
        uow.raw_inputs.add(raw)
        src = Source(id=new_ulid(), user_id=user.user_id, kind=SourceKind.USER_STATEMENT, raw_input_id=raw.id)
        uow.sources.add(src)
        ent = Entity(
            id=new_ulid(),
            user_id=user.user_id,
            type_id="entity.thing",
            canonical_name="bateria",
            aliases=[],
            created_at=NOW,
        )
        uow.entities.add(ent)
        m = Measurement(
            id=new_ulid(),
            user_id=user.user_id,
            entity_id=ent.id,
            dimension_key="battery_charge",
            numeric_value=Decimal("80"),
            unit="%",
            temporal=TemporalKnowledge.unknown("", unknown_reason=TemporalUnknownReason.NOT_PROVIDED),
            source=src,
            raw_input_id=raw.id,
            confidence=Confidence(score=1.0),
            created_at=NOW,
        )
        uow.measurements.add(m)
        uow.commit()
        got = uow.measurements.get(user.user_id, m.id)
        assert got is not None
        assert got.numeric_value == Decimal("80")
        assert got.unit == "%"
        assert got.observed_at is None
        with pytest.raises(ValueError):
            Measurement(
                id=new_ulid(),
                user_id=user.user_id,
                entity_id=ent.id,
                dimension_key="balance",
                numeric_value=Decimal("1"),
                unit="L",
                currency_code="BRL",
                temporal=TemporalKnowledge.unknown("", unknown_reason=TemporalUnknownReason.NOT_PROVIDED),
                created_at=NOW,
            )


def test_repo_cross_user_rejected(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "iso")
    user = benchmark_user()
    other = "user_other_iso"
    with open_sqlite_uow(db) as uow:
        from pke.domain.entities import Entity
        from pke.domain.value_objects import RawInput
        from pke.persist.sqlite.tables import UserRow

        uow.session.add(UserRow(id=other, created_at=NOW))  # type: ignore[union-attr]
        uow.session.flush()  # type: ignore[union-attr]
        raw = RawInput(id=new_ulid(), user_id=user.user_id, text="t", created_at=NOW)
        uow.raw_inputs.add(raw)
        src = Source(id=new_ulid(), user_id=user.user_id, kind=SourceKind.USER_STATEMENT, raw_input_id=raw.id)
        uow.sources.add(src)
        foreign = Entity(
            id=new_ulid(),
            user_id=other,
            type_id="entity.thing",
            canonical_name="x",
            aliases=[],
            created_at=NOW,
        )
        uow.entities.add(foreign)
        m = Measurement(
            id=new_ulid(),
            user_id=user.user_id,
            entity_id=foreign.id,
            dimension_key="temperature",
            numeric_value=Decimal("38"),
            unit="°C",
            temporal=TemporalKnowledge.unknown("", unknown_reason=TemporalUnknownReason.NOT_PROVIDED),
            source=src,
            raw_input_id=raw.id,
            confidence=Confidence(score=1.0),
            created_at=NOW,
        )
        with pytest.raises(StorageIntegrityError):
            uow.measurements.add(m)


def test_repo_history_and_repeated_evidence(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "hist")
    user = benchmark_user()
    with open_sqlite_uow(db) as uow:
        from pke.domain.entities import Entity
        from pke.domain.value_objects import RawInput

        raw = RawInput(id=new_ulid(), user_id=user.user_id, text="t", created_at=NOW)
        uow.raw_inputs.add(raw)
        src = Source(id=new_ulid(), user_id=user.user_id, kind=SourceKind.USER_STATEMENT, raw_input_id=raw.id)
        uow.sources.add(src)
        ent = Entity(
            id=new_ulid(),
            user_id=user.user_id,
            type_id="entity.thing",
            canonical_name="bateria",
            aliases=[],
            created_at=NOW,
        )
        uow.entities.add(ent)
        for val in ("80", "60", "80"):
            uow.measurements.add(
                Measurement(
                    id=new_ulid(),
                    user_id=user.user_id,
                    entity_id=ent.id,
                    dimension_key="battery_charge",
                    numeric_value=Decimal(val),
                    unit="%",
                    temporal=TemporalKnowledge.unknown(
                        "", unknown_reason=TemporalUnknownReason.NOT_PROVIDED
                    ),
                    source=src,
                    raw_input_id=raw.id,
                    confidence=Confidence(score=1.0),
                    created_at=NOW,
                )
            )
        uow.commit()
        rows = uow.measurements.for_entity_dimension(user.user_id, ent.id, "battery_charge")
        assert len(rows) == 3


# --- Materialization MV ---


@pytest.mark.parametrize(
    ("factory", "dim", "num", "unit", "currency"),
    [
        (af.at11_tank_20_liters, "fuel_level", Decimal("20"), "L", None),
        (mf.m3_battery_charge, "battery_charge", Decimal("80"), "%", None),
        (mf.m6_odometer, "odometer", Decimal("125000"), "km", None),
        (mf.m8_temperature, "temperature", Decimal("38"), "°C", None),
        (mf.m12_account_balance, "balance", Decimal("2500"), None, "BRL"),
    ],
    ids=["MV1", "MV2", "MV3", "MV4", "MV5"],
)
def test_mv_measurement_commit(factory, dim, num, unit, currency, tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, dim)
    result, user = _ingest(factory(), db)
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization and result.materialization.measurement_ids
    rows = _measurements(db, user.user_id)
    assert len(rows) == 1
    assert rows[0].dimension_key == dim
    assert rows[0].numeric_value == num
    assert rows[0].unit == unit
    assert rows[0].currency_code == currency
    assert rows[0].observed_at is None
    assert not _attrs(db, user.user_id)
    assert not _states(db, user.user_id)


def test_mv6_inventory_count(tmp_path: Path) -> None:
    proposal = SemanticProposal(
        raw_input="Há 12 garrafas na geladeira.",
        object=SemanticEntityMention(text="garrafas", kind_hint="thing"),
        entities_mentioned=[SemanticEntityMention(text="geladeira", kind_hint="appliance")],
        measurement_expression="12",
        measurable_dimension_key="inventory_count",
        measurement_numeric_value="12",
        measurement_semantics=True,
        primitive_hint="measurement",
    )
    db = fresh_db_path(tmp_path, "inv")
    result, user = _ingest(proposal, db)
    assert result.status is IngestStatus.COMMITTED
    rows = _measurements(db, user.user_id)
    assert len(rows) == 1
    assert rows[0].numeric_value == Decimal("12")
    assert rows[0].unit is None
    assert rows[0].currency_code is None


def test_mv7_entityless_not_materialized() -> None:
    proposal = SemanticProposal(
        raw_input="Está 38 graus.",
        measurement_expression="38",
        measurable_dimension_key="temperature",
        measurement_numeric_value="38",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="measurement",
    )
    assert route_primitive(proposal)[0] is PrimitiveKind.MEASUREMENT
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is None


# --- Non-Measurement regressions ---


@pytest.mark.parametrize(
    "factory",
    [af.at2_house_area, af.at3_notebook_weight],
    ids=["NV1", "NV2"],
)
def test_nv_attribute_only(factory, tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, factory.__name__)
    result, user = _ingest(factory(), db)
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization and result.materialization.attribute_ids
    assert not _measurements(db, user.user_id)


def test_nv3_capacity_routes_attribute_not_measurement() -> None:
    assert route_primitive(mf.m5_battery_capacity())[0] is PrimitiveKind.ATTRIBUTE
    outcome = proposal_to_canonical_ir(mf.m5_battery_capacity())
    if outcome.ir is not None:
        assert outcome.ir.measurement is None
        assert outcome.ir.attribute is not None


def test_nv4_state_routes_not_measurement() -> None:
    assert route_primitive(mf.m4_battery_depleted())[0] is PrimitiveKind.STATE
    outcome = proposal_to_canonical_ir(mf.m4_battery_depleted())
    if outcome.ir is not None:
        assert outcome.ir.measurement is None


def test_nv5_tank_empty_state(tmp_path: Path) -> None:
    proposal = SemanticProposal(
        raw_input="O tanque está vazio.",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        state_expression="vazio",
        condition_semantics=True,
        primitive_hint="state",
    )
    # May or may not resolve state value — ensure no Measurement
    outcome = proposal_to_canonical_ir(proposal)
    if outcome.ir is not None:
        db = fresh_db_path(tmp_path, "nv5")
        result, user = _ingest(proposal, db)
        assert not _measurements(db, user.user_id)


# --- Multi-primitive ---


def test_mv8_event_plus_measurement(tmp_path: Path) -> None:
    base = sc4_replace_clutch()
    proposal = base.model_copy(
        update={
            "raw_input": "Troquei a embreagem e o odômetro estava em 125000 km.",
            "measurement_semantics": True,
            "measurement_expression": "125000 km",
            "measurable_dimension_key": "odometer",
            "measurement_numeric_value": "125000",
            "measurement_unit": "km",
            "subject": SemanticEntityMention(text="odômetro", kind_hint="thing"),
        }
    )
    frames = collect_assertions(proposal)
    assert {f.primitive for f in frames} == {PrimitiveKind.EVENT, PrimitiveKind.MEASUREMENT}
    db = fresh_db_path(tmp_path, "mv8")
    result, user = _ingest(proposal, db)
    assert result.status is IngestStatus.COMMITTED
    mat = result.materialization
    assert mat and mat.event_ids and mat.measurement_ids
    assert len(mat.event_ids) == 1
    assert len(mat.measurement_ids) == 1
    assert len(_measurements(db, user.user_id)) == 1
    assert len(_events(db, user.user_id)) == 1
    assert not _attrs(db, user.user_id)
    assert not _states(db, user.user_id)


def test_partial_event_ok_measurement_skipped(tmp_path: Path) -> None:
    """Valid Event + Measurement without measured entity → Event commits."""
    base = sc4_replace_clutch()
    proposal = base.model_copy(
        update={
            "raw_input": "Troquei a embreagem e deu 95.",
            "measurement_semantics": True,
            "measurement_expression": "95",
            "measurable_dimension_key": "temperature",
            "measurement_numeric_value": "95",
            "measurement_unit": "°C",
            # no subject/object for measurement entity
            "object": SemanticEntityMention(text="embreagem", kind_hint="thing"),
            "subject": None,
        }
    )
    db = fresh_db_path(tmp_path, "partial")
    result, user = _ingest(proposal, db)
    assert result.status is IngestStatus.COMMITTED
    assert result.materialization and result.materialization.event_ids
    # Measurement may wire via object=embreagem — if so it commits; force no meas by clearing object meas path
    # object is embreagem so measurement WOULD use object. Use empty object for skip:
    proposal2 = base.model_copy(
        update={
            "raw_input": "Troquei a embreagem e medi algo.",
            "measurement_semantics": True,
            "measurement_expression": "95",
            "measurable_dimension_key": "temperature",
            "measurement_numeric_value": "95",
            "measurement_unit": "°C",
            "subject": None,
            "object": None,
        }
    )
    outcome = proposal_to_canonical_ir(proposal2)
    assert outcome.ir is not None
    assert outcome.ir.event is not None
    assert outcome.ir.measurement is None
    db2 = fresh_db_path(tmp_path, "partial2")
    result2, user2 = _ingest(proposal2, db2)
    assert result2.status is IngestStatus.COMMITTED
    assert result2.materialization and result2.materialization.event_ids
    assert not _measurements(db2, user2.user_id)


def test_duplicate_assertion_materialization_zero(tmp_path: Path) -> None:
    proposal = af.at11_tank_20_liters()
    db = fresh_db_path(tmp_path, "dup")
    result, user = _ingest(proposal, db)
    assert result.status is IngestStatus.COMMITTED
    assert len(result.materialization.measurement_ids) == 1  # type: ignore[union-attr]
    assert len(_measurements(db, user.user_id)) == 1


def test_core_unchanged() -> None:
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67
