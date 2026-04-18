"""Episode field on GameRecord (BE-T6).

FE shipped FC-R6D (8688790f) with a "-" placeholder waiting for BE.
These tests pin the producer contract: every new game save carries an
episode snapshot, legacy rows still load with ``episode=None``.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from backend.app.models.schemas import GameRecord


class TestGameRecordEpisodeField:
    def test_accepts_episode(self):
        r = GameRecord(
            experiment_id="e",
            bot_level=1,
            score1=15,
            score2=10,
            winner=1,
            duration_frames=1000,
            rally_count=15,
            episode=42,
        )
        assert r.episode == 42

    def test_episode_optional_for_legacy(self):
        r = GameRecord(
            experiment_id="e",
            bot_level=1,
            score1=15,
            score2=10,
            winner=1,
            duration_frames=1000,
            rally_count=15,
        )
        assert r.episode is None

    def test_rejects_negative_episode(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            GameRecord(
                experiment_id="e",
                bot_level=1,
                score1=15,
                score2=10,
                winner=1,
                duration_frames=1000,
                rally_count=15,
                episode=-1,
            )


class TestLiveFrameCallbackTagsEpisode:
    """LiveFrameCallback pulls current_episode off the manager at save."""

    def test_demo_result_carries_current_episode(self, monkeypatch, tmp_path):
        import backend.rl.callbacks as cb_mod
        from backend.rl.callbacks import LiveFrameCallback

        # Patch MAX_SCORE to 1 so the demo match ends immediately.
        monkeypatch.setattr(cb_mod, "MAX_SCORE", 1)

        loop = asyncio.new_event_loop()
        frames_q: asyncio.Queue[dict] = asyncio.Queue()
        results_q: asyncio.Queue[dict] = asyncio.Queue()

        manager = MagicMock()
        manager._bot_level = 2
        manager._experiment_id = "exp-ep"
        manager._title = "run-episode-check"
        manager.current_episode = 17
        manager.last_frame = None

        cb = LiveFrameCallback(
            frames_queue=frames_q,
            results_queue=results_q,
            loop=loop,
            bot_level=1,
            play_interval=1,
            replay_dir=str(tmp_path),
            manager=manager,
        )
        cb.num_timesteps = 1
        fake_model = MagicMock()
        fake_model.predict.return_value = (0, None)
        cb.model = fake_model

        captured: list[dict] = []
        monkeypatch.setattr(
            cb_mod,
            "_safe_enqueue",
            lambda _loop, _q, item: captured.append(item),
        )
        assert cb._on_step() is True
        loop.close()

        results = [c for c in captured if "winner" in c]
        assert len(results) == 1
        assert results[0]["episode"] == 17

    def test_episode_zero_when_manager_absent(self, monkeypatch, tmp_path):
        import backend.rl.callbacks as cb_mod
        from backend.rl.callbacks import LiveFrameCallback

        monkeypatch.setattr(cb_mod, "MAX_SCORE", 1)

        loop = asyncio.new_event_loop()
        cb = LiveFrameCallback(
            frames_queue=asyncio.Queue(),
            results_queue=asyncio.Queue(),
            loop=loop,
            bot_level=1,
            play_interval=1,
            replay_dir=str(tmp_path),
            manager=None,
        )
        cb.num_timesteps = 1
        fake_model = MagicMock()
        fake_model.predict.return_value = (0, None)
        cb.model = fake_model

        captured: list[dict] = []
        monkeypatch.setattr(
            cb_mod,
            "_safe_enqueue",
            lambda _loop, _q, item: captured.append(item),
        )
        cb._on_step()
        loop.close()

        results = [c for c in captured if "winner" in c]
        assert results[0]["episode"] == 0


class TestEnvResultCallbackTagsEpisode:
    """EnvResultCallback drains with the manager's current_episode."""

    def test_env_results_carry_episode(self, monkeypatch):
        import backend.rl.callbacks as cb_mod
        from backend.rl.callbacks import EnvResultCallback

        loop = asyncio.new_event_loop()
        q: asyncio.Queue[dict] = asyncio.Queue()

        manager = MagicMock()
        manager._bot_level = 3
        manager._experiment_id = "exp-ep"
        manager._title = "run-xyz"
        manager.current_episode = 88

        cb = EnvResultCallback(
            results_queue=q,
            loop=loop,
            manager=manager,
            drain_interval=1,
        )

        fake_env = MagicMock()
        fake_env.env_method.return_value = [
            [{"score1": 15, "score2": 10, "winner": 1,
              "duration_frames": 1000, "rally_count": 10}],
            [],
            [{"score1": 5, "score2": 15, "winner": 2,
              "duration_frames": 2000, "rally_count": 20}],
        ]
        cb.model = MagicMock()
        cb.model.get_env.return_value = fake_env
        cb.n_calls = 1

        captured: list[dict] = []
        monkeypatch.setattr(
            cb_mod,
            "_safe_enqueue",
            lambda _loop, _q, item: captured.append(item),
        )
        cb._on_step()

        assert len(captured) == 2
        for row in captured:
            assert row["episode"] == 88


class TestResultsPushLoopPersistsEpisode:
    @pytest.mark.asyncio
    async def test_episode_flows_through_handler(self):
        from backend.app.ws.handlers import results_push_loop

        saved: list = []

        class _Svc:
            async def save_game(self, record):
                saved.append(record)

        training_service = MagicMock()
        training_service.manager.results_queue = asyncio.Queue()
        await training_service.manager.results_queue.put({
            "game_id": "44444444-4444-4444-4444-444444444444",
            "experiment_id": "exp",
            "bot_level": 1,
            "score1": 15,
            "score2": 10,
            "winner": 1,
            "duration_frames": 1000,
            "rally_count": 15,
            "env_id": "demo",
            "title": "run-eps",
            "episode": 33,
        })

        manager = MagicMock()

        async def _broadcast(_p):
            raise asyncio.CancelledError

        manager.broadcast = _broadcast

        with pytest.raises(asyncio.CancelledError):
            await results_push_loop(manager, training_service, _Svc())
        assert saved[0].episode == 33
