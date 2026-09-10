"""Erros de persistência."""


class StorageError(Exception):
    """Falha de persistência."""


class StorageIntegrityError(StorageError):
    """FK, isolamento ou constraint violada."""


class RawInputImmutableError(StorageError):
    """RawInput não pode ser alterado nem regravado."""
