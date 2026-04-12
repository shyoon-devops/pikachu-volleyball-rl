"""Error handling and logging tests for REST endpoints.

Each endpoint must:
  1. Re-raise FastAPI HTTPExceptions unchanged (status code preserved).
  2. Convert unhandled exceptions into a 500 with a structured body.
  3. Log the failure at ERROR level with a traceback.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock


def test_games_service_crash_returns_500_and_logs(client, app_instance, caplog):
    """If GameService.get_games raises unexpectedly, return 500 (not 200/422)."""
    original = app_instance.state.game_service.get_games
    app_instance.state.game_service.get_games = AsyncMock(
        side_effect=RuntimeError("mongo gone")
    )
    try:
        with caplog.at_level(logging.ERROR, logger="backend.app.api.routes"):
            resp = client.get("/api/games")
        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"]["code"] == "internal_error"
        assert body["detail"]["endpoint"] == "list_games"
        # Must have logged with stack info
        assert any("Unhandled error in endpoint list_games" in r.message for r in caplog.records)
    finally:
        app_instance.state.game_service.get_games = original


def test_game_not_found_preserves_404(client, app_instance):
    """HTTPException (404) must pass through the guard unchanged."""
    resp = client.get("/api/games/does-not-exist")
    assert resp.status_code == 404


def test_games_service_missing_returns_503(client, app_instance):
    """When the service is uninitialized, list_games returns 503, not 500."""
    original = app_instance.state.game_service
    app_instance.state.game_service = None
    try:
        resp = client.get("/api/games")
        assert resp.status_code == 503
    finally:
        app_instance.state.game_service = original


def test_get_replay_tolerates_game_lookup_failure(client, app_instance, caplog):
    """A failure in get_game_by_game_id must not break the replay response."""
    # Force load_replay to return frames and get_game_by_game_id to raise.
    app_instance.state.replay_service.load_replay = AsyncMock(
        return_value=[{"frame": 1}]
    )
    app_instance.state.game_service.get_game_by_game_id = AsyncMock(
        side_effect=RuntimeError("mongo transient")
    )
    with caplog.at_level(logging.ERROR, logger="backend.app.api.routes"):
        resp = client.get("/api/replays/abc-123")
    assert resp.status_code == 200
    body = resp.json()
    assert body["frames"] == [{"frame": 1}]
    assert body["game"] is None
    assert any("failed to fetch linked game record" in r.message for r in caplog.records)


def test_evaluation_run_semaphore_conflict(client, app_instance):
    """When semaphore is locked, return 409 (not 500)."""
    from backend.app.api import routes

    # Acquire and release only after the request is issued.
    assert routes._eval_semaphore.locked() is False
    # Force the semaphore into a locked state for the duration of this call.
    original_locked = routes._eval_semaphore.locked
    routes._eval_semaphore.locked = lambda: True
    try:
        resp = client.post(
            "/api/evaluation/run",
            json={"model_path": "test.zip", "bot_level": 1, "n_games": 10},
        )
        assert resp.status_code == 409
    finally:
        routes._eval_semaphore.locked = original_locked


def test_training_status_handles_service_crash(client, app_instance, caplog):
    """A crashing training_service.status() returns 500, not a raw stack trace."""
    app_instance.state.training_service.status = MagicMock(
        side_effect=RuntimeError("manager crashed")
    )
    with caplog.at_level(logging.ERROR, logger="backend.app.api.routes"):
        resp = client.get("/api/training/status")
    assert resp.status_code == 500
    assert resp.json()["detail"]["endpoint"] == "training_status"


def test_list_models_scan_failure_returns_500(client, app_instance, monkeypatch, caplog):
    """OSError during directory scan must be logged and returned as 500."""
    import backend.app.api.routes as routes_mod

    class _FailingPath:
        def resolve(self):
            return self

        def __str__(self) -> str:
            return "/tmp/fake-models"

        def exists(self) -> bool:
            return True

        def rglob(self, _pattern):
            raise OSError("EIO")

    monkeypatch.setattr(routes_mod, "Path", lambda _p: _FailingPath())
    with caplog.at_level(logging.ERROR, logger="backend.app.api.routes"):
        resp = client.get("/api/models")
    assert resp.status_code == 500
    assert any("failed to scan model_dir" in r.message for r in caplog.records)
