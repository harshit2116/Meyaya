"""Structured logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog


def configure_logging() -> None:
    """Configure stdlib logging and structlog."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    telemetry = logging.getLogger("meyaya.telemetry")
    if not telemetry.handlers:
        try:
            directory = Path("logs")
            directory.mkdir(exist_ok=True)
            handler = RotatingFileHandler(
                directory / "telemetry.jsonl", maxBytes=5_000_000,
                backupCount=3, encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            telemetry.addHandler(handler)
            telemetry.setLevel(logging.INFO)
        except OSError:
            logging.getLogger(__name__).warning("File logging unavailable; using console telemetry")
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )
