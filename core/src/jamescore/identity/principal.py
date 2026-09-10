from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    sub: str
    display_name: str | None = None
    issuer: str = ""
