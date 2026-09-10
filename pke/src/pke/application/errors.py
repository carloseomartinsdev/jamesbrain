"""Erros da application. Não são issues de reasoning."""


class MaterializationDenied(ValueError):
    """Tentativa de materializar conhecimento não persistível."""
