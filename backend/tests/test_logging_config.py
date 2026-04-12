"""Tests for JSON logging + correlation-id plumbing."""

from __future__ import annotations

import io
import json
import logging

import pytest

from backend.app.logging_config import (
    CorrelationIdFilter,
    JSONFormatter,
    configure_logging,
    correlation_id_var,
    new_correlation_id,
    process_uptime_seconds,
)


# --- JSONFormatter -----------------------------------------------------------


def _format(record_kwargs: dict | None = None, *, formatter: JSONFormatter | None = None) -> dict:
    formatter = formatter or JSONFormatter(service="test")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="/src/app.py",
        lineno=42,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    for k, v in (record_kwargs or {}).items():
        setattr(record, k, v)
    return json.loads(formatter.format(record))


def test_json_formatter_emits_required_fields():
    out = _format()
    assert out["level"] == "INFO"
    assert out["logger"] == "test.logger"
    assert out["msg"] == "hello world"
    assert out["service"] == "test"
    assert out["line"] == 42
    assert "ts" in out
    # correlation_id defaults to "-" when no filter has run
    assert out["correlation_id"] == "-"


def test_json_formatter_includes_correlation_id_when_present():
    out = _format({"correlation_id": "abc123"})
    assert out["correlation_id"] == "abc123"


def test_json_formatter_merges_extra_fields():
    out = _format({"user_id": 17, "route": "/api/games"})
    assert out["user_id"] == 17
    assert out["route"] == "/api/games"


def test_json_formatter_stringifies_unserializable_extras():
    class Unjsonable:
        def __repr__(self):
            return "<un-jsonable>"

    out = _format({"thing": Unjsonable()})
    assert out["thing"] == "<un-jsonable>"


def test_json_formatter_serializes_exc_info():
    formatter = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="t", level=logging.ERROR, pathname="p", lineno=1,
            msg="fail", args=(), exc_info=sys.exc_info(),
        )
    out = json.loads(formatter.format(record))
    assert "exc_info" in out
    assert "ValueError: boom" in out["exc_info"]


# --- CorrelationIdFilter -----------------------------------------------------


def test_correlation_filter_injects_current_contextvar():
    f = CorrelationIdFilter()
    record = logging.LogRecord("t", logging.INFO, "p", 1, "m", (), None)
    token = correlation_id_var.set("cid-xyz")
    try:
        assert f.filter(record) is True
        assert record.correlation_id == "cid-xyz"
    finally:
        correlation_id_var.reset(token)


def test_correlation_filter_defaults_to_dash_when_unset():
    f = CorrelationIdFilter()
    record = logging.LogRecord("t", logging.INFO, "p", 1, "m", (), None)
    f.filter(record)
    assert record.correlation_id == "-"


# --- configure_logging (integration) ----------------------------------------


def test_configure_logging_replaces_its_own_handlers_idempotently():
    buf1 = io.StringIO()
    configure_logging(stream=buf1, service="svc-1", level="INFO")
    root = logging.getLogger()
    ours_before = [h for h in root.handlers if getattr(h, "_pikachu_json", False)]
    assert len(ours_before) == 1

    # Call again with a different stream; our previous handler should be dropped
    buf2 = io.StringIO()
    configure_logging(stream=buf2, service="svc-2", level="INFO")
    ours_after = [h for h in root.handlers if getattr(h, "_pikachu_json", False)]
    assert len(ours_after) == 1
    assert ours_after[0] is not ours_before[0]


def test_configured_logger_emits_json_with_correlation_id(caplog):
    buf = io.StringIO()
    configure_logging(stream=buf, service="svc-test", level="INFO")
    token = correlation_id_var.set("req-42")
    try:
        logging.getLogger("be3.test").info("ready", extra={"phase": "ready"})
    finally:
        correlation_id_var.reset(token)

    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["msg"] == "ready"
    assert payload["correlation_id"] == "req-42"
    assert payload["phase"] == "ready"
    assert payload["service"] == "svc-test"


# --- new_correlation_id ------------------------------------------------------


def test_new_correlation_id_is_unique_and_hex():
    a, b = new_correlation_id(), new_correlation_id()
    assert a != b
    assert len(a) == 32
    int(a, 16)  # parseable as hex


# --- process_uptime_seconds --------------------------------------------------


def test_process_uptime_handles_missing_start():
    assert process_uptime_seconds(None) == 0.0


def test_process_uptime_is_non_negative(monkeypatch):
    import time as _t

    monkeypatch.setattr(_t, "monotonic", lambda: 100.0)
    # started later than "now" (clock skew) should clamp to 0
    assert process_uptime_seconds(200.0) == 0.0
