"""Migração Storage Schema v5 → v6 — Relation termination evidence."""

from __future__ import annotations

from sqlalchemy import Engine, text

_TERM_COLUMNS: tuple[tuple[str, str], ...] = (
    ("term_time_original_text", "TEXT"),
    ("term_time_date", "DATE"),
    ("term_time_instant", "DATETIME"),
    ("term_time_precision", "VARCHAR(32)"),
    ("term_temporal_kind", "VARCHAR(32)"),
    ("term_temporal_relation", "VARCHAR(32)"),
    ("term_temporal_occurrence_status", "VARCHAR(32)"),
    ("term_temporal_unknown_reason", "VARCHAR(32)"),
    ("term_temporal_interval_start", "DATE"),
    ("term_temporal_interval_end", "DATE"),
    ("term_temporal_granularity", "VARCHAR(32)"),
    ("term_temporal_tense_evidence", "TEXT"),
    ("term_temporal_source_kind", "VARCHAR(64)"),
    ("termination_observed_at", "DATETIME"),
    ("termination_raw_input_id", "VARCHAR(32)"),
    ("termination_source_id", "VARCHAR(32)"),
    ("termination_confidence_score", "REAL"),
    ("termination_confidence_qualifier", "VARCHAR(32)"),
)


def migrate_v5_to_v6(engine: Engine) -> None:
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT storage_schema_version FROM schema_meta ORDER BY id LIMIT 1")
        ).scalar()
        if version in {"6", "7"}:
            return
        if version != "5":
            raise RuntimeError(f"migração v5→v6 não soporta versão {version!r}")
        existing = {
            row[1] for row in conn.execute(text("PRAGMA table_info(relations)")).fetchall()
        }
        for name, ddl in _TERM_COLUMNS:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE relations ADD COLUMN {name} {ddl}"))
        rows = conn.execute(
            text(
                """
                SELECT id, is_current, valid_to, observed_at
                FROM relations
                WHERE is_current = 0 AND valid_to IS NOT NULL
                """
            )
        ).fetchall()
        for row_id, is_current, valid_to, observed_at in rows:
            if is_current:
                continue
            if valid_to == observed_at:
                conn.execute(
                    text("UPDATE relations SET valid_to = NULL WHERE id = :id"),
                    {"id": row_id},
                )
        conn.execute(
            text("UPDATE schema_meta SET storage_schema_version = :v"),
            {"v": "6"},
        )
