"""Identificadores persistentes (ULID)."""

from __future__ import annotations

import secrets
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    """Gera um ULID Crockford Base32 (26 caracteres), ordenável por tempo."""
    timestamp_ms = int(time.time() * 1000)
    randomness = secrets.randbits(80)
    value = (timestamp_ms << 80) | randomness
    chars: list[str] = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))
