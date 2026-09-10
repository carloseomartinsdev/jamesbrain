"""Migração Storage Schema v3 → v4 — State dimension/value semantics."""

from __future__ import annotations

from sqlalchemy import Engine, text

from pke.ontology.seeds import core_concept_id

_V4_COLUMNS: tuple[tuple[str, str], ...] = (
    ("dimension_concept_id", "VARCHAR(128)"),
    ("dimension_key", "VARCHAR(128)"),
    ("value_concept_id", "VARCHAR(128)"),
    ("value_key", "VARCHAR(128)"),
    ("is_current", "INTEGER NOT NULL DEFAULT 1"),
)

_LEGACY_V3_KEYS: dict[str, tuple[str, str]] = {
    "state.anomaly": ("state.operational_condition", "state.value.broken"),
    "state.working": ("state.operational_condition", "state.value.working"),
    "state.depletion": ("state.availability", "state.value.depleted"),
    "state.unpaid": ("state.payment_status", "state.value.unpaid"),
    "state.open": ("state.openness", "state.value.open"),
    "state.expired": ("state.validity", "state.value.expired"),
    "state.observed_quantity": ("state.observed_quantity", "state.value.quantity_observation"),
}


def migrate_v3_to_v4(engine: Engine) -> None:
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT storage_schema_version FROM schema_meta ORDER BY id LIMIT 1")
        ).scalar()
        if version in {"4", "5", "6", "7"}:
            return
        if version != "3":
            raise RuntimeError(f"migração v3→v4 não suporta versão {version!r}")
        existing = {
            row[1] for row in conn.execute(text("PRAGMA table_info(states)")).fetchall()
        }
        for name, ddl in _V4_COLUMNS:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE states ADD COLUMN {name} {ddl}"))
        rows = conn.execute(text("SELECT id, key, valid_to FROM states")).fetchall()
        for row_id, legacy_key, valid_to in rows:
            dim_key, val_key = _LEGACY_V3_KEYS.get(
                legacy_key,
                (legacy_key, legacy_key),
            )
            conn.execute(
                text(
                    """
                    UPDATE states SET
                        dimension_concept_id = :dim_id,
                        dimension_key = :dim_key,
                        value_concept_id = :val_id,
                        value_key = :val_key,
                        is_current = :is_current
                    WHERE id = :id
                    """
                ),
                {
                    "id": row_id,
                    "dim_id": core_concept_id(dim_key),
                    "dim_key": dim_key,
                    "val_id": core_concept_id(val_key),
                    "val_key": val_key,
                    "is_current": 0 if valid_to is not None else 1,
                },
            )
        conn.execute(
            text("UPDATE schema_meta SET storage_schema_version = :v"),
            {"v": "4"},
        )
