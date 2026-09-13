"""Append-only per-request stage logs.

File name = `{YmdHis}_{client_request_id}.log` (fallback id: interpreter request).
Enabled in PKE_AUTH_MODE=dev unless PKE_REQUEST_LOG=0.
Tests only write when PKE_REQUEST_LOG_DIR is set.

Truncation is explicit (never silent): truncated / original_size / logged_size.
A failure to write a stage must not abort the operation.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_BODY = 65_536


def _enabled() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("PKE_REQUEST_LOG_DIR"):
        return False
    flag = os.environ.get("PKE_REQUEST_LOG", "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    if flag in {"1", "true", "yes", "on"}:
        return True
    return os.environ.get("PKE_AUTH_MODE", "").strip().lower() == "dev"


def log_dir() -> Path:
    explicit = os.environ.get("PKE_REQUEST_LOG_DIR", "").strip()
    if explicit:
        return Path(explicit)
    product_db = os.environ.get("PKE_PRODUCT_DB", "").strip()
    if product_db:
        return Path(product_db).resolve().parent / "request-logs"
    return Path("data/request-logs")


def safe_file_id(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    cleaned = _SAFE.sub("_", text).strip("._-")
    return cleaned[:80] or None


def _path_for(folder: Path, name: str) -> Path:
    """Reuse `{YmdHis}_{id}.log` for later stages of the same request."""
    pattern = re.compile(rf"^\d{{14}}_{re.escape(name)}\.log$")
    existing = [path for path in folder.iterdir() if path.is_file() and pattern.match(path.name)]
    if existing:
        return max(existing, key=lambda path: path.stat().st_mtime)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return folder / f"{stamp}_{name}.log"


def append_stage(
    file_id: str | None,
    stage: str,
    body: str = "",
    **meta: object,
) -> Path | None:
    """Append one stage block. Returns the file path when written. Fail-safe."""
    try:
        return _append_stage_unsafe(file_id, stage, body, **meta)
    except Exception:
        return None


def _append_stage_unsafe(
    file_id: str | None,
    stage: str,
    body: str = "",
    **meta: object,
) -> Path | None:
    if not _enabled():
        return None
    name = safe_file_id(file_id)
    if not name:
        return None
    folder = log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = _path_for(folder, name)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    lines = [f"=== {stamp} stage={stage} ==="]
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    formatted = ""
    if text:
        formatted = _pretty(text)
        original_size = len(formatted)
        if original_size > _MAX_BODY:
            formatted = formatted[:_MAX_BODY]
            meta = {
                **meta,
                "truncated": True,
                "original_size": original_size,
                "logged_size": len(formatted),
            }
    for key, value in meta.items():
        if value is None or value == "":
            continue
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        lines.append(f"{key}: {rendered}")
    if formatted:
        lines.append("---")
        lines.append(formatted)
    lines.append("")
    path.open("a", encoding="utf-8").write("\n".join(lines) + "\n")
    return path


def dump_model(obj: object) -> object:
    """JSON-friendly dump for stage bodies."""
    if obj is None:
        return None
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump(mode="json", exclude_none=True)
    if isinstance(obj, (dict, list, str, int, float, bool)):
        return obj
    return str(obj)


def _pretty(text: str) -> str:
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
    return json.dumps(parsed, ensure_ascii=False, indent=2)
