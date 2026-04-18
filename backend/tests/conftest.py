"""Shared test fixtures — mocks MongoDB so tests run without a live instance,
and provides RL/game fixtures for trainer/env tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

from backend.app.services.training_service import TrainingServiceWrapper
from backend.app.ws.manager import ConnectionManager


class FakeGameService:
    """In-memory stand-in for GameService."""

    def __init__(self) -> None:
        self._games: list[dict] = []

    async def save_game(self, record) -> str:
        doc = record.model_dump(by_alias=True, exclude_none=True)
        doc["_id"] = str(len(self._games))
        self._games.append(doc)
        return doc["_id"]

    async def get_games(self, page: int = 1, limit: int = 20):
        from backend.app.models.schemas import PaginatedResponse

        start = (page - 1) * limit
        sliced = self._games[start : start + limit]
        return PaginatedResponse(data=sliced, total=len(self._games), page=page, limit=limit)

    async def get_game(self, game_id: str):
        for g in self._games:
            if g.get("_id") == game_id:
                return g
        return None

    async def get_game_by_game_id(self, game_id: str):
        for g in self._games:
            if g.get("game_id") == game_id:
                return g
        return None


class FakeEvalService:
    # Sentinel: paths starting with this prefix pass the synchronous
    # preflight (validate_model_path returns OK) but fail inside the
    # background ``run`` call. Used by test_eval_async to exercise the
    # 202 → poll → failed lifecycle end-to-end without a real model on
    # disk. Regular test paths still 404 at preflight as before.
    _PASS_PREFLIGHT_PREFIX = "bgfail/"

    def validate_model_path(self, model_path: str):
        # Mirrors EvalServiceWrapper.validate_model_path so the async
        # run endpoint's pre-flight check rejects bad paths synchronously
        # against the test fake too. Without this the preflight would
        # short-circuit via the ``hasattr`` guard and security/traversal
        # tests would observe a 202 instead of the expected 404.
        if ".." in model_path or model_path.startswith("/"):
            raise FileNotFoundError(f"Invalid model path: {model_path}")
        if model_path.startswith(self._PASS_PREFLIGHT_PREFIX):
            return None  # preflight OK, background task will raise
        raise FileNotFoundError(f"Model not found: {model_path}")

    async def run(
        self,
        model_path: str,
        bot_level: int = 1,
        n_games: int = 50,
        *,
        progress_callback=None,
        training_title=None,
    ):
        if ".." in model_path or model_path.startswith("/"):
            raise FileNotFoundError(f"Invalid model path: {model_path}")
        raise FileNotFoundError(f"Model not found: {model_path}")

    async def get_results(self):
        return {"data": []}


class FakeReplayService:
    async def list_replays(self):
        return []

    async def load_replay(self, game_id: str):
        return []


class FakeMetricsService:
    """In-memory stand-in for MetricsService.

    Mirrors the real aggregation contract closely enough for endpoint tests
    without needing Mongo. Supports ``record`` (for push-loop tests) and
    ``aggregate`` (for endpoint tests); the aggregate implementation here
    is simplified — it just returns everything that was recorded, bucket
    selection happens at the caller's fidelity.
    """

    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(self, experiment_id: str, data: dict) -> None:
        from datetime import datetime, timezone

        doc = dict(data)
        doc["experiment_id"] = experiment_id
        doc["timestamp"] = datetime.now(timezone.utc)
        self.records.append(doc)

    async def aggregate(
        self,
        *,
        experiment_id: str | None = None,
        bucket: str = "1m",
        since=None,
        until=None,
    ) -> list[dict]:
        # Return a single synthetic bucket spanning everything recorded so
        # endpoint tests can assert shape without simulating $dateTrunc.
        matching = [
            r for r in self.records
            if experiment_id is None or r.get("experiment_id") == experiment_id
        ]
        if not matching:
            return []
        from datetime import timezone

        def _avg(field: str) -> float:
            vals = [r[field] for r in matching if field in r]
            return sum(vals) / len(vals) if vals else 0.0

        return [{
            "bucket_start": min(r["timestamp"] for r in matching).astimezone(timezone.utc),
            "count": len(matching),
            "step_max": max((r.get("step", 0) for r in matching), default=0),
            "avg_mean_reward": _avg("mean_reward"),
            "avg_win_rate": _avg("win_rate"),
            "avg_policy_loss": _avg("policy_loss"),
            "avg_value_loss": _avg("value_loss"),
        }]

    async def recent_points(
        self,
        *,
        field: str,
        limit: int = 100,
        experiment_id: str | None = None,
    ) -> list[dict]:
        """Mirror MetricsService.recent_points over in-memory records.

        Kept simple — the endpoint test only needs the projection + ordering
        contract, not an index-backed scan. Sorted newest-last to match the
        production shape so the test assertion is identical in both cases.
        """
        matching = [
            r for r in self.records
            if (experiment_id is None or r.get("experiment_id") == experiment_id)
            and field in r
        ]
        # Sort by step (the only monotonic-ish field records carry here).
        matching.sort(key=lambda r: r.get("step", 0))
        if len(matching) > limit:
            matching = matching[-limit:]
        out: list[dict] = []
        for r in matching:
            ts = r.get("timestamp")
            ts_iso = ts.isoformat() if ts is not None else None
            out.append({
                "step": r.get("step", 0),
                "value": r.get(field, 0.0),
                "timestamp": ts_iso,
            })
        return out


def _make_queue_mock(maxsize: int) -> MagicMock:
    """Build a queue mock that satisfies the health check's qsize/maxsize reads."""
    m = MagicMock()
    m.qsize = MagicMock(return_value=0)
    m.maxsize = maxsize
    return m


