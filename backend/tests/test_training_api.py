"""REST endpoint tests for the training control / dashboard-recovery API.

Scope
-----
These endpoints were added for FE-8's refresh resilience: REST mirrors of
the existing WS control messages (stop/pause/resume/set_level) plus read
endpoints (``/timeseries``, ``/current_frame``, extended ``/status``) that
let the frontend repaint state on a page refresh without waiting for a
WebSocket reconnect.

Test style
----------
Uses the ``client`` fixture from ``conftest.py`` which installs a mocked
TrainingServiceWrapper (AsyncMock on the manager, no real SB3). That
intentionally keeps the tests fast — the real training loop is exercised
by ``test_trainer.py``. Here we assert only the REST surface contract:
routing, payload shape, state-broadcast fan-out, and boundary validation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


# --- GET /api/training/status ----------------------------------------------


def test_training_status_includes_extended_fields(client):
    """Status response must carry FE-8's extended fields even when idle."""
    resp = client.get("/api/training/status")
    assert resp.status_code == 200
    body = resp.json()
    # The contract FE-8 relies on for first paint.
    assert body["state"] == "stopped"
    assert body["current_step"] == 0
    assert body["current_episode"] == 0
    assert body["bot_level"] == 1
    assert body["experiment_id"] is None
    assert body["started_at"] is None


# --- POST /api/training/stop -----------------------------------------------


