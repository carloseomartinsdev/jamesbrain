"""Migração Storage Schema v2 → v3 — State primitive com TemporalKnowledge."""

from __future__ import annotations

from sqlalchemy import Engine, text

_STATE_V3_COLUMNS: tuple[tuple[str, str], ...] = (
    ("time_original_text", "TEXT NOT NULL DEFAULT ''"),
    ("time_precision", "VARCHAR(32) NOT NULL DEFAULT 'partial'"),
    ("temporal_kind", "VARCHAR(32) NOT NULL DEFAULT 'partial'"),
    ("temporal_relation", "VARCHAR(32)"),
    ("temporal_occurrence_status", "VARCHAR(32)"),
    ("temporal_unknown_reason", "VARCHAR(32)"),
    ("temporal_interval_start", "DATE"),
    ("temporal_interval_end", "DATE"),
    ("temporal_granularity", "VARCHAR(32)"),
    ("temporal_tense_evidence", "TEXT"),
    ("temporal_source_kind", "VARCHAR(64)"),
    ("time_date", "DATE"),
    ("time_instant", "DATETIME"),
    ("observed_at", "DATETIME"),
    ("raw_input_id", "VARCHAR(32)"),
    ("source_id", "VARCHAR(32)"),
    ("supersedes_id", "VARCHAR(32)"),
    ("created_at", "DATETIME"),
    ("confidence_score", "REAL"),
    ("confidence_qualifier", "VARCHAR(32)"),
)


def migrate_v2_to_v3(engine: Engine) -> None:
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT storage_schema_version FROM schema_meta ORDER BY id LIMIT 1")
        ).scalar()
        if version in {"3", "4", "5", "6", "7"}:
            return
        if version != "2":
            raise RuntimeError(f"migração v2→v3 não suporta versão {version!r}")
        existing = {
            row[1] for row in conn.execute(text("PRAGMA table_info(states)")).fetchall()
        }
        for name, ddl in _STATE_V3_COLUMNS:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE states ADD COLUMN {name} {ddl}"))
        conn.execute(
            text(
                """
                UPDATE states SET
                    observed_at = COALESCE(observed_at, valid_from),
                    created_at = COALESCE(created_at, valid_from),
                    temporal_kind = COALESCE(temporal_kind, 'exact'),
                    time_precision = COALESCE(time_precision, 'day'),
                    time_original_text = COALESCE(time_original_text, '')
                WHERE observed_at IS NULL
                """
            )
        )
        conn.execute(
            text("UPDATE schema_meta SET storage_schema_version = :v"),
            {"v": "3"},
        )
