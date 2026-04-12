"""Tests for results_push_loop retry + dead-letter behavior (BUG-6)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.ws import handlers as wsh


class _FlakyGameService:
    """Fails the first N save_game calls then succeeds."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.saved: list = []

    async def save_game(self, record):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"transient error #{self.calls}")
        self.saved.append(record)
        return "id"


class _AlwaysFailService:
    async def save_game(self, record):
        raise RuntimeError("mongo unavailable")


def _make_record_payload() -> dict:
    return {
        "game_id": "test-game-1",
        "experiment_id": "exp-1",
        "bot_level": 1,
        "score1": 15,
        "score2": 10,
        "winner": 1,
        "duration_frames": 300,
        "rally_count": 5,
    }


@pytest.mark.asyncio
async def test_save_with_retry_recovers_after_transient_failure(monkeypatch):
    """save_game retries and succeeds on the 2nd attempt."""
    # Speed up retries.
    monkeypatch.setattr(wsh, "SAVE_RETRY_BASE_DELAY", 0.0)
    svc = _FlakyGameService(fail_times=1)

    from backend.app.models.schemas import GameRecord
    record = GameRecord(**_make_record_payload())

    err = await wsh._save_with_retry(svc, record)
    assert err is None
    assert svc.calls == 2
    assert len(svc.saved) == 1


@pytest.mark.asyncio
async def test_save_with_retry_gives_up_after_max_attempts(monkeypatch):
    """save_game returns the last error after SAVE_RETRY_ATTEMPTS."""
    monkeypatch.setattr(wsh, "SAVE_RETRY_BASE_DELAY", 0.0)
    svc = _AlwaysFailService()

    from backend.app.models.schemas import GameRecord
    record = GameRecord(**_make_record_payload())

    err = await wsh._save_with_retry(svc, record)
    assert err is not None
    assert isinstance(err, RuntimeError)


@pytest.mark.asyncio
async def test_results_push_loop_writes_dead_letter_on_total_failure(
    monkeypatch, tmp_path: Path
):
    """When all retries fail, the record is appended to the dead-letter file
    and an error event is broadcast."""
    dead_letter = tmp_path / "failed_results.jsonl"
    monkeypatch.setattr(wsh, "SAVE_RETRY_BASE_DELAY", 0.0)
    monkeypatch.setattr(wsh, "DEAD_LETTER_PATH", dead_letter)

    payload = _make_record_payload()

    # Queue that yields one item then blocks forever; we cancel after one cycle.
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(payload)

    training_service = MagicMock()
    training_service.manager.results_queue = queue

    game_service = _AlwaysFailService()

    broadcasts: list[dict] = []

    class _MgrStub:
        broadcast = AsyncMock(side_effect=lambda msg: broadcasts.append(msg))

    manager = _MgrStub()

    task = asyncio.create_task(
        wsh.results_push_loop(manager, training_service, game_service)  # type: ignore[arg-type]
    )
    # Let the loop drain the single item; yield control a few times.
    for _ in range(20):
        await asyncio.sleep(0)
        if dead_letter.exists() and len(broadcasts) >= 2:
            break
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert dead_letter.exists(), "dead-letter file must be written"
    line = dead_letter.read_text().strip().splitlines()[0]
    entry = json.loads(line)
    assert entry["record"]["game_id"] == "test-game-1"
    assert "mongo unavailable" in entry["error"]

    # Expect an error broadcast + the normal game:result broadcast.
    types = [m["type"] for m in broadcasts]
    assert "error" in types
    assert "game:result" in types


@pytest.mark.asyncio
async def test_results_push_loop_invalid_payload_goes_to_dead_letter(
    monkeypatch, tmp_path: Path
):
    """Malformed payloads are preserved in the dead-letter file, not dropped."""
    dead_letter = tmp_path / "failed_results.jsonl"
    monkeypatch.setattr(wsh, "DEAD_LETTER_PATH", dead_letter)

    # Missing required fields -> GameRecord validation error.
    bad_payload = {"game_id": "bad", "experiment_id": "exp"}

    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(bad_payload)

    training_service = MagicMock()
    training_service.manager.results_queue = queue

    broadcasts: list[dict] = []

    class _MgrStub:
        broadcast = AsyncMock(side_effect=lambda msg: broadcasts.append(msg))

    game_service = MagicMock()
    game_service.save_game = AsyncMock()

    task = asyncio.create_task(
        wsh.results_push_loop(_MgrStub(), training_service, game_service)  # type: ignore[arg-type]
    )
    for _ in range(20):
        await asyncio.sleep(0)
        if dead_letter.exists():
            break
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert dead_letter.exists()
    entry = json.loads(dead_letter.read_text().strip().splitlines()[0])
    assert entry["record"]["game_id"] == "bad"
    game_service.save_game.assert_not_called()
    assert any(m["type"] == "error" for m in broadcasts)
