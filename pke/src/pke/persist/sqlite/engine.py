"""Engine SQLite com FK obrigatório."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from pke.persist.migrations.runner import ensure_schema_meta_row, upgrade_to_current
from pke.persist.sqlite.tables import Base
from pke.persist.versions import DEFAULT_SQLITE_PATH


def create_sqlite_engine(url: str) -> Engine:
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def sqlite_url(path: str | Path) -> str:
    resolved = Path(path)
    if not resolved.is_absolute() and str(path) != ":memory:":
        resolved = Path.cwd() / resolved
    if str(path) == ":memory:":
        return "sqlite:///:memory:"
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{resolved.as_posix()}"


def init_database(engine: Engine) -> None:
    """Create latest ORM tables, ensure schema_meta, then run canonical upgrades.

    Fresh DBs are created at current ORM shape and stamped with STORAGE_SCHEMA_VERSION;
    upgrade_to_current is a no-op when already current. Existing DBs at older versions
    receive ordered Python migrations via the single migration authority.
    """
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(_RELATIONS_TRIGGER))
        conn.execute(text(_EVENTS_ACTOR_TRIGGER))
        conn.execute(text(_EVENTS_SUBJECT_TRIGGER))
        conn.execute(text(_SOURCES_RAW_TRIGGER))
        conn.execute(text(_FACTS_SOURCE_TRIGGER))
        ensure_schema_meta_row(conn)
    upgrade_to_current(engine)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


_RELATIONS_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS relations_same_user
BEFORE INSERT ON relations
BEGIN
  SELECT CASE
    WHEN (SELECT user_id FROM entities WHERE id = NEW.from_id) != NEW.user_id
      OR (SELECT user_id FROM entities WHERE id = NEW.to_id) != NEW.user_id
    THEN RAISE(ABORT, 'cross-user relation')
  END;
END;
"""

_EVENTS_ACTOR_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS events_actor_same_user
BEFORE INSERT ON events
WHEN NEW.actor_id IS NOT NULL
BEGIN
  SELECT CASE
    WHEN (SELECT user_id FROM entities WHERE id = NEW.actor_id) != NEW.user_id
    THEN RAISE(ABORT, 'event actor cross-user')
  END;
END;
"""

_SOURCES_RAW_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS sources_raw_same_user
BEFORE INSERT ON sources
WHEN NEW.raw_input_id IS NOT NULL
BEGIN
  SELECT CASE
    WHEN (SELECT user_id FROM raw_inputs WHERE id = NEW.raw_input_id) != NEW.user_id
    THEN RAISE(ABORT, 'source raw_input cross-user')
  END;
END;
"""

_FACTS_SOURCE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS facts_source_same_user
BEFORE INSERT ON facts
BEGIN
  SELECT CASE
    WHEN (SELECT user_id FROM sources WHERE id = NEW.source_id) != NEW.user_id
    THEN RAISE(ABORT, 'fact source cross-user')
  END;
END;
"""

_EVENTS_SUBJECT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS events_subject_same_user
BEFORE INSERT ON events
WHEN NEW.subject_id IS NOT NULL
BEGIN
  SELECT CASE
    WHEN (SELECT user_id FROM entities WHERE id = NEW.subject_id) != NEW.user_id
    THEN RAISE(ABORT, 'event subject cross-user')
  END;
END;
"""


__all__ = [
    "DEFAULT_SQLITE_PATH",
    "create_sqlite_engine",
    "init_database",
    "session_factory",
    "sqlite_url",
]
