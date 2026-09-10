"""Erros do runner canônico de migration (MIGRATION-01)."""

from __future__ import annotations

from pke.persist.errors import StorageError


class UnsupportedSchemaVersion(StorageError):
    """DB schema version is higher than application support, or unknown."""


class MigrationFailed(StorageError):
    """A migration step raised; schema version must not claim success."""


class InvalidSchemaState(StorageError):
    """Missing or corrupt schema_meta / unreadable version."""
