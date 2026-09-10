"""Product identity & session authority.

PRODUCT_IDENTITY_AUTHORITY = ProductAuthService
PRODUCT_SESSION_AUTHORITY = ProductAuthService / product sessions table
ENGINE_USER_IDENTITY_SOURCE = AuthUser.id from authenticated Product session

DEV_AUTH is opt-in only (PKE_AUTH_MODE=dev). Never silent production fallback.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pke.product.auth import AUTH_MODE_SESSION, AuthError, AuthUser
from pke.product.passwords import hash_password, hash_session_token, verify_password

_LOG = logging.getLogger("pke.product.auth")

DEFAULT_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,40}$")


@dataclass(frozen=True)
class RegisteredUser:
    id: str
    username: str
    display_name: str


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    user_id: str
    token: str
    expires_at: str


class ProductAuthService:
    """Canonical Product identity + session authority (schema 1.2+)."""

    def __init__(
        self,
        store: object,
        *,
        session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._ttl = max(60, int(session_ttl_seconds))
        self._clock = clock or (lambda: datetime.now(UTC))

    def register(self, username: str, password: str, display_name: str | None = None) -> RegisteredUser:
        username_n = username.strip().lower()
        if not _USERNAME_RE.match(username_n):
            raise AuthError("INVALID_CREDENTIALS", "Usuário ou senha inválidos.", status_code=422)
        if len(password) < 8 or len(password) > 200:
            raise AuthError("INVALID_CREDENTIALS", "Usuário ou senha inválidos.", status_code=422)
        if self._store.get_user_by_username(username_n) is not None:
            # Avoid account enumeration detail
            raise AuthError("INVALID_CREDENTIALS", "Usuário ou senha inválidos.", status_code=422)
        pwd_hash = hash_password(password)
        display = (display_name or username_n).strip()[:80] or username_n
        user = self._store.create_user(username_n, pwd_hash, display)
        self._store.record_auth_event(user.id, "register", "ok")
        _LOG.info("auth_event=register user_id=%s outcome=ok", user.id)
        return RegisteredUser(id=user.id, username=user.username, display_name=user.display_name)

    def login(self, username: str, password: str) -> SessionInfo:
        username_n = username.strip().lower()
        user = self._store.get_user_by_username(username_n)
        if user is None or not verify_password(password, user.password_hash):
            self._store.record_auth_event(
                user.id if user else None, "login_failure", "invalid_credentials"
            )
            _LOG.info("auth_event=login_failure username=%s", username_n)
            raise AuthError("UNAUTHENTICATED", "Usuário ou senha inválidos.")
        return self._issue_session(user.id, event="login")

    def user_public(self, user_id: str) -> RegisteredUser | None:
        user = self._store.get_user_by_id(user_id)
        if user is None:
            return None
        return RegisteredUser(id=user.id, username=user.username, display_name=user.display_name)

    def logout(self, token: str | None) -> None:
        if not token:
            return
        token_hash = hash_session_token(token)
        session = self._store.get_session_by_token_hash(token_hash)
        if session is None:
            return
        self._store.revoke_session(session.id)
        self._store.record_auth_event(session.user_id, "logout", "ok")
        _LOG.info("auth_event=logout user_id=%s session_id=%s", session.user_id, session.id)

    def resolve_bearer(self, authorization: str | None) -> AuthUser:
        if not authorization:
            raise AuthError("UNAUTHENTICATED", "Credencial ausente ou inválida.")
        scheme, _, rest = authorization.partition(" ")
        if scheme.lower() != "bearer" or not rest.strip():
            raise AuthError("UNAUTHENTICATED", "Credencial ausente ou inválida.")
        token = rest.strip()
        if token.startswith("dev:"):
            raise AuthError("UNAUTHENTICATED", "Credencial ausente ou inválida.")
        token_hash = hash_session_token(token)
        session = self._store.get_session_by_token_hash(token_hash)
        now = self._clock()
        if session is None or session.revoked_at is not None:
            raise AuthError("UNAUTHENTICATED", "Sessão inválida ou expirada.")
        expires = datetime.fromisoformat(session.expires_at)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires <= now:
            self._store.revoke_session(session.id)
            self._store.record_auth_event(session.user_id, "session_expired", "expired")
            raise AuthError("UNAUTHENTICATED", "Sessão inválida ou expirada.")
        user = self._store.get_user_by_id(session.user_id)
        if user is None:
            raise AuthError("UNAUTHENTICATED", "Sessão inválida ou expirada.")
        return AuthUser(
            id=user.id,
            display_name=user.display_name,
            auth_mode=AUTH_MODE_SESSION,
            session_id=session.id,
            username=user.username,
        )

    def _issue_session(self, user_id: str, *, event: str) -> SessionInfo:
        token = secrets.token_urlsafe(32)
        token_hash = hash_session_token(token)
        now = self._clock()
        expires = now + timedelta(seconds=self._ttl)
        session = self._store.create_session(
            user_id=user_id,
            token_hash=token_hash,
            created_at=now.replace(microsecond=0).isoformat(),
            expires_at=expires.replace(microsecond=0).isoformat(),
        )
        self._store.record_auth_event(user_id, event, "ok")
        _LOG.info("auth_event=%s user_id=%s session_id=%s", event, user_id, session.id)
        return SessionInfo(
            session_id=session.id,
            user_id=user_id,
            token=token,
            expires_at=session.expires_at,
        )
