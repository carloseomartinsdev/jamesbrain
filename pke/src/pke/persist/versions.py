"""Versões de schema de persistência. Sem tabela de ontologia CORE.

Canonical version source for databases: schema_meta.storage_schema_version
Application target: STORAGE_SCHEMA_VERSION (must match CURRENT_SCHEMA_VERSION in runner).

Authority: pke.persist.migrations.runner (see ADR 0027). Alembic is non-authoritative.
"""

STORAGE_SCHEMA_VERSION = "11"
STORAGE_SCHEMA_FROZEN = False
DEFAULT_SQLITE_PATH = "data/pke.db"
