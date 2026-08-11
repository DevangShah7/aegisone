"""Structured logging configuration.

Outputs JSON in production and a more readable format in development.
Every log record carries the request id (set by RequestIdMiddleware)
and a stable logger name so backend / dashboard / Android logs can be
correlated in a single incident.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from app.core.config import settings


class _JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for structured logs."""

    # Standard LogRecord attributes to skip when serializing `extra`.
    _STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys())

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Promote any custom extras.
        for key, value in record.__dict__.items():
            if key in self._STANDARD_ATTRS or key.startswith("_"):
                continue
            if key in payload:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with JSON or human format based on environment."""

    root = logging.getLogger()
    # Idempotent: clear existing handlers to avoid duplicate output on reload.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    if settings.environment == "prod":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] [req=%(request_id)s] %(message)s",
                defaults={"request_id": "-"},
            )
        )

    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Tame noisy libraries.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
