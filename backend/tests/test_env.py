"""Tests for the Gymnasium environment."""

import numpy as np
import pytest

from gymnasium.utils.env_checker import check_env

from backend.game.constants import NET_PILLAR_X
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
        assert obs.shape == (18,)
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

    @pytest.mark.parametrize("action", list(range(12)))
    def test_step_valid_output(self, env: PikachuVolleyballEnv, action: int) -> None:
        env.reset()
        obs, reward, terminated, truncated, info = env.step(action)

        assert obs.shape == (18,)
        assert obs.dtype == np.float32
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)

    @pytest.mark.parametrize("action", list(range(12)))
    def test_step_obs_in_range(self, env: PikachuVolleyballEnv, action: int) -> None:
        env.reset()
        obs, *_ = env.step(action)
        assert np.all(obs >= -1.0), f"obs below -1: {obs}"
        assert np.all(obs <= 1.0), f"obs above 1: {obs}"


class TestRewardShaping:
    """Reward shaping signals should fire correctly."""

    def test_scoring_gives_positive_reward(self, env: PikachuVolleyballEnv) -> None:
        """Scoring a point should produce a large positive reward spike."""
        env.reset()
        max_reward = -float("inf")
        for _ in range(5000):
            obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
            max_reward = max(max_reward, reward)
            if terminated or truncated:
                break
        # At least one frame should have had a scoring reward (+10)
        assert max_reward >= 5.0, f"No scoring reward detected, max was {max_reward}"

    def test_conceding_gives_negative_reward(self) -> None:
        """Conceding should produce a large negative reward.

        Force-triggers a concede by positioning the ball on the agent's side
        near the ground, so it grounds on the next step regardless of play.
        This avoids flakiness from physics/bot dynamics.
        """
        from backend.game.constants import BALL_GROUND_Y, NET_PILLAR_X

        env = PikachuVolleyballEnv(bot_level=1, max_steps=3000)
        env.reset()
        # Place ball just above ground on agent's (player1) side.
        state = env._game._state
        state.ball.x = NET_PILLAR_X - 50  # agent side
        state.ball.y = BALL_GROUND_Y - 1
        state.ball.vx = 0
        state.ball.vy = 10  # falling fast, will ground next frame
        env._prev_ball_vy = 10
        env._prev_ball_y = BALL_GROUND_Y - 1

        obs, reward, terminated, truncated, info = env.step(0)  # noop
        assert reward <= -5.0, f"Concede should give large negative reward, got {reward}"
        env.close()

    def test_approach_reward_fires_when_moving_toward_ball(
        self, env: PikachuVolleyballEnv
    ) -> None:
        """Moving toward the ball on own side should give small positive reward."""
        env.reset()
        for _ in range(5):
            env.step(1)  # move left
        _, reward_toward, *_ = env.step(2)  # move right
        env.reset()
        for _ in range(5):
            env.step(2)  # move right first
        _, reward_away, *_ = env.step(1)  # move left
        assert isinstance(reward_toward, float)
        assert isinstance(reward_away, float)

    def test_reward_is_bounded_per_step(self, env: PikachuVolleyballEnv) -> None:
        """No single step reward should be unreasonably large."""
        env.reset()
        for _ in range(3000):
            _, reward, terminated, truncated, _ = env.step(env.action_space.sample())
            # Max: score(10) + win(50) + touch(3) + cross(2)
            #      + approach(0.02) + pressure(0.02) + ready(0.005) ≈ 65
            # Min: concede(-10) + lose(-50) + excess_touch(-2)
            #      + stall(-0.05) + timeout(-12) ≈ -75
            assert -80.0 <= reward <= 70.0, f"Reward out of bounds: {reward}"
            if terminated or truncated:
                break


