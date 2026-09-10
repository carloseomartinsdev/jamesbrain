"""Migrações de schema de persistência — autoridade canônica Python.

Use `upgrade_to_current` / `MIGRATIONS` from `runner`.
Alembic stubs under /alembic are non-authoritative reference only.
"""

from pke.persist.migrations.errors import (
    InvalidSchemaState,
    MigrationFailed,
    UnsupportedSchemaVersion,
)
from pke.persist.migrations.runner import (
    CURRENT_SCHEMA_VERSION,
    MIGRATION_DIRECTION,
    MIGRATIONS,
    MigrationStep,
    ensure_schema_meta_row,
    read_schema_version,
    schemas_structurally_equal,
    table_column_map,
    upgrade_to_current,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "InvalidSchemaState",
    "MIGRATION_DIRECTION",
    "MIGRATIONS",
    "MigrationFailed",
    "MigrationStep",
    "UnsupportedSchemaVersion",
    "ensure_schema_meta_row",
    "read_schema_version",
    "schemas_structurally_equal",
    "table_column_map",
    "upgrade_to_current",
]
