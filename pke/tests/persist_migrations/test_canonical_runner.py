"""I11.10.2 — canonical migration runner (M1–M6) and MIGRATION-01 closure tests."""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy import text

from pke.ontology.seeds import CORE_SCHEMA_VERSION, core_concept_id
from pke.persist.migrations.errors import MigrationFailed, UnsupportedSchemaVersion
from pke.persist.migrations.runner import (
    CURRENT_SCHEMA_VERSION,
    MIGRATION_DIRECTION,
    MIGRATIONS,
    MigrationStep,
    read_schema_version,
    schemas_structurally_equal,
    table_column_map,
    upgrade_to_current,
)
from pke.persist.sqlite.engine import create_sqlite_engine, init_database, sqlite_url
from pke.persist.versions import STORAGE_SCHEMA_VERSION


def _engine(path: Path):
    eng = create_sqlite_engine(sqlite_url(path))
    return eng


def _fresh_current(path: Path):
    eng = _engine(path)
    init_database(eng)
    return eng


def _stamp(conn, version: str) -> None:
    conn.execute(text("DELETE FROM schema_meta"))
    conn.execute(
        text(
            "INSERT INTO schema_meta (storage_schema_version, core_schema_version) "
            "VALUES (:s, :c)"
        ),
        {"s": version, "c": CORE_SCHEMA_VERSION},
    )


def _minimal_v5(path: Path):
    """Current ORM tables stamped as version 5."""
    eng = _engine(path)
    init_database(eng)
    with eng.begin() as conn:
        _stamp(conn, "5")
    return eng


def _minimal_v6(path: Path):
    """Current ORM tables stamped as version 6."""
    eng = _engine(path)
    init_database(eng)
    with eng.begin() as conn:
        _stamp(conn, "6")
    return eng


_fresh_v6 = _fresh_current


def _seed_knowledge(eng) -> dict[str, str]:
    now = dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.UTC).isoformat()
    ids = {
        "user": "u1",
        "entity": "e1",
        "raw": "r1",
        "event": "ev1",
        "state": "st1",
        "rel": "rel1",
        "source": "src1",
        "entity2": "e2",
    }
    with eng.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, created_at) VALUES (:id, :at)"),
            {"id": ids["user"], "at": now},
        )
        conn.execute(
            text(
                "INSERT INTO raw_inputs (id, user_id, text, created_at) "
                "VALUES (:id, :u, :t, :at)"
            ),
            {"id": ids["raw"], "u": ids["user"], "t": "seed", "at": now},
        )
        for eid, name, typ in (
            (ids["entity"], "João", "entity.person"),
            (ids["entity2"], "Acme", "entity.organization"),
        ):
            conn.execute(
                text(
                    "INSERT INTO entities "
                    "(id, user_id, type_id, canonical_name, normalized_canonical_name, created_at) "
                    "VALUES (:id, :u, :type, :name, :norm, :at)"
                ),
                {
                    "id": eid,
                    "u": ids["user"],
                    "type": core_concept_id(typ),
                    "name": name,
                    "norm": name.casefold(),
                    "at": now,
                },
            )
        conn.execute(
            text(
                "INSERT INTO sources (id, user_id, kind, raw_input_id) "
                "VALUES (:id, :u, :k, :r)"
            ),
            {"id": ids["source"], "u": ids["user"], "k": "user_statement", "r": ids["raw"]},
        )
        conn.execute(
            text(
                """
                INSERT INTO events (
                    id, user_id, type_id, status, raw_input_id, created_at,
                    time_original_text, time_precision, temporal_kind,
                    actor_id, subject_id
                ) VALUES (
                    :id, :u, :type, 'completed', :raw, :at,
                    '', 'day', 'exact',
                    :actor, :subject
                )
                """
            ),
            {
                "id": ids["event"],
                "u": ids["user"],
                "type": core_concept_id("event.maintenance"),
                "raw": ids["raw"],
                "at": now,
                "actor": ids["entity"],
                "subject": ids["entity2"],
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO states (
                    id, user_id, entity_id,
                    dimension_concept_id, dimension_key,
                    value_concept_id, value_key, is_current,
                    payload_kind,
                    time_original_text, time_precision, temporal_kind,
                    observed_at, created_at
                ) VALUES (
                    :id, :u, :e,
                    :dim_id, :dim_key,
                    :val_id, :val_key, 1,
                    'none',
                    '', 'day', 'exact',
                    :at, :at
                )
                """
            ),
            {
                "id": ids["state"],
                "u": ids["user"],
                "e": ids["entity"],
                "at": now,
                "dim_id": core_concept_id("state.openness"),
                "dim_key": "state.openness",
                "val_id": core_concept_id("state.value.open"),
                "val_key": "state.value.open",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO relations (
                    id, user_id, type_id, from_id, to_id, valid_from,
                    key, is_current,
                    time_original_text, time_precision, temporal_kind,
                    observed_at, created_at
                ) VALUES (
                    :id, :u, :type, :frm, :to, :at,
                    :key, 1,
                    '', 'partial', 'partial',
                    :at, :at
                )
                """
            ),
            {
                "id": ids["rel"],
                "u": ids["user"],
                "type": core_concept_id("relation.employment"),
                "frm": ids["entity"],
                "to": ids["entity2"],
                "at": now,
                "key": "relation.employment",
            },
        )
    return ids


