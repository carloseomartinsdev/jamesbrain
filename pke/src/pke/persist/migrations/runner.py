"""Canonical storage schema migration runner — single authority (MIGRATION-01).

Deterministic, ordered, forward-only. No LLM/provider imports.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Engine, inspect, text
from sqlalchemy.engine import Connection

from pke.ontology.seeds import CORE_SCHEMA_VERSION
from pke.persist.migrations.errors import (
    InvalidSchemaState,
    MigrationFailed,
    UnsupportedSchemaVersion,
)
from pke.persist.migrations.v1_to_v2 import migrate_v1_to_v2
from pke.persist.migrations.v2_to_v3 import migrate_v2_to_v3
from pke.persist.migrations.v3_to_v4 import migrate_v3_to_v4
from pke.persist.migrations.v4_to_v5 import migrate_v4_to_v5
from pke.persist.migrations.v5_to_v6 import migrate_v5_to_v6
from pke.persist.migrations.v6_to_v7 import migrate_v6_to_v7
from pke.persist.migrations.v7_to_v8 import migrate_v7_to_v8
from pke.persist.migrations.v8_to_v9 import migrate_v8_to_v9
from pke.persist.migrations.v9_to_v10 import migrate_v9_to_v10
from pke.persist.migrations.v10_to_v11 import migrate_v10_to_v11
from pke.persist.versions import STORAGE_SCHEMA_VERSION

logger = logging.getLogger(__name__)

UpgradeFn = Callable[[Engine], None]


@dataclass(frozen=True)
class MigrationStep:
    from_version: int
    to_version: int
    upgrade: UpgradeFn
    name: str


# Explicit ordered registry — no dynamic discovery.
MIGRATIONS: tuple[MigrationStep, ...] = (
    MigrationStep(1, 2, migrate_v1_to_v2, "v1_to_v2"),
    MigrationStep(2, 3, migrate_v2_to_v3, "v2_to_v3"),
    MigrationStep(3, 4, migrate_v3_to_v4, "v3_to_v4"),
    MigrationStep(4, 5, migrate_v4_to_v5, "v4_to_v5"),
    MigrationStep(5, 6, migrate_v5_to_v6, "v5_to_v6"),
    MigrationStep(6, 7, migrate_v6_to_v7, "v6_to_v7"),
    MigrationStep(7, 8, migrate_v7_to_v8, "v7_to_v8"),
    MigrationStep(8, 9, migrate_v8_to_v9, "v8_to_v9"),
    MigrationStep(9, 10, migrate_v9_to_v10, "v9_to_v10"),
    MigrationStep(10, 11, migrate_v10_to_v11, "v10_to_v11"),
)

CURRENT_SCHEMA_VERSION = int(STORAGE_SCHEMA_VERSION)
MIGRATION_DIRECTION = "FORWARD_ONLY"


def parse_schema_version(raw: str | int | None) -> int:
    if raw is None:
        raise InvalidSchemaState("schema version is missing")
    text_v = str(raw).strip()
    if not text_v.isdigit():
        raise InvalidSchemaState(f"schema version is not an integer: {raw!r}")
    return int(text_v)


def read_schema_version(engine: Engine) -> int:
    """Canonical version source: schema_meta.storage_schema_version."""
    insp = inspect(engine)
    if "schema_meta" not in insp.get_table_names():
        raise InvalidSchemaState("schema_meta table does not exist")
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT storage_schema_version FROM schema_meta ORDER BY id LIMIT 1"
            )
        ).first()
        if row is None:
            raise InvalidSchemaState("schema_meta has no rows")
        return parse_schema_version(row[0])


def ensure_schema_meta_row(conn: Connection, *, storage_version: str | None = None) -> None:
    count = conn.execute(text("SELECT COUNT(*) FROM schema_meta")).scalar()
    if count:
        return
    version = storage_version or STORAGE_SCHEMA_VERSION
    conn.execute(
        text(
            "INSERT INTO schema_meta (storage_schema_version, core_schema_version) "
            "VALUES (:s, :c)"
        ),
        {"s": version, "c": CORE_SCHEMA_VERSION},
    )


def upgrade_to_current(
    engine: Engine,
    *,
    steps: tuple[MigrationStep, ...] | None = None,
    target: int | None = None,
) -> list[str]:
    """Apply ordered migrations until STORAGE_SCHEMA_VERSION.

    Returns names of steps that ran. Idempotent when already current.
    `steps` / `target` are for tests only — production always uses the registry.
    """
    version = read_schema_version(engine)
    goal = CURRENT_SCHEMA_VERSION if target is None else target
    registry = steps if steps is not None else MIGRATIONS
    by_from = {step.from_version: step for step in registry}
    if version > goal:
        raise UnsupportedSchemaVersion(
            f"database schema version {version} is newer than supported {goal}"
        )
    applied: list[str] = []
    while version < goal:
        step = by_from.get(version)
        if step is None:
            raise UnsupportedSchemaVersion(
                f"no migration registered from version {version} toward {goal}"
            )
        logger.info(
            "storage migration %s: %s → %s",
            step.name,
            step.from_version,
            step.to_version,
        )
        before = version
        try:
            step.upgrade(engine)
        except (UnsupportedSchemaVersion, InvalidSchemaState, MigrationFailed):
            raise
        except Exception as exc:  # noqa: BLE001
            after_fail = _safe_read(engine)
            if after_fail is not None and after_fail != before:
                raise MigrationFailed(
                    f"{step.name} failed after advancing version "
                    f"{before}→{after_fail}: {exc}"
                ) from exc
            raise MigrationFailed(f"{step.name} failed: {exc}") from exc
        version = read_schema_version(engine)
        if version != step.to_version:
            raise MigrationFailed(
                f"{step.name} did not advance version to {step.to_version}; "
                f"still {version}"
            )
        applied.append(step.name)
    return applied


def _safe_read(engine: Engine) -> int | None:
    try:
        return read_schema_version(engine)
    except Exception:  # noqa: BLE001
        return None


def table_column_map(engine: Engine) -> dict[str, tuple[str, ...]]:
    """Structural snapshot for schema equivalence tests."""
    insp = inspect(engine)
    out: dict[str, tuple[str, ...]] = {}
    for name in sorted(insp.get_table_names()):
        cols = tuple(sorted(col["name"] for col in insp.get_columns(name)))
        out[name] = cols
    return out


def schemas_structurally_equal(left: Engine, right: Engine) -> bool:
    return table_column_map(left) == table_column_map(right)
