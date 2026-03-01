from __future__ import annotations

import logging
import logging.config
import os
import sys


def configure_logging() -> None:
    """Set up structured JSON logging for production, pretty logging for development."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    is_dev = os.getenv("APP_ENV", "development") == "development"

    if is_dev:
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        handlers: dict = {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "pretty",
            }
        }
        formatters = {
            "pretty": {"format": fmt, "datefmt": "%H:%M:%S"},
        }
    else:
        # JSON structured logging for production
        try:
            import structlog

            structlog.configure(
                processors=[
                    structlog.contextvars.merge_contextvars,
                    structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.JSONRenderer(),
                ],
                wrapper_class=structlog.make_filtering_bound_logger(
                    logging.getLevelName(log_level)
                ),
                logger_factory=structlog.PrintLoggerFactory(sys.stdout),
            )
            logging.basicConfig(level=log_level, stream=sys.stdout)
            return
        except ImportError:
            pass

        fmt_json = "%(asctime)s %(levelname)s %(name)s %(message)s"
        handlers = {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json",
            }
        }
        formatters = {
            "json": {"format": fmt_json},
        }

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": formatters,
            "handlers": handlers,
            "root": {"level": log_level, "handlers": list(handlers.keys())},
            "loggers": {
                "uvicorn": {"propagate": True},
                "uvicorn.access": {"propagate": True},
                "langchain": {"level": "WARNING", "propagate": True},
                "langgraph": {"level": "INFO", "propagate": True},
                "httpx": {"level": "WARNING", "propagate": True},
            },
        }
    )
