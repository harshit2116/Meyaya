"""Structured logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog


class DiscordRateLimitHandler(logging.Handler):
    """Count discord.py's internally retried 429s without storing URLs."""
    def emit(self, record):
        message = record.getMessage().lower()
        if 'rate limited' in message or ('429' in message and 'retry' in message):
            from bot.logging.telemetry import event
            event('discord_rate_limit')


def configure_logging() -> None:
    """Configure stdlib logging and structlog."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    discord_http = logging.getLogger("discord.http")
    if not any(isinstance(handler, DiscordRateLimitHandler) for handler in discord_http.handlers):
        discord_http.addHandler(DiscordRateLimitHandler(level=logging.WARNING))
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
