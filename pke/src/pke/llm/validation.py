"""Formatação de erros Pydantic para diagnóstico wire."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError


def format_validation_issues(exc: ValidationError) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in exc.errors():
        path = ".".join(str(part) for part in item.get("loc", ()))
        issues.append(
            {
                "path": path,
                "type": item.get("type"),
                "reason": item.get("msg"),
                "input": _safe_input(item.get("input")),
            }
        )
    return issues


def _safe_input(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, dict)):
        text = str(value)
        return text[:200] + ("…" if len(text) > 200 else "")
    return type(value).__name__
