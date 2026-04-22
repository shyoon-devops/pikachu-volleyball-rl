"""Regression pin for the self-play Monitor wrap.

Background: the self-play VecEnv path in TrainingManager._train_loop
constructs a DummyVecEnv directly (to keep a shared in-process
PFSPProvider) instead of calling ``make_vec_env``. ``make_vec_env``
transparently wraps each env in SB3's ``Monitor``, which is what
injects ``info["episode"]`` on natural terminations — the signal the
_PausePoke callback reads to drive ``manager.current_episode``.

Dropping the Monitor wrap was the root cause of a bug where step
counted up normally during self-play training but episode stayed at 0
(PM report 2026-04-18, run-quiet-lynx-38b8). This test fails loudly
if someone drops the wrap again.
"""

from __future__ import annotations

import numpy as np
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from backend.rl.env import PikachuVolleyballEnv
from backend.rl.opponent import FixedBotProvider


def _build_self_play_vec_env(n_envs: int = 2) -> DummyVecEnv:
    """Mirror ``TrainingManager._train_loop``'s self-play construction."""

    def _make_one(i: int):
        def _f():
            base_env = PikachuVolleyballEnv(
                bot_level=1,
                opponent_provider=FixedBotProvider(level=1),
                env_index=i,
            )
            return Monitor(base_env)

        return _f

    return DummyVecEnv([_make_one(i) for i in range(n_envs)])


class TestSelfPlayMonitorWrap:
    def test_episode_key_observed_within_bounded_steps(self) -> None:
        """info['episode'] must fire at least once before max_steps * 2.

        A 3000-step episode cap × 2 gives enough headroom for either
        env to terminate naturally at least once under NOOP input.
        If Monitor is missing, ``info['episode']`` never shows up and
        this test hangs / fails.
        """
        env = _build_self_play_vec_env(n_envs=2)
        env.reset()
        seen = 0
        for _ in range(6000):
            _obs, _r, _dones, infos = env.step(np.array([0, 0]))
            for info in infos:
                if "episode" in info:
                    seen += 1
            if seen >= 1:
                break
        env.close()
        assert seen >= 1, (
            "self-play DummyVecEnv did not emit info['episode'] — "
            "Monitor wrapping dropped"
        )

    def test_monitor_injects_reward_and_length(self) -> None:
        """Spot-check that info['episode'] has the expected SB3 shape.

        Monitor surfaces ``{"r": float, "l": int, "t": float}`` —
        downstream MetricsCallback reads ``r`` for the episode-reward
        moving average. If the key names drift we'd want to know.
        """
        env = _build_self_play_vec_env(n_envs=1)
        env.reset()
        episode_info: dict | None = None
        for _ in range(6000):
            _obs, _r, _dones, infos = env.step(np.array([0]))
            for info in infos:
                if "episode" in info:
                    episode_info = info["episode"]
                    break
            if episode_info is not None:
                break
        env.close()
        assert episode_info is not None, "no episode info seen"
        assert "r" in episode_info
        assert "l" in episode_info
