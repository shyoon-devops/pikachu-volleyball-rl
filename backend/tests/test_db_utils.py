"""Tests for the Mongo client builder and retry helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pymongo.errors import (
    AutoReconnect,
    ConnectionFailure,
    DuplicateKeyError,
    NetworkTimeout,
    ServerSelectionTimeoutError,
)

from backend.app.services.db_utils import (
    TRANSIENT_ERRORS,
    build_mongo_client,
    with_mongo_retry,
)


# --- build_mongo_client ------------------------------------------------------


def test_build_mongo_client_applies_defaults():
    """Default pool + timeout values are applied when env is unset."""
    with patch.dict(
        "os.environ",
        {k: "" for k in (
            "MONGO_MAX_POOL_SIZE", "MONGO_MIN_POOL_SIZE",
            "MONGO_SERVER_SELECTION_TIMEOUT_MS", "MONGO_CONNECT_TIMEOUT_MS",
            "MONGO_SOCKET_TIMEOUT_MS", "MONGO_WAIT_QUEUE_TIMEOUT_MS",
            "MONGO_RETRY_WRITES",
        )},
        clear=False,
    ):
        # Clear the vars so defaults apply
        for k in list(
            k for k in (
                "MONGO_MAX_POOL_SIZE", "MONGO_MIN_POOL_SIZE",
                "MONGO_SERVER_SELECTION_TIMEOUT_MS", "MONGO_CONNECT_TIMEOUT_MS",
                "MONGO_SOCKET_TIMEOUT_MS", "MONGO_WAIT_QUEUE_TIMEOUT_MS",
                "MONGO_RETRY_WRITES",
            )
        ):
            __import__("os").environ.pop(k, None)

        client = build_mongo_client("mongodb://localhost:27017/test")
        opts = client.options
    # maxPoolSize / minPoolSize are surfaced via pool_options on newer motor
    pool = opts.pool_options
    assert pool.max_pool_size == 50
    assert pool.min_pool_size == 5
    assert opts.server_selection_timeout == 5.0  # seconds
    assert pool.connect_timeout == 5.0
    assert pool.socket_timeout == 20.0


def test_build_mongo_client_reads_env_overrides(monkeypatch):
    monkeypatch.setenv("MONGO_MAX_POOL_SIZE", "200")
    monkeypatch.setenv("MONGO_MIN_POOL_SIZE", "10")
    monkeypatch.setenv("MONGO_CONNECT_TIMEOUT_MS", "1500")
    monkeypatch.setenv("MONGO_SOCKET_TIMEOUT_MS", "3000")
    monkeypatch.setenv("MONGO_RETRY_WRITES", "false")

    client = build_mongo_client("mongodb://localhost:27017/test")
    pool = client.options.pool_options
    assert pool.max_pool_size == 200
    assert pool.min_pool_size == 10
    assert pool.connect_timeout == 1.5
    assert pool.socket_timeout == 3.0


# --- with_mongo_retry --------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_returns_value_on_first_attempt():
    op = AsyncMock(return_value="ok")
    result = await with_mongo_retry(op, attempts=3, base_delay=0.0)
    assert result == "ok"
    assert op.await_count == 1


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failure():
    """Transient error on attempt 1 → success on attempt 2."""
    op = AsyncMock(side_effect=[AutoReconnect("flap"), "ok"])
    result = await with_mongo_retry(op, attempts=3, base_delay=0.0)
    assert result == "ok"
    assert op.await_count == 2


@pytest.mark.asyncio
async def test_retry_raises_after_exhausting_attempts():
    op = AsyncMock(side_effect=NetworkTimeout("timeout"))
    with pytest.raises(NetworkTimeout):
        await with_mongo_retry(op, attempts=3, base_delay=0.0)
    assert op.await_count == 3


@pytest.mark.asyncio
async def test_retry_does_not_swallow_non_transient_errors():
    """Business-level errors (duplicate key, etc) propagate immediately."""
    op = AsyncMock(side_effect=DuplicateKeyError("dup"))
    with pytest.raises(DuplicateKeyError):
        await with_mongo_retry(op, attempts=3, base_delay=0.0)
    assert op.await_count == 1  # no retry


@pytest.mark.asyncio
async def test_retry_handles_server_selection_timeout():
    op = AsyncMock(side_effect=[ServerSelectionTimeoutError("no primary"), "ok"])
    result = await with_mongo_retry(op, attempts=2, base_delay=0.0)
    assert result == "ok"


@pytest.mark.asyncio
async def test_retry_handles_connection_failure():
    op = AsyncMock(side_effect=[ConnectionFailure("refused"), "ok"])
    result = await with_mongo_retry(op, attempts=2, base_delay=0.0)
    assert result == "ok"


@pytest.mark.asyncio
async def test_retry_delay_is_exponential(monkeypatch):
    """Verify backoff doubles between attempts."""
    sleeps: list[float] = []

    async def _fake_sleep(d: float) -> None:
        sleeps.append(d)

    monkeypatch.setattr("backend.app.services.db_utils.asyncio.sleep", _fake_sleep)

    op = AsyncMock(side_effect=AutoReconnect("keep flapping"))
    with pytest.raises(AutoReconnect):
        await with_mongo_retry(op, attempts=4, base_delay=0.1)
    # attempts 1,2,3 fail before final attempt 4 → 3 sleeps: 0.1, 0.2, 0.4
    assert sleeps == [0.1, 0.2, 0.4]


# --- GameService integration ------------------------------------------------


@pytest.mark.asyncio
async def test_game_service_save_retries_on_autoreconnect():
    """save_game retries transient Mongo errors."""
    from backend.app.models.schemas import GameRecord
    from backend.app.services.game_service import GameService

    # Mock database/collection with a flaky insert_one
    class _FakeColl:
        def __init__(self):
            self.calls = 0

        async def insert_one(self, doc):
            self.calls += 1
            if self.calls < 3:
                raise AutoReconnect("flap")

            class _R:
                inserted_id = "fake-id"

            return _R()

    fake_col = _FakeColl()
    # Build a GameService without touching Motor
    svc = GameService.__new__(GameService)
    svc._col = fake_col

    record = GameRecord(
        experiment_id="e1", bot_level=1, score1=1, score2=0, winner=1,
        duration_frames=10, rally_count=1,
    )
    # Patch sleep so test runs instantly
    with patch("backend.app.services.db_utils.asyncio.sleep", AsyncMock()):
        result = await svc.save_game(record)
    assert result == "fake-id"
    assert fake_col.calls == 3


def test_transient_errors_list_is_non_empty():
    """Sanity check: transient-error tuple covers at least the expected types."""
    assert AutoReconnect in TRANSIENT_ERRORS
    assert ConnectionFailure in TRANSIENT_ERRORS
    assert NetworkTimeout in TRANSIENT_ERRORS
    assert ServerSelectionTimeoutError in TRANSIENT_ERRORS
