"""Shared test fixtures — mocks MongoDB so tests run without a live instance."""

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
    async def run(self, model_path: str, bot_level: int = 1, n_games: int = 50):
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
    app.state.replay_service = FakeReplayService()
    mock_manager = MagicMock()
    mock_manager.status = "stopped"
    mock_manager.start = AsyncMock(return_value="test-experiment-id")
    mock_manager.stop = AsyncMock()
    mock_manager.resume = AsyncMock()
    mock_manager.metrics_queue = _make_queue_mock(500)
    mock_manager.frames_queue = _make_queue_mock(100)
    mock_manager.results_queue = _make_queue_mock(200)
    # Health check inspects `manager._thread`; MagicMock is fine (is_alive() returns a mock truthy value).
    mock_manager._thread = None

    app.state.training_service = TrainingServiceWrapper.__new__(TrainingServiceWrapper)
    app.state.training_service.manager = mock_manager
    app.state.training_service.status = lambda: {
        "state": "stopped",
        "current_step": 0,
        "current_episode": 0,
    }
    app.state.eval_service = FakeEvalService()
    app.state.ws_manager = ConnectionManager()
    yield
    pass


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
