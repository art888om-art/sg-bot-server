"""Structured logging setup with structlog."""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.types import EventDict, Processor

from app.config import get_settings


def _drop_sensitive(logger: object, method_name: str, event_dict: EventDict) -> EventDict:
    """Strip values that look like tokens/secrets from log events."""
    sensitive_keys = {"bot_token", "jwt_secret", "password", "token", "secret", "authorization"}
    for key in list(event_dict.keys()):
        if key.lower() in sensitive_keys:
            event_dict[key] = "***"
    return event_dict


def configure_logging() -> None:
    """Configure structlog + stdlib logging once at startup."""
    settings = get_settings()
    level = getattr(logging, settings.log_level, logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _drop_sensitive,
    ]

    if settings.is_production:
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    log: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return log
