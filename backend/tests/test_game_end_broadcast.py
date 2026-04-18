"""training:game_end WS broadcast after a successful save (BE-T7)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest


class _FakeGameService:
    """Minimal save-only GameService stand-in."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.saved: list = []

    async def save_game(self, record):
        if self.fail:
            raise RuntimeError("db unavailable")
        self.saved.append(record)


async def _run_one_loop_iteration(manager, training_service, game_service):
    """Drive results_push_loop for exactly one queue item, then cancel."""
    from backend.app.ws.handlers import results_push_loop

    broadcasts: list[dict] = []
    # First call succeeds, second call ends the loop — cancellation
    # isn't raised inside broadcast until AFTER the first training:
    # game_end + game:result pair the contract emits per save.
    call_count = {"n": 0}

    async def _broadcast(payload):
        broadcasts.append(payload)
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise asyncio.CancelledError

    manager.broadcast = _broadcast
    with pytest.raises(asyncio.CancelledError):
        await results_push_loop(manager, training_service, game_service)
    return broadcasts


class TestGameEndBroadcast:
    @pytest.mark.asyncio
    async def test_emits_training_game_end_after_save(self):
        queue: asyncio.Queue = asyncio.Queue()
        await queue.put({
            "game_id": "55555555-5555-5555-5555-555555555555",
            "experiment_id": "exp-t7",
            "bot_level": 3,
            "score1": 15,
            "score2": 12,
            "winner": 1,
            "duration_frames": 2500,
            "rally_count": 42,
            "env_id": "0",
            "title": "run-t7-check",
            "episode": 87,
        })

        training_service = MagicMock()
        training_service.manager.results_queue = queue

        broadcasts = await _run_one_loop_iteration(
            MagicMock(),
            training_service,
            _FakeGameService(),
        )

        # First broadcast — training:game_end with the structured record.
        assert broadcasts[0]["type"] == "training:game_end"
        record = broadcasts[0]["payload"]["record"]
        assert record["game_id"] == "55555555-5555-5555-5555-555555555555"
        assert record["title"] == "run-t7-check"
        assert record["env_id"] == "0"
        assert record["score1"] == 15
        assert record["score2"] == 12
        assert record["winner"] == 1
        assert record["episode"] == 87
        assert record["duration_frames"] == 2500
        assert record["experiment_id"] == "exp-t7"
        # Timestamp is populated at record-build time — always a string.
        assert isinstance(record["timestamp"], str)

        # Second broadcast — the legacy game:result envelope still fires
        # after game_end so existing FE subscribers keep working.
        assert broadcasts[1]["type"] == "game:result"

    @pytest.mark.asyncio
    async def test_no_game_end_when_save_fails(self, tmp_path, monkeypatch):
        # Redirect dead-letter to a tmp file — its parent must be writable.
        monkeypatch.setenv("FAILED_RESULTS_PATH", str(tmp_path / "dl.jsonl"))
        # Import-time path cache is set in handlers.py; patch it too.
        import backend.app.ws.handlers as h_mod

        monkeypatch.setattr(h_mod, "DEAD_LETTER_PATH", tmp_path / "dl.jsonl")

        queue: asyncio.Queue = asyncio.Queue()
        await queue.put({
            "game_id": "66666666-6666-6666-6666-666666666666",
            "experiment_id": "exp-t7-fail",
            "bot_level": 3,
            "score1": 15,
            "score2": 10,
            "winner": 1,
            "duration_frames": 1000,
            "rally_count": 10,
            "env_id": "1",
            "title": "run-t7-fail",
            "episode": 5,
        })

        training_service = MagicMock()
        training_service.manager.results_queue = queue

        broadcasts = await _run_one_loop_iteration(
            MagicMock(),
            training_service,
            _FakeGameService(fail=True),
        )

        # Error broadcast + game:result, NO training:game_end.
        assert not any(b["type"] == "training:game_end" for b in broadcasts)
        assert broadcasts[0]["type"] == "error"
        assert broadcasts[1]["type"] == "game:result"

    @pytest.mark.asyncio
    async def test_payload_shape_has_all_fields(self):
        queue: asyncio.Queue = asyncio.Queue()
        await queue.put({
            "game_id": "77777777-7777-7777-7777-777777777777",
            "experiment_id": "exp",
            "bot_level": 1,
            "score1": 15,
            "score2": 0,
            "winner": 1,
            "duration_frames": 500,
            "rally_count": 3,
            # Intentionally legacy-shape — no title/env_id/episode.
        })

        training_service = MagicMock()
        training_service.manager.results_queue = queue

        broadcasts = await _run_one_loop_iteration(
            MagicMock(),
            training_service,
            _FakeGameService(),
        )

        record = broadcasts[0]["payload"]["record"]
        # Missing optional fields arrive as None, not KeyError.
        assert record["title"] is None
        assert record["env_id"] is None
        assert record["episode"] is None
        # Required fields still present.
        assert record["score1"] == 15
        assert record["winner"] == 1
