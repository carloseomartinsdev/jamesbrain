"""Identidade resolvida no servidor. Nunca aceitar user_id do body como autoridade.

Canonical production path: session bearer via ProductAuthService.
DEV_AUTH: only when PKE_AUTH_MODE=dev (explicit). Never silent fallback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

AUTH_MODE_SESSION = "session"
AUTH_MODE_DEV = "dev"
DEV_AUTH_MODE = AUTH_MODE_DEV


@dataclass(frozen=True)
class AuthUser:
    id: str
    display_name: str
    auth_mode: str
    session_id: str | None = None
    username: str | None = None


class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def resolve_auth_mode(raw: str | None = None) -> str:
    mode = (raw if raw is not None else os.environ.get("PKE_AUTH_MODE", "")).strip().lower()
    if not mode:
        return AUTH_MODE_SESSION
    if mode in {AUTH_MODE_SESSION, AUTH_MODE_DEV}:
        return mode
    raise AuthError(
        "AUTH_MISCONFIGURED",
        "Configuração de autenticação inválida.",
        status_code=503,
    )


class DevAuthAdapter:
    """DEV_AUTH — test/dev only. Activate with PKE_AUTH_MODE=dev."""

    def __init__(
        self,
        *,
        default_user_id: str | None = None,
        default_display_name: str | None = None,
    ) -> None:
        self._default_user_id = (
            default_user_id
            or os.environ.get("PKE_DEV_USER_ID", "").strip()
            or "dev-user"
        )
        self._default_display_name = (
            default_display_name
            or os.environ.get("PKE_DEV_DISPLAY_NAME", "").strip()
            or "James"
        )

    def resolve(self, authorization: str | None) -> AuthUser:
        if not authorization:
            raise AuthError("UNAUTHENTICATED", "Credencial ausente ou inválida.")
        scheme, _, rest = authorization.partition(" ")
        if scheme.lower() != "bearer" or not rest.strip():
            raise AuthError("UNAUTHENTICATED", "Credencial ausente ou inválida.")
        token = rest.strip()
        if token.startswith("dev:"):
            candidate = token[4:].strip()
            if not candidate or len(candidate) > 80:
                raise AuthError("UNAUTHENTICATED", "Credencial ausente ou inválida.")
            return AuthUser(
                id=candidate,
                display_name=candidate,
                auth_mode=DEV_AUTH_MODE,
                username=candidate,
            )
        if token == self._default_user_id:
            return AuthUser(
                id=self._default_user_id,
                display_name=self._default_display_name,
                auth_mode=DEV_AUTH_MODE,
                username=self._default_user_id,
            )
        raise AuthError("UNAUTHENTICATED", "Credencial ausente ou inválida.")


class ProductAuthResolver:
    """Resolves AuthUser from Authorization according to PKE_AUTH_MODE."""

    def __init__(self, auth_service: object | None = None, *, mode: str | None = None) -> None:
        self._mode = resolve_auth_mode(mode)
        self._session = auth_service
        self._dev = DevAuthAdapter() if self._mode == AUTH_MODE_DEV else None
        if self._mode == AUTH_MODE_SESSION and self._session is None:
            raise AuthError(
                "AUTH_MISCONFIGURED",
                "Serviço de autenticação não configurado.",
                status_code=503,
            )

    @property
    def mode(self) -> str:
        return self._mode

    def resolve(self, authorization: str | None) -> AuthUser:
        if self._mode == AUTH_MODE_DEV:
            assert self._dev is not None
            return self._dev.resolve(authorization)
        assert self._session is not None
        return self._session.resolve_bearer(authorization)
