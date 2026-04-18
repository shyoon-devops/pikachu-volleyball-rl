"""Per-env game save (BE-A2) — env drain hook + EnvResultCallback.

Verifies the producer side of the per-env save pipeline:
  * PikachuVolleyballEnv queues a result dict when a match terminates.
  * Truncation (stall / max_steps) does NOT queue — only real wins.
  * drain_pending_results returns AND clears in one call.
  * EnvResultCallback pulls from each env and enqueues on the shared
    results_queue with env_id tagged.
  * GameRecord schema accepts env_id.
  * results_push_loop forwards env_id through to the persisted record.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.game.constants import MAX_SCORE
from backend.rl.callbacks import EnvResultCallback
from backend.rl.env import PikachuVolleyballEnv


class TestEnvDrainHook:
    """PikachuVolleyballEnv.drain_pending_results contract."""

    def test_terminated_match_queues_result(self):
        env = PikachuVolleyballEnv(bot_level=1)
        env.reset()
        # Force a terminal condition — p1 wins on this step.
        env._game._state.score1 = MAX_SCORE - 1
        # Seed the ball on p2's side so the next ground-out scores p1.
        from backend.game.constants import BALL_GROUND_Y, GROUND_WIDTH

        env._game._state.ball.x = GROUND_WIDTH - 50
        env._game._state.ball.y = BALL_GROUND_Y - 1
        env._game._state.ball.vx = 0
        env._game._state.ball.vy = 5
        env.step(0)  # noop action — engine handles the scoring
        results = env.drain_pending_results()
        assert len(results) == 1
        r = results[0]
        assert r["score1"] == MAX_SCORE
        assert r["winner"] == 1
        assert r["duration_frames"] > 0
        assert r["rally_count"] >= 0

    def test_truncated_match_does_not_queue(self):
        """Stall / max_steps truncations must NOT be saved as games."""
        env = PikachuVolleyballEnv(bot_level=1, max_steps=1)
        env.reset()
        env.step(0)  # immediately truncates (max_steps=1)
        results = env.drain_pending_results()
        assert results == []

    def test_drain_clears_list(self):
        env = PikachuVolleyballEnv(bot_level=1)
        env.reset()
        env._pending_results.append({"score1": MAX_SCORE, "score2": 0, "winner": 1,
                                     "duration_frames": 100, "rally_count": 5})
        first = env.drain_pending_results()
        second = env.drain_pending_results()
        assert len(first) == 1
        assert second == []

    def test_rally_count_increments_on_net_crossing(self):
        """Net crossings accumulate per-match across both directions."""
        from backend.game.constants import NET_PILLAR_X

        env = PikachuVolleyballEnv(bot_level=1)
        env.reset()
        start = env._rally_count
        # Force ball to the right side → counts one crossing.
        env._game._state.ball.x = NET_PILLAR_X + 50
        env.step(0)
        assert env._rally_count == start + 1
        # Cross back → another.
        env._game._state.ball.x = NET_PILLAR_X - 50
        env.step(0)
        assert env._rally_count == start + 2


class TestEnvResultCallback:
    """EnvResultCallback drains each env and enqueues tagged results."""

    @staticmethod
    def _fake_training_env(per_env_results: list[list[dict]]):
        env = MagicMock()
        env.env_method.return_value = per_env_results
        return env

    def test_drain_enqueues_tagged_results(self):
        import backend.rl.callbacks as cb_mod

        loop = asyncio.new_event_loop()
        q: asyncio.Queue[dict] = asyncio.Queue()

        manager = MagicMock()
        manager._experiment_id = "exp-xyz"
        manager._bot_level = 3

        cb = EnvResultCallback(
            results_queue=q, loop=loop, manager=manager, drain_interval=1
        )
        fake_env = self._fake_training_env([
            [{"score1": MAX_SCORE, "score2": 11, "winner": 1,
              "duration_frames": 3000, "rally_count": 42}],  # env 0
            [],  # env 1 — no completed games this tick
            [{"score1": 8, "score2": MAX_SCORE, "winner": 2,
              "duration_frames": 4000, "rally_count": 51}],  # env 2
        ])
        cb.model = MagicMock()
        cb.model.get_env.return_value = fake_env
        cb.n_calls = 1

        captured: list[dict] = []
        original = cb_mod._safe_enqueue
        cb_mod._safe_enqueue = lambda _loop, _q, item: captured.append(item)
        try:
            cb._on_step()
        finally:
            cb_mod._safe_enqueue = original

        assert len(captured) == 2
        r0 = captured[0]
        assert r0["env_id"] == "0"
        assert r0["experiment_id"] == "exp-xyz"
        assert r0["bot_level"] == 3
        assert r0["score1"] == MAX_SCORE
        assert r0["winner"] == 1
        assert r0["rally_count"] == 42
        assert "game_id" in r0 and len(r0["game_id"]) >= 8

        r2 = captured[1]
        assert r2["env_id"] == "2"
        assert r2["winner"] == 2

    def test_drain_interval_skips_between_ticks(self):
        import backend.rl.callbacks as cb_mod

        loop = asyncio.new_event_loop()
        q: asyncio.Queue[dict] = asyncio.Queue()
        cb = EnvResultCallback(results_queue=q, loop=loop, drain_interval=4)
        fake_env = self._fake_training_env([[{"score1": 15, "score2": 0, "winner": 1,
                                              "duration_frames": 1, "rally_count": 0}]])
        cb.model = MagicMock()
        cb.model.get_env.return_value = fake_env

        captured: list[dict] = []
        original = cb_mod._safe_enqueue
        cb_mod._safe_enqueue = lambda _loop, _q, item: captured.append(item)
        try:
            for i in range(1, 4):  # 1, 2, 3 — none on drain boundary
                cb.n_calls = i
                cb._on_step()
            assert captured == []
            cb.n_calls = 4  # drain tick
            cb._on_step()
            assert len(captured) == 1
        finally:
            cb_mod._safe_enqueue = original

    def test_drain_failure_does_not_abort(self):
        loop = asyncio.new_event_loop()
        q: asyncio.Queue[dict] = asyncio.Queue()
        cb = EnvResultCallback(results_queue=q, loop=loop, drain_interval=1)
        broken = MagicMock()
        broken.env_method.side_effect = RuntimeError("worker died")
        cb.model = MagicMock()
        cb.model.get_env.return_value = broken
        cb.n_calls = 1
        assert cb._on_step() is True


class TestGameRecordEnvId:
    """Schema + handler contract — env_id round-trips through GameRecord."""

    def test_game_record_accepts_env_id(self):
        from backend.app.models.schemas import GameRecord

        r = GameRecord(
            experiment_id="exp",
            bot_level=1,
            score1=15, score2=10, winner=1,
            duration_frames=100, rally_count=5,
            env_id="3",
        )
        doc = r.model_dump(by_alias=True, exclude_none=True)
        assert doc["env_id"] == "3"

    def test_game_record_env_id_optional_legacy(self):
        from backend.app.models.schemas import GameRecord

        r = GameRecord(
            experiment_id="exp",
            bot_level=1,
            score1=15, score2=10, winner=1,
            duration_frames=100, rally_count=5,
        )
        doc = r.model_dump(by_alias=True, exclude_none=True)
        assert "env_id" not in doc  # None omitted via exclude_none


class TestResultsPushLoopWithEnvId:
    """results_push_loop forwards env_id onto the persisted GameRecord."""

    @pytest.mark.asyncio
    async def test_env_id_flows_through_handler(self):
        from backend.app.ws.handlers import results_push_loop

        saved: list[Any] = []

        class _GameSvc:
            async def save_game(self, record):
                saved.append(record)

        # Build a fake training_service wrapper.
        training_service = MagicMock()
        training_service.manager.results_queue = asyncio.Queue()
        await training_service.manager.results_queue.put({
            "game_id": "11111111-1111-1111-1111-111111111111",
            "experiment_id": "exp-bg",
            "bot_level": 2,
            "score1": 15, "score2": 12, "winner": 1,
            "duration_frames": 2500, "rally_count": 30,
            "env_id": "5",
        })

        manager = MagicMock()

        async def _broadcast(_payload):
            raise asyncio.CancelledError

        manager.broadcast = _broadcast

        with pytest.raises(asyncio.CancelledError):
            await results_push_loop(manager, training_service, _GameSvc())

        assert len(saved) == 1
        assert saved[0].env_id == "5"
        assert saved[0].score1 == 15
