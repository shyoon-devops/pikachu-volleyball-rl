"""SB3 BaseCallback protocol coverage for ``DreamerAgent.learn``.

QA bench-B 2026-04-23 hit a silent failure: Dreamer V3 training
ran to completion but ``MetricsCallback`` / ``CheckpointCallback``
never fired — ``manager.current_step`` stayed at 0 so the
dashboard showed no progress, and a 2M run that crashed mid-way
had zero intermediate checkpoints. Root cause: ``learn()`` never
called the ``BaseCallback`` protocol methods.

This suite pins the wire so the silent failure mode can't
reappear — every lifecycle hook fires, ``num_timesteps``
propagates to the callback, and ``False`` from ``on_step`` is
honoured as an early-stop signal (matches SB3 contract used by
``_StopEventCallback`` in trainer.py).
"""

from __future__ import annotations

from typing import Any

from stable_baselines3.common.callbacks import BaseCallback, CallbackList
from stable_baselines3.common.vec_env import DummyVecEnv

from backend.rl.dreamer_runner import DreamerAgent
from backend.rl.env import PikachuVolleyballEnv


def _make_env() -> Any:
    return DummyVecEnv([lambda: PikachuVolleyballEnv(bot_level=1)])


def _tiny_agent() -> DreamerAgent:
    return DreamerAgent(
        env=_make_env(),
        device="cpu",
        rssm_hidden_size=32, latent_dim=4, latent_axes=4,
        batch_size=4, sequence_length=8, train_every=8,
        imagine_horizon=3, replay_capacity=512, free_bits=0.1,
    )


class _CountingCallback(BaseCallback):
    """Records every lifecycle hit so tests can assert precise counts
    + num_timesteps propagation."""

    def __init__(self) -> None:
        super().__init__(verbose=0)
        self.step_count = 0
        self.training_start_count = 0
        self.training_end_count = 0
        self.num_timesteps_history: list[int] = []

    def _on_step(self) -> bool:
        self.step_count += 1
        # SB3 updates ``self.num_timesteps`` from model before
        # calling ``_on_step`` — snapshot it to verify propagation.
        self.num_timesteps_history.append(int(self.num_timesteps))
        return True

    def _on_training_start(self) -> None:
        self.training_start_count += 1

    def _on_training_end(self) -> None:
        self.training_end_count += 1


class TestCallbackLifecycle:
    def test_on_step_fires_once_per_collect_step(self) -> None:
        """100 env-step learn → 100 on_step calls. One-to-one with
        VecEnv ``_collect_step`` so callbacks see the same cadence
        that PPO / SAC have."""
        agent = _tiny_agent()
        cb = _CountingCallback()
        agent.learn(total_timesteps=100, callback=cb)
        assert cb.step_count == 100

    def test_training_start_and_end_each_fire_exactly_once(self) -> None:
        agent = _tiny_agent()
        cb = _CountingCallback()
        agent.learn(total_timesteps=32, callback=cb)
        assert cb.training_start_count == 1
        assert cb.training_end_count == 1

    def test_num_timesteps_propagates_to_callback(self) -> None:
        """BaseCallback reads ``self.model.num_timesteps`` before
        every ``_on_step``. Dashboards + _StopEventCallback rely on
        this (MetricsCallback writes ``manager.current_step`` off
        it)."""
        agent = _tiny_agent()
        cb = _CountingCallback()
        agent.learn(total_timesteps=50, callback=cb)
        # n_envs=1 → each step increments by 1. Last recorded
        # num_timesteps equals model.num_timesteps equals 50.
        assert cb.num_timesteps_history[-1] == 50
        assert cb.num_timesteps_history[-1] == agent.num_timesteps
        # Monotonic nondecreasing (within n_envs stride).
        assert cb.num_timesteps_history == sorted(cb.num_timesteps_history)

    def test_on_step_false_aborts_training(self) -> None:
        """Matching SB3's contract: any child callback returning
        False halts ``learn()`` early. ``_StopEventCallback`` uses
        this to propagate the manager's stop request."""

        class _StopAfterTen(BaseCallback):
            def __init__(self) -> None:
                super().__init__(verbose=0)
                self.calls = 0

            def _on_step(self) -> bool:
                self.calls += 1
                return self.calls < 10

        agent = _tiny_agent()
        cb = _StopAfterTen()
        agent.learn(total_timesteps=1000, callback=cb)
        # Stops on the 10th call (which returns False).
        assert cb.calls == 10
        assert agent.num_timesteps < 1000


class TestCallbackList:
    """``CallbackList`` is the container trainer.py passes to
    ``model.learn`` (MetricsCallback + CheckpointCallback +
    LiveFrameCallback + _StopEventCallback at once). The handshake
    must forward to every child."""

    def test_callback_list_forwards_all_lifecycle_hooks(self) -> None:
        agent = _tiny_agent()
        cb_a = _CountingCallback()
        cb_b = _CountingCallback()
        agent.learn(total_timesteps=20, callback=CallbackList([cb_a, cb_b]))
        for cb in (cb_a, cb_b):
            assert cb.step_count == 20
            assert cb.training_start_count == 1
            assert cb.training_end_count == 1


class TestNoCallback:
    """Backward-compat: ``callback=None`` must still work — tests
    that don't supply a callback shouldn't blow up."""

    def test_no_callback_runs_cleanly(self) -> None:
        agent = _tiny_agent()
        agent.learn(total_timesteps=20)  # no callback kwarg
        assert agent.num_timesteps == 20
