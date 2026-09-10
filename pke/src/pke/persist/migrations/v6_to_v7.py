"""Migração Storage Schema v6 → v7 — EventParticipant table + safe legacy backfill.

I11.10.3-R: EntityKind ≠ SemanticRole. v6 stored no participant-role provenance,
so every legacy actor_id / subject_id association becomes role.unspecified.
New semantic writes (post-cutover) are unaffected — they write explicit roles.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

from pke.domain.ids import new_ulid

LEGACY_SAFE_ROLE = "role.unspecified"


def classify_legacy_actor_role(type_id: str | None = None) -> str:
    """Legacy actor_id has no persisted role evidence — never promote to actor/context."""
    del type_id
    return LEGACY_SAFE_ROLE


def classify_legacy_subject_role(type_id: str | None = None) -> str:
    """Legacy subject_id is overloaded — never invent OBJECT/PATIENT certainty."""
    del type_id
    return LEGACY_SAFE_ROLE


def migrate_v6_to_v7(engine: Engine) -> None:
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT storage_schema_version FROM schema_meta ORDER BY id LIMIT 1")
        ).scalar()
        if version == "7":
            return
        if version != "6":
            raise RuntimeError(f"migração v6→v7 não suporta versão {version!r}")

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS event_participants (
                    id VARCHAR(32) NOT NULL,
                    event_id VARCHAR(32) NOT NULL,
                    entity_id VARCHAR(32) NOT NULL,
                    role VARCHAR(64) NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE,
                    FOREIGN KEY(entity_id) REFERENCES entities (id),
                    CONSTRAINT uq_event_participant_role UNIQUE (event_id, entity_id, role)
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_event_participants_event "
                "ON event_participants (event_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_event_participants_entity "
                "ON event_participants (entity_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_event_participants_event_role "
                "ON event_participants (event_id, role)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_event_participants_entity_role "
                "ON event_participants (entity_id, role)"
            )
        )

        events = conn.execute(
            text("SELECT id, actor_id, subject_id FROM events")
        ).fetchall()
        existing = {
            (row[0], row[1], row[2])
            for row in conn.execute(
                text("SELECT event_id, entity_id, role FROM event_participants")
            ).fetchall()
        }

        for event_id, actor_id, subject_id in events:
            planned: list[tuple[str, str]] = []
            if actor_id:
                planned.append((actor_id, classify_legacy_actor_role()))
            if subject_id:
                planned.append((subject_id, classify_legacy_subject_role()))
            seen_local: set[tuple[str, str]] = set()
            for entity_id, role in planned:
                key = (entity_id, role)
                if key in seen_local:
                    continue
                seen_local.add(key)
                triple = (event_id, entity_id, role)
                if triple in existing:
                    continue
                conn.execute(
                    text(
                        "INSERT INTO event_participants (id, event_id, entity_id, role) "
                        "VALUES (:id, :event_id, :entity_id, :role)"
                    ),
                    {
                        "id": new_ulid(),
                        "event_id": event_id,
                        "entity_id": entity_id,
                        "role": role,
                    },
                )
                existing.add(triple)

        conn.execute(
            text("UPDATE schema_meta SET storage_schema_version = :v"),
            {"v": "7"},
        )
