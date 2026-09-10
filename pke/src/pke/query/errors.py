"""Erros do QueryEngine. Sem copy de UI."""


class QueryError(Exception):
    """Falha de consulta determinística."""


class QuerySpecError(QueryError):
    """ResolvedQuerySpec inválido (conceito, kind, associação)."""


class QueryIsolationError(QueryError):
    """ID não visível para o usuário da consulta."""


class MultiCurrencyAggregateError(QueryError):
    """SUM recusado quando há mais de uma currency."""