@asynccontextmanager
async def _test_lifespan(app):
    mongo_client = MagicMock()
    # Health check awaits `mongo_client.admin.command("ping")`.
    mongo_client.admin.command = AsyncMock(return_value={"ok": 1})
    app.state.mongo_client = mongo_client
    app.state.db = MagicMock()
    app.state.game_service = FakeGameService()
    app.state.metrics_service = FakeMetricsService()
    app.state.replay_service = FakeReplayService()
    mock_manager = MagicMock()
    mock_manager.status = "stopped"
    mock_manager.start = AsyncMock(return_value="test-experiment-id")
    # stop/pause/resume now return the real manager's result dict; handlers
    # read .get("stopped") / .get("paused") off it so AsyncMock's default
    # MagicMock return isn't enough — give each a realistic payload.
    mock_manager.stop = AsyncMock(return_value={"stopped": True, "reason": "stopped"})
    mock_manager.pause = AsyncMock(return_value={"paused": True, "reason": "paused"})
    mock_manager.resume = AsyncMock(return_value={"resumed": True, "reason": "unpaused"})
    mock_manager.metrics_queue = _make_queue_mock(500)
    mock_manager.frames_queue = _make_queue_mock(100)
    mock_manager.results_queue = _make_queue_mock(200)
    # Health check inspects manager._thread; None means no running training.
    mock_manager._thread = None

    app.state.training_service = TrainingServiceWrapper.__new__(TrainingServiceWrapper)
    app.state.training_service.manager = mock_manager
    app.state.training_service.status = lambda: {
        "state": "stopped",
        "current_step": 0,
        "current_episode": 0,
        "experiment_id": None,
        "bot_level": 1,
        "started_at": None,
    }
    # Expose the last-frame accessor the /api/training/current_frame endpoint
    # calls. Default None — individual tests overwrite when a frame should
    # be surfaced.
    app.state.training_service.last_frame = lambda: None
    app.state.eval_service = FakeEvalService()
    app.state.ws_manager = ConnectionManager()
    yield
    pass


def pytest_addoption(parser: pytest.Parser) -> None:
    # No default live-backend URL. Incident 2026-04-17: a silent default of
    # http://localhost:8001 caused a full-suite unit-test run to hammer the
    # dev backend with training:start/set_level/stop via httpx+WebSocket.
    # E2E tests must be opt-in with explicit --base-url AND -m e2e.
    parser.addoption(
        "--base-url",
        default="http://localhost:9999",
        help=(
            "Base URL for E2E/regression tests. Default is an unreachable "
            "port so accidental runs fail fast instead of mutating a live "
            "env. Supply --base-url + -m e2e when running against QA/prod."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    # The `e2e` and `load` markers are also declared in pyproject.toml so
    # `-m 'not e2e'` is picked up via addopts. Re-registering here keeps
    # older invocations (outside the pyproject path) lint-clean.
    config.addinivalue_line(
        "markers",
        "e2e: end-to-end tests that hit a live backend over "
        "httpx/WebSocket. Deselected by default.",
    )
    config.addinivalue_line(
        "markers",
        "load: marks tests that exert heavy concurrency/load "
        "(deselect with -m 'not load')",
    )


@pytest.fixture
def rl_env():
    from backend.rl.env import PikachuVolleyballEnv

    env = PikachuVolleyballEnv(bot_level=1, max_steps=3000)
    yield env
    env.close()


@pytest.fixture
def game_engine():
    from backend.game.engine import PikachuVolleyball

    game = PikachuVolleyball()
    game.reset()
    return game


@pytest.fixture
def game_state(game_engine):
    """Reset the game engine before each test that uses it."""
    game_engine.reset()
    return None


@pytest.fixture
def app_instance():
    from backend.app.main import app

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan
    yield app
    app.router.lifespan_context = original_lifespan


@pytest.fixture
def client(app_instance):
    with TestClient(app_instance) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_route_caches():
    """Clear TTL caches attached to route handlers before each test.

    The ``@cache_ttl`` decorator exposes the underlying ``AsyncTTLCache`` via
    ``wrapper.cache``; without this reset, a successful response in one test
    would satisfy later tests whose fixtures swap the service for a mock.
    """
    try:
        from backend.app.api import routes as routes_mod

        for obj in vars(routes_mod).values():
            cache = getattr(obj, "cache", None)
            if cache is not None and hasattr(cache, "clear"):
                cache.clear()
    except Exception:  # noqa: BLE001 — best-effort test hygiene
        pass
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limit_buckets():
    """Clear in-memory rate-limit buckets before each test.

    The RateLimitMiddleware instance is shared across every TestClient
    because FastAPI builds the middleware chain once at import. Without a
    reset, earlier tests (test_api, test_error_handling, ...) consume
    tokens and later tests that hit the same endpoints end up getting 429
    instead of the status they expect. Per-test reset keeps each test in
    control of its own rate-limit assumptions.
    """
    try:
        from backend.app.main import app as _app

        for mw in _app.user_middleware:
            if mw.cls.__name__ == "RateLimitMiddleware":
                # Starlette stores options under mw.kwargs; the bucket dict
                # lives on the bound middleware once the app is built, not on
                # the config. We reach the instance through app.middleware_stack.
                break
        # Walk the middleware stack to find the RateLimitMiddleware instance.
        stack = getattr(_app, "middleware_stack", None)
        while stack is not None:
            if type(stack).__name__ == "RateLimitMiddleware":
                stack._buckets.clear()
                break
            stack = getattr(stack, "app", None)
    except Exception:  # noqa: BLE001 — best-effort test hygiene
        pass
    yield
