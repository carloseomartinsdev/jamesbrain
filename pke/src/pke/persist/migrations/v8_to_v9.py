"""Migração Storage Schema v8 → v9 — measurements (Measurement).

NO semantic backfill — legacy State observed_quantity rows untouched.
"""

from __future__ import annotations

from sqlalchemy import Engine, text


def migrate_v8_to_v9(engine: Engine) -> None:
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT storage_schema_version FROM schema_meta ORDER BY id LIMIT 1")
        ).scalar()
        if version == "9":
            return
        if version != "8":
            raise RuntimeError(f"migração v8→v9 não suporta versão {version!r}")

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS measurements (
                    id VARCHAR(32) NOT NULL,
                    user_id VARCHAR(32) NOT NULL,
                    entity_id VARCHAR(32) NOT NULL,
                    context_entity_id VARCHAR(32),
                    dimension_key VARCHAR(128) NOT NULL,
                    dimension_concept_id VARCHAR(128),
                    numeric_value VARCHAR(40) NOT NULL,
                    unit VARCHAR(32),
                    currency_code VARCHAR(3),
                    time_original_text TEXT NOT NULL DEFAULT '',
                    time_date DATE,
                    time_instant DATETIME,
                    time_precision VARCHAR(32) NOT NULL DEFAULT 'partial',
                    temporal_kind VARCHAR(32) NOT NULL DEFAULT 'unknown',
                    temporal_relation VARCHAR(32),
                    temporal_occurrence_status VARCHAR(32),
                    temporal_unknown_reason VARCHAR(32),
                    temporal_interval_start DATE,
                    temporal_interval_end DATE,
                    temporal_granularity VARCHAR(32),
                    temporal_tense_evidence TEXT,
                    temporal_source_kind VARCHAR(64),
                    observed_at DATETIME,
                    raw_input_id VARCHAR(32),
                    source_id VARCHAR(32) NOT NULL,
                    confidence_score FLOAT,
                    confidence_qualifier VARCHAR(32),
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    FOREIGN KEY(entity_id) REFERENCES entities (id),
                    FOREIGN KEY(context_entity_id) REFERENCES entities (id),
                    FOREIGN KEY(raw_input_id) REFERENCES raw_inputs (id),
                    FOREIGN KEY(source_id) REFERENCES sources (id),
                    CONSTRAINT ck_measurements_unit_currency_xor CHECK (
                        NOT (unit IS NOT NULL AND currency_code IS NOT NULL)
                    ),
                    CONSTRAINT ck_measurements_currency_format CHECK (
                        currency_code IS NULL OR (
                            length(currency_code) = 3
                            AND currency_code = upper(currency_code)
                        )
                    ),
                    CONSTRAINT ck_measurements_dimension_nonempty CHECK (
                        length(trim(dimension_key)) > 0
                    )
                )
                """
            )
        )
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS ix_measurements_user ON measurements (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_measurements_entity ON measurements (entity_id)",
            "CREATE INDEX IF NOT EXISTS ix_measurements_entity_dim "
            "ON measurements (entity_id, dimension_key)",
            "CREATE INDEX IF NOT EXISTS ix_measurements_entity_dim_observed "
            "ON measurements (entity_id, dimension_key, observed_at)",
            "CREATE INDEX IF NOT EXISTS ix_measurements_dimension ON measurements (dimension_key)",
            "CREATE INDEX IF NOT EXISTS ix_measurements_context "
            "ON measurements (context_entity_id)",
        ):
            conn.execute(text(idx_sql))

        conn.execute(
            text("UPDATE schema_meta SET storage_schema_version = :v"),
            {"v": "9"},
        )