# --- M1–M6 ---


def test_m1_fresh_database_initializes_to_current(tmp_path: Path) -> None:
    eng = _fresh_current(tmp_path / "m1.db")
    assert read_schema_version(eng) == 11
    assert STORAGE_SCHEMA_VERSION == "11"
    assert CURRENT_SCHEMA_VERSION == 11


def test_m2_existing_v5_upgrades_to_current(tmp_path: Path) -> None:
    eng = _minimal_v5(tmp_path / "m2.db")
    assert read_schema_version(eng) == 5
    applied = upgrade_to_current(eng)
    assert applied == ["v5_to_v6", "v6_to_v7", "v7_to_v8", "v8_to_v9", "v9_to_v10", "v10_to_v11"]
    assert read_schema_version(eng) == 11


def test_m3_current_performs_no_migration(tmp_path: Path) -> None:
    eng = _fresh_current(tmp_path / "m3.db")
    applied = upgrade_to_current(eng)
    assert applied == []
    assert read_schema_version(eng) == 11


def test_m4_future_unsupported_version_fails_safely(tmp_path: Path) -> None:
    eng = _fresh_current(tmp_path / "m4.db")
    with eng.begin() as conn:
        _stamp(conn, "12")
    with pytest.raises(UnsupportedSchemaVersion):
        upgrade_to_current(eng)
    assert read_schema_version(eng) == 12


def test_m5_migration_failure_does_not_advance_version(tmp_path: Path) -> None:
    eng = _minimal_v6(tmp_path / "m5.db")
    assert read_schema_version(eng) == 6

    def boom(_engine) -> None:
        raise RuntimeError("simulated migration failure")

    steps = (MigrationStep(6, 7, boom, "boom_v6_to_v7"),)
    with pytest.raises(MigrationFailed):
        upgrade_to_current(eng, steps=steps, target=7)
    assert read_schema_version(eng) == 6


def test_m6_fresh_equals_migrated_schema(tmp_path: Path) -> None:
    fresh = _fresh_current(tmp_path / "m6_fresh.db")
    migrated = _minimal_v5(tmp_path / "m6_mig.db")
    upgrade_to_current(migrated)
    assert schemas_structurally_equal(fresh, migrated)
    assert table_column_map(fresh) == table_column_map(migrated)


def test_multi_hop_v4_to_v7(tmp_path: Path) -> None:
    eng = _fresh_current(tmp_path / "hop.db")
    with eng.begin() as conn:
        _stamp(conn, "4")
    applied = upgrade_to_current(eng)
    assert applied == ["v4_to_v5", "v5_to_v6", "v6_to_v7", "v7_to_v8", "v8_to_v9", "v9_to_v10", "v10_to_v11"]
    assert read_schema_version(eng) == 11


def test_data_preservation_across_upgrade(tmp_path: Path) -> None:
    eng = _minimal_v5(tmp_path / "data.db")
    ids = _seed_knowledge(eng)
    upgrade_to_current(eng)
    with eng.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM entities")).scalar() == 2
        assert conn.execute(text("SELECT COUNT(*) FROM events")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM states")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM relations")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM event_participants")).scalar() >= 2
        event = conn.execute(
            text("SELECT actor_id, subject_id FROM events WHERE id = :id"),
            {"id": ids["event"]},
        ).one()
        assert event[0] == ids["entity"]
        assert event[1] == ids["entity2"]
        assert (
            conn.execute(
                text("SELECT canonical_name FROM entities WHERE id = :id"),
                {"id": ids["entity"]},
            ).scalar()
            == "João"
        )


def test_migration_direction_forward_only() -> None:
    assert MIGRATION_DIRECTION == "FORWARD_ONLY"


def test_registry_is_contiguous_to_current() -> None:
    assert MIGRATIONS[0].from_version == 1
    assert MIGRATIONS[-1].to_version == CURRENT_SCHEMA_VERSION
    for i, step in enumerate(MIGRATIONS[:-1]):
        assert step.to_version == MIGRATIONS[i + 1].from_version


def test_provider_independence_of_migration_package() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "pke" / "persist" / "migrations"
    forbidden = ("pke.interpretation.deepseek", "pke.providers", "openai", "httpx")
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(f in alias.name for f in forbidden), path
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(f in node.module for f in forbidden), path


def test_alembic_stubs_are_non_authoritative() -> None:
    import importlib.util

    stub = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "001_storage_v2_temporal_knowledge.py"
    )
    spec = importlib.util.spec_from_file_location("alembic_stub_001", stub)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(RuntimeError, match="not the PKE schema authority"):
        mod.upgrade()
