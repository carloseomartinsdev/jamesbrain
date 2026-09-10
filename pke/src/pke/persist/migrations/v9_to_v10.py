"""Migração Storage Schema v9 → v10 — knowledge_corrections (Correction ledger).

NO correction backfill — legacy world rows untouched.
"""

from __future__ import annotations

from sqlalchemy import Engine, text


def migrate_v9_to_v10(engine: Engine) -> None:
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT storage_schema_version FROM schema_meta ORDER BY id LIMIT 1")
        ).scalar()
        if version == "10":
            return
        if version != "9":
            raise RuntimeError(f"migração v9→v10 não suporta versão {version!r}")

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS knowledge_corrections (
                    id VARCHAR(32) NOT NULL,
                    user_id VARCHAR(64) NOT NULL,
                    operation VARCHAR(16) NOT NULL,
                    target_kind VARCHAR(16) NOT NULL,
                    target_id VARCHAR(32) NOT NULL,
                    replacement_kind VARCHAR(16),
                    replacement_id VARCHAR(32),
                    raw_input_id VARCHAR(32),
                    source_id VARCHAR(32),
                    recorded_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    FOREIGN KEY(raw_input_id) REFERENCES raw_inputs (id),
                    FOREIGN KEY(source_id) REFERENCES sources (id),
                    CONSTRAINT uq_knowledge_corrections_target
                        UNIQUE (user_id, target_kind, target_id),
                    CONSTRAINT ck_knowledge_corrections_operation
                        CHECK (operation IN ('retract', 'replace')),
                    CONSTRAINT ck_knowledge_corrections_target_kind
                        CHECK (target_kind IN (
                            'event', 'measurement', 'relation', 'state', 'attribute'
                        )),
                    CONSTRAINT ck_knowledge_corrections_replacement_kind
                        CHECK (
                            replacement_kind IS NULL
                            OR replacement_kind IN (
                                'event', 'measurement', 'relation', 'state', 'attribute'
                            )
                        ),
                    CONSTRAINT ck_knowledge_corrections_op_replacement
                        CHECK (
                            (
                                operation = 'retract'
                                AND replacement_kind IS NULL
                                AND replacement_id IS NULL
                            )
                            OR (
                                operation = 'replace'
                                AND replacement_kind IS NOT NULL
                                AND replacement_id IS NOT NULL
                            )
                        ),
                    CONSTRAINT ck_knowledge_corrections_no_self
                        CHECK (
                            NOT (
                                replacement_kind IS NOT NULL
                                AND replacement_id IS NOT NULL
                                AND target_kind = replacement_kind
                                AND target_id = replacement_id
                            )
                        )
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_corrections_target "
                "ON knowledge_corrections (user_id, target_kind, target_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_corrections_replacement "
                "ON knowledge_corrections (user_id, replacement_kind, replacement_id)"
            )
        )
        conn.execute(
            text("UPDATE schema_meta SET storage_schema_version = :v"),
            {"v": "10"},
        )
