from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("jamescore")


def log_turn(kind: str, **fields: Any) -> None:
    parts = " ".join(f"{k}={v}" for k, v in fields.items())
    log.info("jamescore %s %s", kind, parts)
