from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val is None or str(val).strip() == "":
        return default
    return str(val).strip()


def _hydrate_presenter_secrets() -> None:
    """Fill missing Presenter/DeepSeek settings from PKE .env without clobbering."""
    pke_env = Path(__file__).resolve().parents[3] / "pke" / ".env"
    if not pke_env.is_file():
        return
    try:
        lines = pke_env.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    wanted = {
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_BASE_URL",
        "PRESENTER_API_KEY",
        "PRESENTER_MODEL",
        "PRESENTER_BASE_URL",
    }
    found: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in wanted:
            continue
        found[key] = value.strip().strip('"').strip("'")
    for key, value in found.items():
        if os.environ.get(key, "").strip():
            continue
        if value:
            os.environ[key] = value


def _bool_env(key: str, default: bool = True) -> bool:
    raw = _env(key, "1" if default else "0").casefold()
    return raw not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    http_host: str
    http_port: int
    data_dir: Path
    assertion_secret: str
    assertion_iss: str
    assertion_aud: str
    pke_api_url: str
    pke_timeout_seconds: float
    pke_auth_prefix: str
    presenter_enabled: bool = True
    presenter_timeout_seconds: float = 8.0
    presenter_api_key: str = ""
    presenter_base_url: str = "https://api.deepseek.com"
    presenter_model: str = "deepseek-chat"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jamescore.sqlite"

    @classmethod
    def from_env(cls) -> Settings:
        _hydrate_presenter_secrets()
        data = Path(_env("JAMESCORE_DATA_DIR", "./data")).resolve()
        timeout = float(_env("PKE_TIMEOUT_SECONDS", "60") or "60")
        presenter_timeout = float(_env("PRESENTER_TIMEOUT_SECONDS", "8") or "8")
        return cls(
            http_host=_env("JAMESCORE_HTTP_HOST", "127.0.0.1"),
            http_port=int(_env("JAMESCORE_HTTP_PORT", "8010") or "8010"),
            data_dir=data,
            assertion_secret=_env("JAMESCORE_ASSERTION_SECRET", ""),
            assertion_iss=_env("JAMESCORE_ASSERTION_ISS", "james-portal"),
            assertion_aud=_env("JAMESCORE_ASSERTION_AUD", "jamescore"),
            pke_api_url=_env("PKE_API_URL", "http://127.0.0.1:8008").rstrip("/"),
            pke_timeout_seconds=timeout if timeout > 0 else 60.0,
            pke_auth_prefix=_env("PKE_AUTH_PREFIX", "dev:james-"),
            presenter_enabled=_bool_env("PRESENTER_ENABLED", True),
            presenter_timeout_seconds=presenter_timeout if presenter_timeout > 0 else 8.0,
            presenter_api_key=_env("PRESENTER_API_KEY") or _env("DEEPSEEK_API_KEY", ""),
            presenter_base_url=(
                _env("PRESENTER_BASE_URL") or _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            ).rstrip("/"),
            presenter_model=_env("PRESENTER_MODEL") or _env("DEEPSEEK_MODEL") or "deepseek-chat",
        )
