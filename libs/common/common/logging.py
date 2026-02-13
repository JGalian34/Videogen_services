"""
Structured JSON logging configuration.

Call ``setup_logging()`` once at service startup.
"""

from __future__ import annotations

import logging
import sys

from pythonjsonlogger import jsonlogger

from common.config import LOG_LEVEL, LOG_FORMAT


class _CorrelationFilter(logging.Filter):
    """Inject correlation_id from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        from common.middleware.correlation import get_correlation_id

        record.correlation_id = get_correlation_id()  # type: ignore[attr-defined]
        return True


def setup_logging(service_name: str = "service") -> None:
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL.upper())

    handler = logging.StreamHandler(sys.stdout)

    if LOG_FORMAT == "json":
        fmt = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(correlation_id)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
    else:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s (%(correlation_id)s) %(message)s")

    handler.setFormatter(fmt)
    handler.addFilter(_CorrelationFilter())

    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("kafka").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logging.getLogger(service_name).info("Logging initialised", extra={"service": service_name})
