"""WS league_push_loop — training:league_update broadcasts (B-impl-5)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from backend.app.models.league import (
    LeagueCheckpoint,
    LeagueStandings,
    now_iso,
)
from backend.app.ws.handlers import league_push_loop


def _ckpt(cid, elo):
    return LeagueCheckpoint.model_validate({
        "id": cid, "elo": elo, "wins": 0, "losses": 0,
        "games": 0, "admitted_at": now_iso(), "source": "training",
    })


class _FakeRepo:
    def __init__(self, standings):
        self._standings = standings

    async def standings_envelope(self, limit=10):
        return self._standings


class _FakeManager:
    def __init__(self):
        self.league_queue: asyncio.Queue = asyncio.Queue()


async def _drive_one(manager_mock, training_service, repo):
    broadcasts: list[dict] = []

    async def _broadcast(payload):
        broadcasts.append(payload)
        raise asyncio.CancelledError

    manager_mock.broadcast = _broadcast
    with pytest.raises(asyncio.CancelledError):
        await league_push_loop(manager_mock, training_service, repo)
    return broadcasts


class TestLeaguePushLoop:
    @pytest.mark.asyncio
    async def test_emits_training_league_update(self):
        training_service = MagicMock()
        mgr = _FakeManager()
        training_service.manager = mgr

        standings = LeagueStandings(
            top=[_ckpt("a", 1200), _ckpt("b", 1050)],
            champion_id="a",
            generation=4,
            pool_size=32,
            total_checkpoints=2,
        )
        repo = _FakeRepo(standings)

        await mgr.league_queue.put({
            "total_matches": 64,
            "since_last_broadcast": 64,
            "recent": [{"winner": 1, "score1": 15, "score2": 9}],
        })
        ws_manager = MagicMock()
        broadcasts = await _drive_one(ws_manager, training_service, repo)

        assert broadcasts[0]["type"] == "training:league_update"
        payload = broadcasts[0]["payload"]
        assert [c["id"] for c in payload["top_n"]] == ["a", "b"]
        assert payload["champion_id"] == "a"
        assert payload["generation"] == 4
        assert payload["pool_size"] == 32
        assert payload["total_matches"] == 64
        assert payload["since_last_broadcast"] == 64
        assert payload["recent"] == [{"winner": 1, "score1": 15, "score2": 9}]

    @pytest.mark.asyncio
    async def test_missing_league_queue_parks(self):
        training_service = MagicMock()
        training_service.manager = MagicMock(spec=[])  # no league_queue
        # Loop should return cleanly without broadcasting.
        await league_push_loop(MagicMock(), training_service, _FakeRepo(None))

    @pytest.mark.asyncio
    async def test_missing_repository_parks(self):
        training_service = MagicMock()
        training_service.manager = _FakeManager()
        # league_queue exists but repository is None → park.
        await league_push_loop(MagicMock(), training_service, None)

    @pytest.mark.asyncio
    async def test_payload_build_failure_does_not_kill_loop(self):
        """If standings_envelope raises, we log + skip, but keep looping.

        Drive two records: the first raises (should be skipped), the
        second succeeds (should be broadcast). Verifies the loop
        doesn't die on a transient DB error.
        """
        training_service = MagicMock()
        mgr = _FakeManager()
        training_service.manager = mgr

        standings = LeagueStandings(
            top=[_ckpt("x", 1100)],
            champion_id="x",
            generation=1,
            pool_size=32,
            total_checkpoints=1,
        )

        attempts = {"n": 0}

        class _FlakyRepo:
            async def standings_envelope(self, limit=10):
                attempts["n"] += 1
                if attempts["n"] == 1:
                    raise RuntimeError("mongo blipped")
                return standings

        await mgr.league_queue.put({"total_matches": 64, "recent": []})
        await mgr.league_queue.put({"total_matches": 128, "recent": []})

        broadcasts: list[dict] = []

        async def _broadcast(payload):
            broadcasts.append(payload)
            if len(broadcasts) >= 1:
                raise asyncio.CancelledError

        ws_manager = MagicMock()
        ws_manager.broadcast = _broadcast

        with pytest.raises(asyncio.CancelledError):
            await league_push_loop(ws_manager, training_service, _FlakyRepo())

        # First record failed silently; second succeeded and broadcast once.
        assert len(broadcasts) == 1
        assert broadcasts[0]["payload"]["champion_id"] == "x"
        assert broadcasts[0]["payload"]["total_matches"] == 128


class TestTrainingManagerLeagueQueue:
    def test_manager_exposes_bounded_league_queue(self):
        from backend.rl.trainer import TrainingManager

        mgr = TrainingManager(
            model_dir="/tmp/m_league", replay_dir="/tmp/r_league",
        )
        assert hasattr(mgr, "league_queue")
        assert isinstance(mgr.league_queue, asyncio.Queue)
        assert mgr.league_queue.maxsize > 0
