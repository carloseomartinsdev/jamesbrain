"""python -m pke.product"""

from __future__ import annotations

import os

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from pke.product.api.v1.app import create_app


def main() -> None:
    host = os.environ.get("PKE_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("PKE_HTTP_PORT", "8000"))
    log_config = LOGGING_CONFIG.copy()
    log_config["loggers"]["pke"] = {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
    uvicorn.run(create_app(), host=host, port=port, log_config=log_config)


if __name__ == "__main__":
    main()
