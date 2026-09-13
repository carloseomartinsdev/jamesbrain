"""Append presenter stages onto the same per-request log as PKE.

File name matches PKE: `{YmdHis}_{client_request_id}.log`.
Prefers PKE_REQUEST_LOG_DIR so jamesCore and PKE share one trace file.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_BODY = 65_536


def _flag_off(raw: str) -> bool:
    return raw.strip().lower() in {"0", "false", "no", "off"}


def _flag_on(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _enabled() -> bool:
    has_dir = bool(
        os.environ.get("PKE_REQUEST_LOG_DIR", "").strip()
        or os.environ.get("JAMESCORE_REQUEST_LOG_DIR", "").strip()
    )
    if os.environ.get("PYTEST_CURRENT_TEST") and not has_dir:
        return False
    for key in ("JAMESCORE_REQUEST_LOG", "PKE_REQUEST_LOG"):
        flag = os.environ.get(key, "")
        if _flag_off(flag):
            return False
        if _flag_on(flag):
            return True
    if os.environ.get("PKE_AUTH_MODE", "").strip().lower() == "dev":
        return True
    return _default_dir().is_dir()


def _default_dir() -> Path:
    explicit = os.environ.get("PKE_REQUEST_LOG_DIR", "").strip()
    if explicit:
        return Path(explicit)
    core_dir = os.environ.get("JAMESCORE_REQUEST_LOG_DIR", "").strip()
    if core_dir:
        return Path(core_dir)
    product_db = os.environ.get("PKE_PRODUCT_DB", "").strip()
    if product_db:
        return Path(product_db).resolve().parent / "request-logs"
    # James portal data used by start_pke_james.ps1 and the Logs UI.
    workspace = Path(__file__).resolve().parents[5]
    portal = workspace / "james" / "data" / "pke" / "request-logs"
    return portal


def log_dir() -> Path:
    return _default_dir()


def safe_file_id(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    cleaned = _SAFE.sub("_", text).strip("._-")
    return cleaned[:80] or None


def _path_for(folder: Path, name: str) -> Path:
    pattern = re.compile(rf"^\d{{14}}_{re.escape(name)}\.log$")
    existing = [path for path in folder.iterdir() if path.is_file() and pattern.match(path.name)]
    if existing:
        return max(existing, key=lambda path: path.stat().st_mtime)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return folder / f"{stamp}_{name}.log"


def append_stage(
    file_id: str | None,
    stage: str,
    body: object = "",
    **meta: object,
) -> Path | None:
    try:
        return _append_stage_unsafe(file_id, stage, body, **meta)
    except Exception:
        return None


def _append_stage_unsafe(
    file_id: str | None,
    stage: str,
    body: object = "",
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


def _pretty(text: str) -> str:
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
    return json.dumps(parsed, ensure_ascii=False, indent=2)
