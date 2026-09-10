from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val is None or str(val).strip() == "":
        return default
    return str(val).strip()


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

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jamescore.sqlite"

    @classmethod
    def from_env(cls) -> Settings:
        data = Path(_env("JAMESCORE_DATA_DIR", "./data")).resolve()
        timeout = float(_env("PKE_TIMEOUT_SECONDS", "60") or "60")
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
        )
