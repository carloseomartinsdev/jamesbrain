"""Migração Storage Schema v4 → v5 — Relation evolution (temporal, currentness, history)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Engine, text

CORE_PREFIX = "core:"


def migrate_v4_to_v5(engine: Engine) -> None:
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT storage_schema_version FROM schema_meta ORDER BY id LIMIT 1")
        ).scalar()
        if version in {"5", "6", "7"}:
            return
        if version != "4":
            raise RuntimeError(f"migração v4→v5 não suporta versão {version!r}")
        existing = {
            row[1] for row in conn.execute(text("PRAGMA table_info(relations)")).fetchall()
        }
        columns: tuple[tuple[str, str], ...] = (
            ("key", "VARCHAR(128) NOT NULL DEFAULT ''"),
            ("is_current", "INTEGER NOT NULL DEFAULT 1"),
            ("time_original_text", "TEXT NOT NULL DEFAULT ''"),
            ("time_date", "DATE"),
            ("time_instant", "DATETIME"),
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
            ("observed_at", "DATETIME"),
            ("caused_by_event_id", "VARCHAR(32)"),
            ("supersedes_id", "VARCHAR(32)"),
            ("raw_input_id", "VARCHAR(32)"),
            ("source_id", "VARCHAR(32)"),
            ("confidence_score", "REAL"),
            ("confidence_qualifier", "VARCHAR(32)"),
            ("created_at", "DATETIME"),
        )
        for name, ddl in columns:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE relations ADD COLUMN {name} {ddl}"))
        fallback = dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat()
        rows = conn.execute(
            text("SELECT id, type_id, valid_from, valid_to FROM relations")
        ).fetchall()
        for row_id, type_id, valid_from, valid_to in rows:
            key = type_id.removeprefix(CORE_PREFIX) if type_id.startswith(CORE_PREFIX) else type_id
            observed = valid_from or fallback
            conn.execute(
                text(
                    """
                    UPDATE relations SET
                        key = :key,
                        is_current = :is_current,
                        temporal_kind = 'partial',
                        temporal_relation = 'during',
                        temporal_occurrence_status = 'ongoing',
                        temporal_unknown_reason = 'not_provided',
                        time_precision = 'partial',
                        observed_at = :observed_at,
                        created_at = :created_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": row_id,
                    "key": key,
                    "is_current": 0 if valid_to is not None else 1,
                    "observed_at": observed,
                    "created_at": observed,
                },
            )
        conn.execute(
            text("UPDATE schema_meta SET storage_schema_version = :v"),
            {"v": "5"},
        )
