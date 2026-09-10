"""Persistência do PKE. Não interpreta nem raciocina.

O pacote chama-se `persist` (não `storage`) porque `**/storage/` está no
`.cursorignore` do monorepo. O papel arquitetural continua sendo Storage.

`persistable` (assessment) ≠ materializado (FKs concretas no banco).
"""

from pke.persist.contracts import UnitOfWork
from pke.persist.errors import RawInputImmutableError, StorageError, StorageIntegrityError
from pke.persist.sqlite.read_store import SqliteKnowledgeReadStore, open_sqlite_read_store
from pke.persist.sqlite.uow import SqliteUnitOfWork, open_sqlite_uow, sqlite_uow
from pke.persist.versions import (
    DEFAULT_SQLITE_PATH,
    STORAGE_SCHEMA_FROZEN,
    STORAGE_SCHEMA_VERSION,
)

__all__ = [
    "DEFAULT_SQLITE_PATH",
    "STORAGE_SCHEMA_FROZEN",
    "STORAGE_SCHEMA_VERSION",
    "RawInputImmutableError",
    "SqliteKnowledgeReadStore",
    "SqliteUnitOfWork",
    "StorageError",
    "StorageIntegrityError",
    "UnitOfWork",
    "open_sqlite_read_store",
    "open_sqlite_uow",
    "sqlite_uow",
]
