"""Migração Storage Schema v10 → v11 — principal_bindings (E1.1).

Additive only. No reinterpretation of existing knowledge rows.
"""

from __future__ import annotations

from sqlalchemy import Engine, text


def migrate_v10_to_v11(engine: Engine) -> None:
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT storage_schema_version FROM schema_meta ORDER BY id LIMIT 1")
        ).scalar()
        if version == "11":
            return
        if version != "10":
            raise RuntimeError(f"migração v10→v11 não suporta versão {version!r}")

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS principal_bindings (
                    user_id VARCHAR(64) NOT NULL,
                    entity_id VARCHAR(32) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (user_id),
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    FOREIGN KEY(entity_id) REFERENCES entities (id),
                    CONSTRAINT uq_principal_bindings_entity UNIQUE (entity_id)
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_principal_bindings_entity "
                "ON principal_bindings (entity_id)"
            )
        )
        conn.execute(
            text("UPDATE schema_meta SET storage_schema_version = :v"),
            {"v": "11"},
        )
