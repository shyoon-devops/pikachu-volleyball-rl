"""Tests for /api/health, /api/health/live, /api/health/ready."""

from __future__ import annotations

from unittest.mock import AsyncMock


# --- /api/health/live --------------------------------------------------------


def test_live_endpoint_returns_200_without_dependency_checks(client, monkeypatch):
    """Liveness must not touch mongo — if it did, it would restart a pod when
    the database is just temporarily unavailable."""
    # Make mongo ping fail; /live should still be green because it doesn't call it.
    app = client.app
    app.state.mongo_client.admin.command = AsyncMock(side_effect=RuntimeError("down"))

    r = client.get("/api/health/live")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "live"
    assert "uptime_seconds" in body
    assert body["uptime_seconds"] >= 0.0


def test_live_endpoint_reports_uptime_after_start(client):
    app = client.app
    # Simulate a process that's been up for a while
    import time

    app.state.started_at_monotonic = time.monotonic() - 5.0
    r = client.get("/api/health/live")
    assert r.status_code == 200
    assert r.json()["uptime_seconds"] >= 5.0


# --- /api/health/ready -------------------------------------------------------


def test_ready_endpoint_returns_200_when_healthy(client):
    r = client.get("/api/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "uptime_seconds" in body
    assert set(body["checks"].keys()) == {"mongo", "disk", "training", "queues"}


def test_ready_endpoint_returns_503_when_mongo_down(client):
    client.app.state.mongo_client.admin.command = AsyncMock(
        side_effect=RuntimeError("connection refused")
    )
    r = client.get("/api/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["mongo"]["ok"] is False


# --- /api/health (backward compat) -------------------------------------------


def test_health_endpoint_has_same_shape_as_ready(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "uptime_seconds" in body
    assert "checks" in body


def test_health_endpoint_returns_503_when_mongo_down(client):
    client.app.state.mongo_client.admin.command = AsyncMock(
        side_effect=RuntimeError("down")
    )
    r = client.get("/api/health")
    assert r.status_code == 503


# --- Correlation ID middleware ----------------------------------------------


def test_correlation_id_echoed_when_client_provides_one(client):
    r = client.get("/api/health/live", headers={"X-Request-ID": "client-provided-abc"})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == "client-provided-abc"


def test_correlation_id_generated_when_client_omits(client):
    r = client.get("/api/health/live")
    assert r.status_code == 200
    cid = r.headers.get("X-Request-ID")
    assert cid is not None
    # Should be a 32-char hex string from uuid4
    assert len(cid) == 32
    int(cid, 16)


def test_correlation_id_overlong_input_is_replaced(client):
    # 200 chars — above our 128-char bound; middleware should reject and regenerate
    overlong = "a" * 200
    r = client.get("/api/health/live", headers={"X-Request-ID": overlong})
    assert r.status_code == 200
    cid = r.headers.get("X-Request-ID")
    assert cid != overlong
    assert len(cid) == 32
