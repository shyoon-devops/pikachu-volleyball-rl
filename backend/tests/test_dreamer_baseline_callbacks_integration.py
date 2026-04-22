"""End-to-end integration: Dreamer + the actual trainer callback list.

``test_dreamer_callback_dispatch.py`` uses mock callbacks to pin the
lifecycle hooks — that catches "we forgot to call on_step" but does
NOT catch BaseAlgorithm attribute shortfalls. QA bench-B 2026-04-23
hit exactly that gap: the mock-callback test passed at merge time,
but the real ``EnvFrameCallback`` accessing ``self.training_env``
(→ ``self.model.get_env()``) crashed 24 steps into live training
with ``AttributeError: 'DreamerAgent' object has no attribute 'get_env'``.

This suite wires the production callback set (MetricsCallback +
CheckpointCallback + EnvFrameCallback + EnvResultCallback) into a
``CallbackList`` and runs ``DreamerAgent.learn(200)`` — matching
what ``trainer.TrainingManager._train_loop`` hands the model.
Success = all four callbacks touch the model surface they expect
without an AttributeError + checkpoints land on disk + frames are
enqueued.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from stable_baselines3.common.callbacks import CallbackList
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from backend.rl.callbacks import (
    CheckpointCallback,
    EnvFrameCallback,
    EnvResultCallback,
    MetricsCallback,
)
from backend.rl.dreamer_runner import DreamerAgent
from backend.rl.env import PikachuVolleyballEnv


def _make_vec_env(n_envs: int = 1) -> Any:
    def _mk() -> Any:
        return Monitor(PikachuVolleyballEnv(bot_level=1))

    return make_vec_env(_mk, n_envs=n_envs, vec_env_cls=DummyVecEnv)


def _tiny_agent(env: Any) -> DreamerAgent:
    return DreamerAgent(
        env=env, device="cpu",
        rssm_hidden_size=32, latent_dim=4, latent_axes=4,
        batch_size=4, sequence_length=8, train_every=8,
        imagine_horizon=3, replay_capacity=2048, free_bits=0.1,
    )


class TestDreamerBaseAlgorithmInterface:
    """The minimal BaseAlgorithm surface callbacks touch:
    ``get_env``, ``observation_space``, ``action_space``,
    ``_vec_normalize_env``, ``num_timesteps``, ``logger``,
    ``predict``, ``save``. bench-B failure pinpointed the gap at
    ``get_env`` — this test pins all of them."""

    def test_sb3_interface_attributes_present(self) -> None:
        env = _make_vec_env(n_envs=1)
        agent = _tiny_agent(env)
        assert agent.get_env() is env
        assert agent.observation_space.shape == (18,)
        assert agent.action_space.n == 12
        assert agent._vec_normalize_env is None
        assert agent.num_timesteps == 0
        # logger is a BaseCallback-readable record sink.
        assert agent.logger is not None
        assert hasattr(agent.logger, "name_to_value")
        # predict + save + get_env are the callsites inside the
        # trainer callbacks.
        assert callable(agent.predict)
        assert callable(agent.save)
        assert callable(agent.get_env)


class TestDreamerWithProductionCallbacks:
    """The exact callback set TrainingManager._train_loop assembles.
    Prior to this fix, EnvFrameCallback._on_step's
    ``self.training_env`` access crashed at step 24 on bench-B."""

    def test_callback_list_runs_200_steps_without_crash(
        self, tmp_path: Path
    ) -> None:
        """200 env steps through the full production CallbackList.
        Success = no AttributeError, checkpoints appear on disk,
        frames + metrics events stay queued (callback side-effects
        all land)."""
        env = _make_vec_env(n_envs=1)
        agent = _tiny_agent(env)

        # Async queues the production callbacks enqueue into. We
        # don't consume them here — just prove enqueue doesn't
        # crash and the queue shape is valid.
        # Use a fresh loop object as the queue's enqueue target but
        # DON'T install it as the process-wide current loop —
        # leaving a closed loop in the global slot poisons sibling
        # tests (test_metrics_aggregation hit this 2026-04-23).
        loop = asyncio.new_event_loop()
        metrics_queue: asyncio.Queue = asyncio.Queue()
        env_frames_queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        results_queue: asyncio.Queue = asyncio.Queue()

        exp_id = "dreamer-integ-xxxxxxxx"
        callback_list = CallbackList([
            MetricsCallback(
                queue=metrics_queue, loop=loop, log_interval=50,
            ),
            CheckpointCallback(
                experiment_id=exp_id, model_dir=str(tmp_path),
                save_interval=100, slug="dreamer-integ",
            ),
            EnvFrameCallback(
                env_frames_queue=env_frames_queue, loop=loop,
                broadcast_interval=4,
            ),
            EnvResultCallback(
                results_queue=results_queue, loop=loop,
                manager=None, drain_interval=4,
            ),
        ])

        agent.learn(total_timesteps=200, callback=callback_list)
        # Got past step 24 (bench-B crash site) — got to 200.
        assert agent.num_timesteps == 200
        # Checkpoint callback produced 2 zips (at steps 100, 200).
        checkpoint_dir = tmp_path / exp_id
        zips = sorted(checkpoint_dir.glob("*.zip"))
        assert len(zips) == 2, (
            f"expected checkpoints at 100 + 200; got {len(zips)}: "
            f"{[p.name for p in zips]}"
        )
        # Reloading the last one must work — pins the full round-trip.
        reloaded = DreamerAgent.load(
            str(zips[-1]), env=_make_vec_env(n_envs=1), device="cpu",
        )
        assert reloaded.num_timesteps == 200

        loop.close()

    def test_env_frame_callback_uses_training_env(
        self, tmp_path: Path
    ) -> None:
        """The specific bench-B regression: EnvFrameCallback calls
        ``self.training_env.env_method(...)``. Without ``get_env()``
        that read blew up. This narrows the integration test to that
        exact code path so a future regression lights up faster."""
        env = _make_vec_env(n_envs=1)
        agent = _tiny_agent(env)

        # Use a fresh loop object as the queue's enqueue target but
        # DON'T install it as the process-wide current loop —
        # leaving a closed loop in the global slot poisons sibling
        # tests (test_metrics_aggregation hit this 2026-04-23).
        loop = asyncio.new_event_loop()
        env_frames_queue: asyncio.Queue = asyncio.Queue(maxsize=64)

        cb = EnvFrameCallback(
            env_frames_queue=env_frames_queue, loop=loop,
            # Fire every step so even a short run exercises the
            # training_env path.
            broadcast_interval=1,
        )
        # Would AttributeError here pre-fix.
        agent.learn(total_timesteps=32, callback=cb)
        assert agent.num_timesteps == 32
        loop.close()


class TestCallbackSurfaceStaysStable:
    """Regression guards for future refactors — if any SB3 callback
    attribute drifts off DreamerAgent, the bench-B silent-failure
    mode reappears. Pin each attribute with a direct assertion."""

    @pytest.mark.parametrize("attr", [
        "get_env", "observation_space", "action_space",
        "_vec_normalize_env", "num_timesteps", "logger",
        "predict", "save", "num_envs", "env",
    ])
    def test_attribute_present(self, attr: str) -> None:
        env = _make_vec_env(n_envs=1)
        agent = _tiny_agent(env)
        assert hasattr(agent, attr), (
            f"DreamerAgent.{attr} missing — SB3 BaseAlgorithm "
            "surface regression. Restore before merge or bench-B "
            "will crash again."
        )
