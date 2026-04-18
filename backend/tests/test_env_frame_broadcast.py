"""Per-env frame broadcast (BE-A1) — callback + env snapshot contract.

These tests stay hermetic: they exercise the callback's enqueue path
and the env's snapshot shape without booting an SB3 training loop.
SubprocVecEnv + PPO integration is covered end-to-end by the
existing trainer smoke test; here we verify the slice this commit
added (the callback, the snapshot, and the WS push loop wiring).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.rl.callbacks import EnvFrameCallback
from backend.rl.env import PikachuVolleyballEnv


class TestEnvSnapshotShape:
    """PikachuVolleyballEnv.get_frame_snapshot — the wire schema."""

    def test_snapshot_contains_frame_score_state_name(self):
        env = PikachuVolleyballEnv(bot_level=1)
        env.reset()
        snap = env.get_frame_snapshot()
        # Frame keys mirror the demo serializer (players + ball + flags).
        assert {"player1", "player2", "ball", "score1", "score2", "frame"}.issubset(snap.keys())
        # Top-level convenience duplicates the FE renders as a header.
        assert snap["score"] == [0, 0]
        assert snap["state_name"] in ("live", "scoring", "ended")

    def test_snapshot_state_name_flips_to_ended_at_max_score(self):
        env = PikachuVolleyballEnv(bot_level=1)
        env.reset()
        from backend.game.constants import MAX_SCORE

        # Force the engine into the gameEnd window.
        env._game._state.score1 = MAX_SCORE
        env._game._state.is_game_ended = True
        snap = env.get_frame_snapshot()
        assert snap["state_name"] == "ended"
        assert snap["score"] == [MAX_SCORE, 0]

    def test_snapshot_is_picklable_for_subprocvecenv(self):
        """Snapshot crosses the SubprocVecEnv pipe — must be plain dict primitives."""
        import pickle

        env = PikachuVolleyballEnv(bot_level=1)
        env.reset()
        snap = env.get_frame_snapshot()
        # If this fails, env.env_method("get_frame_snapshot") will raise
        # `PicklingError` at training time — a painful surprise to catch here.
        roundtrip = pickle.loads(pickle.dumps(snap))
        assert roundtrip == snap


class TestEnvFrameCallback:
    """Callback samples every N vec steps and enqueues per-env payloads."""

    @staticmethod
    def _fake_training_env(n_envs: int, snapshots: list[dict] | None = None):
        """Build a minimal MagicMock that answers env_method('get_frame_snapshot')."""
        env = MagicMock()
        env.env_method.return_value = snapshots or [
            {"score": [0, 0], "state_name": "live"} for _ in range(n_envs)
        ]
        return env

    def test_broadcast_interval_skips_between_samples(self):
        """n_calls % interval != 0 → no enqueue this tick."""
        loop = asyncio.new_event_loop()
        q: asyncio.Queue[dict] = asyncio.Queue()
        cb = EnvFrameCallback(env_frames_queue=q, loop=loop, broadcast_interval=4)
        fake_env = self._fake_training_env(n_envs=8)
        cb.model = MagicMock()
        cb.model.get_env.return_value = fake_env

        captured: list[Any] = []

        def _capture(loop_, queue, item):
            captured.append(item)

        # Patch _safe_enqueue so we see every would-be enqueue synchronously.
        import backend.rl.callbacks as cb_mod

        original = cb_mod._safe_enqueue
        cb_mod._safe_enqueue = _capture
        try:
            # n_calls starts at 0; BaseCallback increments it BEFORE _on_step
            # per SB3 semantics. Simulate the counter directly.
            for i in range(1, 9):  # 1..8
                cb.n_calls = i
                cb.num_timesteps = i * 8  # pretend n_envs=8
                cb._on_step()
        finally:
            cb_mod._safe_enqueue = original
        # With interval=4, only n_calls in {4, 8} emit → 2 × 8 = 16 payloads.
        assert len(captured) == 16
        # Each payload carries env_id 0..7, score, state_name.
        env_ids = {p["env_id"] for p in captured}
        assert env_ids == set(range(8))

    def test_snapshot_failure_does_not_crash_training(self):
        loop = asyncio.new_event_loop()
        q: asyncio.Queue[dict] = asyncio.Queue()
        cb = EnvFrameCallback(env_frames_queue=q, loop=loop, broadcast_interval=1)
        broken = MagicMock()
        broken.env_method.side_effect = RuntimeError("worker died")
        cb.model = MagicMock()
        cb.model.get_env.return_value = broken
        cb.n_calls = 1
        # Must return True (continue training) and NOT propagate the exception.
        assert cb._on_step() is True

    def test_payload_shape_has_required_fields(self):
        loop = asyncio.new_event_loop()
        q: asyncio.Queue[dict] = asyncio.Queue()
        cb = EnvFrameCallback(env_frames_queue=q, loop=loop, broadcast_interval=1)
        fake_env = self._fake_training_env(
            n_envs=2,
            snapshots=[
                {"score": [3, 2], "state_name": "live", "player1": {"x": 36}},
                {"score": [0, 1], "state_name": "scoring", "player1": {"x": 200}},
            ],
        )
        cb.model = MagicMock()
        cb.model.get_env.return_value = fake_env
        cb.n_calls = 1
        cb.num_timesteps = 100

        captured: list[dict] = []
        import backend.rl.callbacks as cb_mod

        original = cb_mod._safe_enqueue
        cb_mod._safe_enqueue = lambda _loop, _q, item: captured.append(item)
        try:
            cb._on_step()
        finally:
            cb_mod._safe_enqueue = original

        assert len(captured) == 2
        first = captured[0]
        assert first["env_id"] == 0
        assert first["frame"]["player1"]["x"] == 36
        assert first["score"] == [3, 2]
        assert first["state_name"] == "live"
        assert first["step"] == 100
        assert captured[1]["env_id"] == 1
        assert captured[1]["state_name"] == "scoring"


class TestEnvFramesQueueOnManager:
    """TrainingManager must expose env_frames_queue for the push loop."""

    def test_manager_constructs_bounded_queue(self):
        from backend.rl.trainer import TrainingManager

        mgr = TrainingManager(model_dir="/tmp/models_x", replay_dir="/tmp/replays_x")
        assert hasattr(mgr, "env_frames_queue")
        assert isinstance(mgr.env_frames_queue, asyncio.Queue)
        # Bounded so a slow WS subscriber can't blow memory.
        assert mgr.env_frames_queue.maxsize > 0


class TestEnvFramesPushLoop:
    """Handler wraps queued items as training:env_frame envelopes."""

    @pytest.mark.asyncio
    async def test_push_loop_broadcasts_envelope(self):
        from backend.app.ws.handlers import env_frames_push_loop

        queue: asyncio.Queue[dict] = asyncio.Queue()
        # Pre-load one item so the loop drains immediately.
        await queue.put({"env_id": 3, "frame": {"score1": 5}, "score": [5, 4], "state_name": "live"})

        manager = MagicMock()
        broadcasts: list[dict] = []

        async def _broadcast(payload):
            broadcasts.append(payload)
            # Cancel after first drain so the loop exits.
            raise asyncio.CancelledError

        manager.broadcast = _broadcast

        training_service = MagicMock()
        training_service.manager.env_frames_queue = queue

        with pytest.raises(asyncio.CancelledError):
            await env_frames_push_loop(manager, training_service)

        assert broadcasts == [
            {
                "type": "training:env_frame",
                "payload": {
                    "env_id": 3,
                    "frame": {"score1": 5},
                    "score": [5, 4],
                    "state_name": "live",
                },
            }
        ]

    @pytest.mark.asyncio
    async def test_push_loop_parks_when_queue_missing(self):
        """Older manager / test fake with no env_frames_queue → loop returns cleanly."""
        from backend.app.ws.handlers import env_frames_push_loop

        training_service = MagicMock()
        # Drop the attribute entirely so getattr returns None.
        del training_service.manager.env_frames_queue
        training_service.manager = MagicMock(spec=[])  # no attributes

        await env_frames_push_loop(MagicMock(), training_service)
        # If we got here, the loop exited gracefully — no hang, no crash.
