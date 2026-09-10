"""Migração Storage Schema v7 → v8 — entity_attributes (EntityAttribute).

No semantic backfill — first-class Attribute storage did not exist in v7.
"""

from __future__ import annotations

from sqlalchemy import Engine, text


def migrate_v7_to_v8(engine: Engine) -> None:
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT storage_schema_version FROM schema_meta ORDER BY id LIMIT 1")
        ).scalar()
        if version == "8":
            return
        if version != "7":
            raise RuntimeError(f"migração v7→v8 não suporta versão {version!r}")

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS entity_attributes (
                    id VARCHAR(32) NOT NULL,
                    user_id VARCHAR(32) NOT NULL,
                    entity_id VARCHAR(32) NOT NULL,
                    dimension_key VARCHAR(128) NOT NULL,
                    dimension_concept_id VARCHAR(128),
                    value_kind VARCHAR(16) NOT NULL,
                    concept_value_id VARCHAR(128),
                    text_value TEXT,
                    numeric_value VARCHAR(40),
                    unit VARCHAR(32),
                    date_value DATE,
                    year_value INTEGER,
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
                    observed_at DATETIME NOT NULL,
                    valid_from DATETIME,
                    valid_to DATETIME,
                    is_current BOOLEAN NOT NULL DEFAULT 1,
                    supersedes_id VARCHAR(32),
                    raw_input_id VARCHAR(32),
                    source_id VARCHAR(32) NOT NULL,
                    confidence_score FLOAT,
                    confidence_qualifier VARCHAR(32),
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    FOREIGN KEY(entity_id) REFERENCES entities (id),
                    FOREIGN KEY(supersedes_id) REFERENCES entity_attributes (id),
                    FOREIGN KEY(raw_input_id) REFERENCES raw_inputs (id),
                    FOREIGN KEY(source_id) REFERENCES sources (id),
                    CONSTRAINT ck_entity_attributes_value_kind CHECK (
                        (value_kind = 'text' AND text_value IS NOT NULL AND numeric_value IS NULL
                         AND year_value IS NULL AND date_value IS NULL AND concept_value_id IS NULL AND unit IS NULL)
                        OR (value_kind = 'number' AND numeric_value IS NOT NULL AND text_value IS NULL
                            AND year_value IS NULL AND date_value IS NULL AND concept_value_id IS NULL)
                        OR (value_kind = 'year' AND year_value IS NOT NULL AND text_value IS NULL
                            AND numeric_value IS NULL AND date_value IS NULL AND concept_value_id IS NULL AND unit IS NULL)
                        OR (value_kind = 'date' AND date_value IS NOT NULL AND text_value IS NULL
                            AND numeric_value IS NULL AND year_value IS NULL AND concept_value_id IS NULL AND unit IS NULL)
                        OR (value_kind = 'concept' AND concept_value_id IS NOT NULL AND text_value IS NULL
                            AND numeric_value IS NULL AND year_value IS NULL AND date_value IS NULL AND unit IS NULL)
                    ),
                    CONSTRAINT ck_entity_attribute_no_self_supersede CHECK (id != supersedes_id)
                )
                """
            )
        )
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS ix_entity_attributes_user ON entity_attributes (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_entity_attributes_entity ON entity_attributes (entity_id)",
            "CREATE INDEX IF NOT EXISTS ix_entity_attributes_entity_dim "
            "ON entity_attributes (entity_id, dimension_key)",
            "CREATE INDEX IF NOT EXISTS ix_entity_attributes_entity_dim_current "
            "ON entity_attributes (entity_id, dimension_key, is_current)",
            "CREATE INDEX IF NOT EXISTS ix_entity_attributes_dimension "
            "ON entity_attributes (dimension_key)",
        ):
            conn.execute(text(idx_sql))

        conn.execute(
            text("UPDATE schema_meta SET storage_schema_version = :v"),
            {"v": "8"},
        )
