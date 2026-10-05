"""Logging setup."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(app: Flask) -> None:
    level = getattr(logging, app.config["LOG_LEVEL"].upper(), logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)

    app.logger.handlers.clear()
    app.logger.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    app.logger.addHandler(console)

    log_file = app.config.get("LOG_FILE")
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=10, encoding="utf-8")
        file_handler.setFormatter(formatter)
        app.logger.addHandler(file_handler)