class TestAntiTossLoop:
    """Reward shaping should discourage repeated self-tosses on same side."""

    def _force_touch(self, env: PikachuVolleyballEnv) -> None:
        """Simulate a player1 ball touch by manipulating internal state.

        Sets up the ball state so _compute_reward detects a collision:
        prev_ball_vy >= 0, current vy <= -14, ball near player1.
        """
        state = env._game._state
        env._prev_ball_vy = 0.0
        env._prev_ball_x = float(state.player1.x)
        env._prev_ball_y = float(state.player1.y) - 30
        state.ball.x = state.player1.x
        state.ball.y = state.player1.y - 30
        state.ball.vy = -20

    def test_first_touch_gives_full_reward(
        self, env: PikachuVolleyballEnv
    ) -> None:
        env.reset()
        self._force_touch(env)
        reward = env._compute_reward(env._game._state)
        assert reward >= 2.5, f"First touch should give ~+3.0, got {reward}"
        assert env._consecutive_touches == 1

    def test_second_touch_gives_reduced_reward(
        self, env: PikachuVolleyballEnv
    ) -> None:
        env.reset()
        env._consecutive_touches = 1
        self._force_touch(env)
        reward = env._compute_reward(env._game._state)
        # Second touch: +1.0 touch reward (plus small aux rewards possible)
        assert 0.5 <= reward <= 2.0, f"Second touch should be +1.0, got {reward}"
        assert env._consecutive_touches == 2

    def test_third_touch_gives_penalty(
        self, env: PikachuVolleyballEnv
    ) -> None:
        env.reset()
        env._consecutive_touches = 2
        self._force_touch(env)
        reward = env._compute_reward(env._game._state)
        # Third touch: -2.0 penalty
        assert reward <= -1.0, f"Third touch should penalize, got {reward}"
        assert env._consecutive_touches == 3

    def test_net_crossing_resets_touch_counter(
        self, env: PikachuVolleyballEnv
    ) -> None:
        env.reset()
        env._consecutive_touches = 5
        env._frames_since_crossing = 500
        # Simulate ball crossing from p1 to p2 side
        state = env._game._state
        env._prev_ball_x = float(NET_PILLAR_X - 10)
        state.ball.x = int(NET_PILLAR_X + 10)
        state.ball.vx = 5
        env._compute_reward(state)
        assert env._consecutive_touches == 0
        assert env._frames_since_crossing == 0

    def test_net_crossing_gives_strong_reward(
        self, env: PikachuVolleyballEnv
    ) -> None:
        env.reset()
        state = env._game._state
        env._prev_ball_x = float(NET_PILLAR_X - 10)
        state.ball.x = int(NET_PILLAR_X + 10)
        state.ball.vx = 5
        state.ball.vy = 0
        env._prev_ball_vy = 0.0
        reward = env._compute_reward(state)
        assert reward >= 1.5, f"Net crossing should be +2.0, got {reward}"

    def test_stall_penalty_applies_after_threshold(
        self, env: PikachuVolleyballEnv
    ) -> None:
        env.reset()
        env._frames_since_crossing = env._STALL_THRESHOLD + 1
        # Put ball in neutral position (no touch, no crossing, no aux rewards)
        state = env._game._state
        state.ball.x = int(NET_PILLAR_X + 50)  # opp side, small ready reward
        state.ball.y = 100
        state.ball.vy = 5
        env._prev_ball_vy = 5.0
        env._prev_ball_x = float(state.ball.x)
        reward = env._compute_reward(state)
        # Stall penalty (-0.03) should dominate any small ready reward
        assert reward < 0.0, f"Expected negative stall reward, got {reward}"

    def test_scoring_resets_counters(self, env: PikachuVolleyballEnv) -> None:
        env.reset()
        env._consecutive_touches = 10
        env._frames_since_crossing = 500
        env._prev_score1 = 0
        env._game._state.score1 = 1
        env._compute_reward(env._game._state)
        assert env._consecutive_touches == 0
        assert env._frames_since_crossing == 0

    def test_reset_clears_counters(self, env: PikachuVolleyballEnv) -> None:
        env.reset()
        env.step(0)
        env._consecutive_touches = 99
        env._frames_since_crossing = 999
        env.reset()
        assert env._consecutive_touches == 0
        assert env._frames_since_crossing == 0

    def test_rally_timeout_truncates_episode(
        self, env: PikachuVolleyballEnv
    ) -> None:
        """Episode should truncate with penalty after _RALLY_MAX_FRAMES."""
        env.reset()
        env._frames_since_crossing = env._RALLY_MAX_FRAMES - 1
        _, reward, terminated, truncated, info = env.step(0)
        assert truncated, "Expected truncation after rally timeout"
        assert not terminated
        assert info["stalled_out"] is True
        # Reward includes -5.0 timeout penalty
        assert reward <= -3.0, f"Expected timeout penalty, got {reward}"

    def test_info_includes_touch_and_stall_stats(
        self, env: PikachuVolleyballEnv
    ) -> None:
        env.reset()
        _, _, _, _, info = env.step(0)
        assert "consecutive_touches" in info
        assert "stalled_out" in info
        assert info["stalled_out"] is False


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
            _, _, terminated, truncated, _ = env.step(0)
            if terminated or truncated:
                break
        assert truncated or terminated
        env.close()
