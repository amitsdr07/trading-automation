# logging_config.py
from __future__ import annotations
import logging
import logging.config

def configure_logging(level: str = "INFO", log_file: str | None = None) -> logging.Logger:
    """Configure console + optional file logging. Returns a logger 'ats.cli'."""
    # Try RichHandler for nicer console logs
    try:
        import rich  # noqa: F401
        console_handler = {
            "class": "rich.logging.RichHandler",
            "level": level,
            "formatter": "rich",
            "rich_tracebacks": True,
            "markup": True,
        }
        rich_formatter = {"format": "%(message)s"}
    except Exception:
        console_handler = {
            "class": "logging.StreamHandler",
            "level": level,
            "formatter": "plain",
        }
        rich_formatter = {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}

    handlers = {"console": console_handler}
    root_handlers = ["console"]

    if log_file:
        handlers["file"] = {
            "class": "logging.FileHandler",
            "level": level,
            "formatter": "plain",
            "filename": log_file,
            "encoding": "utf-8",
        }
        root_handlers.append("file")

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
            "rich": rich_formatter,
        },
        "handlers": handlers,
        "loggers": {
            "ats.cli": {"level": level, "handlers": root_handlers, "propagate": False},
            "": {"level": level, "handlers": root_handlers},  # root
        },
    }

    try:
        logging.config.dictConfig(config)
    except Exception:
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    return logging.getLogger("ats.cli")
