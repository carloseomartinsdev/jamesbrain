from __future__ import annotations

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from jamescore.api.app import create_app
from jamescore.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    log_config = LOGGING_CONFIG.copy()
    log_config["loggers"]["jamescore"] = {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
    uvicorn.run(create_app(settings), host=settings.http_host, port=settings.http_port, log_config=log_config)


if __name__ == "__main__":
    main()
