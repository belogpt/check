import logging
import sys
from logging.config import dictConfig


def setup_logging() -> None:
    """
    Configure application logging so that our own loggers
    emit structured messages alongside uvicorn logs.
    """
    if logging.getLogger().handlers:
        # Respect existing configuration (e.g., when uvicorn provides it).
        logging.getLogger().setLevel(logging.INFO)
        return

    dictConfig(
        {
            "version": 1,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "default",
                    "level": "INFO",
                }
            },
            "root": {"level": "INFO", "handlers": ["console"]},
            "disable_existing_loggers": False,
        }
    )
