"""JSON structured logging + correlation-id plumbing.

Design notes:
- Named ``logging_config`` rather than ``logging`` so we never shadow the
  stdlib ``logging`` module from imports inside ``backend/app/**``.
- The correlation ID lives in a ``ContextVar`` so it is propagated across
  awaits without having to thread it through every call site. The
  CorrelationIdMiddleware sets this per-request; anywhere code calls
  ``logger.info(...)`` the filter pulls the current value in.
- Output is single-line JSON per record for easy ingestion by Loki/Promtail
  (see DevOps commit f863c11e). Multi-line tracebacks are serialized into
  the ``exc_info`` string field so one log line = one event.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Public context variable — set by middleware, read by the filter.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


def new_correlation_id() -> str:
    """Return a short-ish uuid4 hex string safe to use as an X-Request-ID."""
    return uuid.uuid4().hex


class CorrelationIdFilter(logging.Filter):
    """Attach the current correlation id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get()
        return True


# Fields that belong on every record but come from LogRecord defaults; we
# copy them out explicitly so the JSON output is deterministic.
_BASE_KEYS = (
    "name", "levelname", "pathname", "lineno", "funcName",
)


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log record.

    The resulting format is intentionally flat so it is trivial to query
    from Loki/Grafana:

        {"ts": "...", "level": "INFO", "logger": "...", "msg": "...",
         "correlation_id": "...", "path": "...", "line": N}
    """

    def __init__(self, *, service: str = "backend") -> None:
        super().__init__()
        self.service = service

    def _iso_ts(self, record: logging.LogRecord) -> str:
        # stdlib ``Formatter.formatTime`` uses ``time.strftime`` which does
        # not support ``%f``. Round-trip through ``datetime`` so we get
        # microsecond precision in a proper ISO-8601 UTC string.
        return (
            datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
        )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self._iso_ts(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "service": self.service,
            "path": record.pathname,
            "line": record.lineno,
            "func": record.funcName,
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        # Merge any extra fields set via logger.info("...", extra={...}).
        # Skip known LogRecord internals to avoid polluting the JSON.
        reserved = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "message", "module",
            "msecs", "msg", "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "thread", "threadName",
            "taskName", "correlation_id",
        }
        for key, value in record.__dict__.items():
            if key in reserved or key.startswith("_"):
                continue
            try:
                json.dumps(value)  # ensure serializable
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(
    *,
    level: str | int | None = None,
    service: str = "pikachu-backend",
    stream=None,
) -> None:
    """Install the JSON formatter + correlation-id filter on the root logger.

    Idempotent: safe to call multiple times (we replace any existing handlers
    installed by a prior call so reloads under uvicorn do not multiply them).
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()

    root = logging.getLogger()
    # Drop only our previous handlers (marked via attribute) so uvicorn's
    # default handlers installed before us keep working on restart.
    for h in list(root.handlers):
        if getattr(h, "_pikachu_json", False):
            root.removeHandler(h)

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JSONFormatter(service=service))
    handler.addFilter(CorrelationIdFilter())
    handler._pikachu_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)

    # Align uvicorn loggers so our handler is the one that emits their records.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True


def process_uptime_seconds(started_at: float | None) -> float:
    """Return monotonic uptime since started_at (or 0 if unset)."""
    if started_at is None:
        return 0.0
    return max(0.0, time.monotonic() - started_at)
