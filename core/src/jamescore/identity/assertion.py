"""Signed Portal → jamesCore identity assertion. Body user_id is never identity."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from jamescore.identity.principal import AuthenticatedPrincipal
from jamescore.settings import Settings


class IdentityError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def mint_assertion(
    settings: Settings,
    *,
    sub: str,
    display_name: str | None = None,
    ttl_seconds: int = 120,
) -> str:
    if not settings.assertion_secret:
        raise IdentityError("IDENTITY_MISCONFIGURED", "Assertion secret is not configured.")
    now = int(time.time())
    payload = {
        "iss": settings.assertion_iss,
        "aud": settings.assertion_aud,
        "sub": str(sub),
        "name": display_name,
        "iat": now,
        "exp": now + ttl_seconds,
        "nonce": secrets.token_hex(8),
    }
    body = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = _b64url(
        hmac.new(settings.assertion_secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
    return f"jc1.{body}.{sig}"


def parse_bearer(header: str | None) -> str | None:
    if not header:
        return None
    parts = header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def verify_assertion(settings: Settings, token: str) -> AuthenticatedPrincipal:
    if not settings.assertion_secret:
        raise IdentityError("IDENTITY_MISCONFIGURED", "Assertion secret is not configured.")
    bits = token.split(".")
    if len(bits) != 3 or bits[0] != "jc1":
        raise IdentityError("IDENTITY_INVALID", "Malformed identity assertion.")
    body, sig = bits[1], bits[2]
    expected = _b64url(
        hmac.new(settings.assertion_secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(sig, expected):
        raise IdentityError("IDENTITY_INVALID", "Identity assertion signature failed.")
    try:
        payload: dict[str, Any] = json.loads(_b64url_decode(body).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise IdentityError("IDENTITY_INVALID", "Identity assertion payload is not JSON.") from exc
    now = int(time.time())
    if payload.get("iss") != settings.assertion_iss:
        raise IdentityError("IDENTITY_INVALID", "Identity assertion issuer mismatch.")
    if payload.get("aud") != settings.assertion_aud:
        raise IdentityError("IDENTITY_INVALID", "Identity assertion audience mismatch.")
    exp = int(payload.get("exp") or 0)
    if exp < now:
        raise IdentityError("IDENTITY_EXPIRED", "Identity assertion expired.")
    sub = str(payload.get("sub") or "").strip()
    if not sub:
        raise IdentityError("IDENTITY_INVALID", "Identity assertion has no subject.")
    name = payload.get("name")
    display = str(name).strip() if isinstance(name, str) and name.strip() else None
    return AuthenticatedPrincipal(sub=sub, display_name=display, issuer=str(payload.get("iss") or ""))
