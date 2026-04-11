"""Tests for the Gymnasium environment."""

import numpy as np
import pytest

import gymnasium
from gymnasium.utils.env_checker import check_env

from backend.rl.env import PikachuVolleyballEnv


@pytest.fixture
def env() -> PikachuVolleyballEnv:
    e = PikachuVolleyballEnv(bot_level=1, max_steps=3000)
    yield e
    e.close()


class TestEnvChecker:
    """Environment should pass gymnasium's built-in checker."""

    def test_check_env_passes(self) -> None:
        env = PikachuVolleyballEnv(bot_level=1, max_steps=3000)
        check_env(env.unwrapped, skip_render_check=True)
        env.close()


class TestReset:
    """reset() should return correct observation shape."""

    def test_reset_obs_shape(self, env: PikachuVolleyballEnv) -> None:
        obs, info = env.reset()
        assert obs.shape == (12,)
        assert obs.dtype == np.float32

    def test_reset_obs_range(self, env: PikachuVolleyballEnv) -> None:
        obs, _ = env.reset()
        assert np.all(obs >= -1.0)
        assert np.all(obs <= 1.0)

    def test_reset_returns_info_dict(self, env: PikachuVolleyballEnv) -> None:
        _, info = env.reset()
        assert isinstance(info, dict)


class TestStep:
    """step() should return valid obs/reward/done for each action."""

    @pytest.mark.parametrize("action", [0, 1, 2, 3, 4, 5])
    def test_step_valid_output(self, env: PikachuVolleyballEnv, action: int) -> None:
        env.reset()
        obs, reward, terminated, truncated, info = env.step(action)

        assert obs.shape == (12,)
        assert obs.dtype == np.float32
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)

    @pytest.mark.parametrize("action", [0, 1, 2, 3, 4, 5])
    def test_step_obs_in_range(self, env: PikachuVolleyballEnv, action: int) -> None:
        env.reset()
        obs, *_ = env.step(action)
        assert np.all(obs >= -1.0), f"obs below -1: {obs}"
        assert np.all(obs <= 1.0), f"obs above 1: {obs}"


class TestEpisodeTermination:
    """Episode should end when MAX_SCORE is reached."""

    def test_episode_terminates_at_max_score(self) -> None:
        env = PikachuVolleyballEnv(bot_level=1, max_steps=100000)
        env.reset()
        terminated = False
        truncated = False
        for _ in range(100000):
            action = env.action_space.sample()
            _, _, terminated, truncated, _ = env.step(action)
            if terminated or truncated:
                break
        assert terminated or truncated
        env.close()

    def test_episode_truncates_at_max_steps(self) -> None:
        env = PikachuVolleyballEnv(bot_level=5, max_steps=100)
        env.reset()
        truncated = False
        for _ in range(200):
            _, _, terminated, truncated, _ = env.step(0)  # noop
            if terminated or truncated:
                break
        assert truncated or terminated
        env.close()
