"""Erros de resolução temporal — sem fallback silencioso."""


class TemporalError(Exception):
    """Falha ao resolver tempo."""


class ImpossibleTimeError(TemporalError):
    """Expressão temporal impossível (intervalo invertido, weekday inválido, etc.)."""


class InsufficientTemporalContextError(TemporalError):
    """Falta relógio, política ou campo estruturado para resolver com segurança."""


class InvalidTimezoneError(TemporalError):
    def __init__(self, timezone: str) -> None:
        self.timezone = timezone
        super().__init__(f"timezone inválido: {timezone}")


class TemporalConflictError(TemporalError):
    """Campos temporais divergentes (hoje vs data absoluta, weekday vs data, ...)."""


class EntityResolutionError(Exception):
    """Falha de resolução de entidade."""


class ForeignEntityError(EntityResolutionError):
    """ID explícito existe, mas não é visível para o usuário corrente."""


class ContextIsolationError(EntityResolutionError):
    """Contexto pessoal de outro usuário."""
