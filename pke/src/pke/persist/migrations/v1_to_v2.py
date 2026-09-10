"""Migração Storage Schema v1 → v2 — TemporalKnowledge."""

from __future__ import annotations

from sqlalchemy import Engine, text

_V2_COLUMNS: tuple[tuple[str, str], ...] = (
    ("temporal_kind", "VARCHAR(32) NOT NULL DEFAULT 'exact'"),
    ("temporal_relation", "VARCHAR(32)"),
    ("temporal_occurrence_status", "VARCHAR(32)"),
    ("temporal_unknown_reason", "VARCHAR(32)"),
    ("temporal_interval_start", "DATE"),
    ("temporal_interval_end", "DATE"),
    ("temporal_granularity", "VARCHAR(32)"),
    ("temporal_tense_evidence", "TEXT"),
    ("temporal_source_kind", "VARCHAR(64)"),
)


def migrate_v1_to_v2(engine: Engine) -> None:
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT storage_schema_version FROM schema_meta ORDER BY id LIMIT 1")
        ).scalar()
        if version in {"2", "3", "4", "5", "6", "7"}:
            return
        if version != "1":
            raise RuntimeError(f"migração v1→v2 não suporta versão {version!r}")
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(events)")).fetchall()
        }
        for name, ddl in _V2_COLUMNS:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE events ADD COLUMN {name} {ddl}"))
        conn.execute(
            text("UPDATE schema_meta SET storage_schema_version = :v"),
            {"v": "2"},
        )