def test_training_stop_rest_calls_manager_with_force(client, app_instance):
    """REST Stop always sends force=True — matches the WS path guarantee.

    QA's top complaint pre-hotfix was a silent no-op at the protection
    threshold because the wrapper defaulted to force=False. A REST Stop
    button click is the same explicit intent — it must not silently drop.
    """
    manager = app_instance.state.training_service.manager
    manager.stop = AsyncMock(return_value={"stopped": True, "reason": "stopped"})

    resp = client.post("/api/training/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["result"]["stopped"] is True
    # force=True kw-only on the wrapper; verify it reached the manager.
    manager.stop.assert_awaited_once()
    _, kwargs = manager.stop.call_args
    assert kwargs == {"force": True}


# --- POST /api/training/pause ----------------------------------------------


def test_training_pause_rest_routes_to_manager_pause(client, app_instance):
    manager = app_instance.state.training_service.manager
    manager.pause = AsyncMock(return_value={"paused": True, "reason": "paused"})

    resp = client.post("/api/training/pause")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["result"]["paused"] is True
    manager.pause.assert_awaited_once()


# --- POST /api/training/resume ---------------------------------------------


def test_training_resume_rest_routes_to_manager_resume(client, app_instance):
    manager = app_instance.state.training_service.manager
    manager.resume = AsyncMock(return_value={"resumed": True, "reason": "unpaused"})

    resp = client.post("/api/training/resume")
    assert resp.status_code == 200
    assert resp.json()["result"]["resumed"] is True
    manager.resume.assert_awaited_once()


def test_training_resume_rest_returns_409_when_no_checkpoint(client, app_instance):
    """resume-from-stopped without a checkpoint must surface as 409, not 500.

    FE-8 wants to show an actionable error ("No saved session to resume")
    instead of a generic server-error toast. 409 Conflict is the right
    shape: the request is valid but the current state doesn't permit it.
    """
    manager = app_instance.state.training_service.manager
    manager.resume = AsyncMock(side_effect=FileNotFoundError("No checkpoint found"))

    resp = client.post("/api/training/resume")
    assert resp.status_code == 409
    assert "No checkpoint" in resp.json()["detail"]


# --- GET/PATCH /api/training/level -----------------------------------------


def test_training_level_get_returns_current(client, app_instance):
    manager = app_instance.state.training_service.manager
    manager._bot_level = 3
    # The fixture installs a hardcoded status() lambda; override for this test.
    app_instance.state.training_service.status = lambda: {
        "state": "stopped", "current_step": 0, "current_episode": 0,
        "experiment_id": None, "bot_level": 3, "started_at": None,
    }

    resp = client.get("/api/training/level")
    assert resp.status_code == 200
    assert resp.json() == {"level": 3}


def test_training_level_patch_updates_and_echoes(client, app_instance):
    """PATCH succeeds and the body carries the new level back."""
    manager = app_instance.state.training_service.manager
    manager.set_bot_level = MagicMock()

    resp = client.patch("/api/training/level", json={"level": 4})
    assert resp.status_code == 200
    assert resp.json() == {"level": 4}
    manager.set_bot_level.assert_called_once_with(4)


def test_training_level_patch_rejects_out_of_range(client):
    resp = client.patch("/api/training/level", json={"level": 99})
    assert resp.status_code == 422  # pydantic schema rejects

    resp_low = client.patch("/api/training/level", json={"level": 0})
    assert resp_low.status_code == 422


# --- GET /api/training/timeseries ------------------------------------------


def test_training_timeseries_empty(client):
    """No persisted metrics → empty points list, not 404."""
    resp = client.get("/api/training/timeseries?metric=reward&limit=50")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric"] == "reward"
    assert body["points"] == []


def test_training_timeseries_with_data(client, app_instance):
    """After records are inserted, timeseries returns them newest-last.

    ``recent_points`` on the production MetricsService fetches newest-first
    from Mongo and reverses to newest-last — the fake in conftest mirrors
    that ordering so this test pins the wire contract.
    """
    import asyncio

    svc = app_instance.state.metrics_service
    # Seed in out-of-order step order to prove sort, not insertion order,
    # drives the response.
    rows = [
        {"step": 300, "mean_reward": 3.0, "win_rate": 0.3},
        {"step": 100, "mean_reward": 1.0, "win_rate": 0.1},
        {"step": 200, "mean_reward": 2.0, "win_rate": 0.2},
    ]
    loop = asyncio.new_event_loop()
    try:
        for row in rows:
            loop.run_until_complete(svc.record("exp-ts-1", row))
    finally:
        loop.close()

    resp = client.get("/api/training/timeseries?metric=reward&limit=10")
    assert resp.status_code == 200
    points = resp.json()["points"]
    # newest-last — i.e. ascending by step
    assert [p["step"] for p in points] == [100, 200, 300]
    assert points[-1]["value"] == 3.0
    # Every point must carry a timestamp so the FE can render time-based
    # tooltips and reconcile against the local WS clock. Timestamp is the
    # server-stamped ISO-8601 UTC string, never null once persisted.
    for p in points:
        assert "timestamp" in p
        assert p["timestamp"] is not None
        # Parseable as ISO-8601 (fromisoformat accepts +00:00 / naive / offset).
        from datetime import datetime as _dt
        _dt.fromisoformat(p["timestamp"])


def test_training_timeseries_default_limit_is_1000(client, app_instance):
    """Unspecified limit must default to 1000 (product spec v0.2.4)."""
    import asyncio

    svc = app_instance.state.metrics_service
    loop = asyncio.new_event_loop()
    try:
        # Seed 3 rows — fewer than the cap — so we can verify the endpoint
        # accepts the no-limit default without 422ing.
        for step in (100, 200, 300):
            loop.run_until_complete(svc.record(
                "exp-default-limit",
                {"step": step, "mean_reward": float(step)},
            ))
    finally:
        loop.close()

    resp = client.get("/api/training/timeseries?metric=reward")
    assert resp.status_code == 200
    # 3 seeded points come back; default didn't truncate them.
    assert len(resp.json()["points"]) == 3


def test_training_timeseries_rejects_unknown_metric(client):
    resp = client.get("/api/training/timeseries?metric=bogus&limit=50")
    assert resp.status_code == 400
    assert "Unknown metric" in resp.json()["detail"]


def test_training_timeseries_respects_limit_bounds(client):
    # limit=0 is below the declared minimum.
    assert client.get("/api/training/timeseries?metric=reward&limit=0").status_code == 422
    # 1001 used to be the ceiling; after the metrics-resolution bump
    # (MetricsCallback log_interval 100→256 → ~3900 points per 1M-step
    # run) the cap was raised to 10000 so a full run fits in one call.
    assert client.get("/api/training/timeseries?metric=reward&limit=1001").status_code == 200
    assert client.get("/api/training/timeseries?metric=reward&limit=10000").status_code == 200
    # 10001 is now the pathological-response guard.
    assert client.get("/api/training/timeseries?metric=reward&limit=10001").status_code == 422


# --- GET /api/training/current_frame ---------------------------------------


def test_current_frame_returns_404_when_none_cached(client):
    """No training ever ran → 404 (not a misleading null body)."""
    resp = client.get("/api/training/current_frame")
    assert resp.status_code == 404


def test_current_frame_returns_cached_frame(client, app_instance):
    """When LiveFrameCallback has populated last_frame the endpoint surfaces it.

    The fixture installs ``last_frame = lambda: None``; overriding the
    lambda simulates a live training session mid-demo game. The exact
    payload shape mirrors ``_serialize_state`` in backend/rl/callbacks.py.
    """
    sample = {
        "player1": {"x": 100, "y": 200, "vx": 0, "vy": 0,
                    "is_jumping": False, "is_diving": False, "is_power_hitting": False},
        "player2": {"x": 300, "y": 200, "vx": 0, "vy": 0,
                    "is_jumping": False, "is_diving": False, "is_power_hitting": False},
        "ball": {"x": 216, "y": 100, "vx": 0, "vy": 1, "rotation": 0.0},
        "score1": 6, "score2": 9, "frame": 4500,
    }
    app_instance.state.training_service.last_frame = lambda: sample

    resp = client.get("/api/training/current_frame")
    assert resp.status_code == 200
    assert resp.json() == sample


# --- Broadcast fan-out contract --------------------------------------------


def test_stop_rest_broadcasts_training_status(client, app_instance):
    """The REST Stop click must notify open WS dashboards, not just the caller.

    Matches the WS handler's broadcast contract from BE-6 hotfix: every
    live dashboard has to see the state flip, not only the browser that
    hit the REST endpoint.
    """
    manager = app_instance.state.training_service.manager
    manager.stop = AsyncMock(return_value={"stopped": True, "reason": "stopped"})

    ws_manager = app_instance.state.ws_manager
    ws_manager.broadcast = AsyncMock()

    resp = client.post("/api/training/stop")
    assert resp.status_code == 200
    ws_manager.broadcast.assert_awaited()
    sent = ws_manager.broadcast.await_args.args[0]
    assert sent["type"] == "training:status"
    # The broadcast payload must carry the resulting state, not a hardcoded label.
    assert sent["payload"]["state"] == "stopped"


def test_level_patch_broadcasts_training_status(client, app_instance):
    manager = app_instance.state.training_service.manager
    manager.set_bot_level = MagicMock()

    ws_manager = app_instance.state.ws_manager
    ws_manager.broadcast = AsyncMock()

    resp = client.patch("/api/training/level", json={"level": 2})
    assert resp.status_code == 200
    ws_manager.broadcast.assert_awaited()
    sent = ws_manager.broadcast.await_args.args[0]
    assert sent["type"] == "training:status"
    assert sent["payload"]["bot_level"] == 2
