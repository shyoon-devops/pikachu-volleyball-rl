"""Gymnasium environment for Pikachu Volleyball RL training."""

from __future__ import annotations

from typing import Any

import numpy as np

import gymnasium
from gymnasium import spaces

from backend.game.bot import RuleBasedBot
from backend.game.constants import (
    GROUND_HEIGHT,
    GROUND_WIDTH,
    MAX_SCORE,
    NET_PILLAR_X,
)
from backend.game.engine import PikachuVolleyball, PlayerInput

# Action mapping: 0=noop, 1=left, 2=right, 3=jump, 4=left+jump, 5=right+jump
ACTION_MAP: dict[int, PlayerInput] = {
    0: PlayerInput(x_dir=0, y_dir=0, power_hit=False),
    1: PlayerInput(x_dir=-1, y_dir=0, power_hit=False),
    2: PlayerInput(x_dir=1, y_dir=0, power_hit=False),
    3: PlayerInput(x_dir=0, y_dir=-1, power_hit=False),
    4: PlayerInput(x_dir=-1, y_dir=-1, power_hit=False),
    5: PlayerInput(x_dir=1, y_dir=-1, power_hit=False),
}


class PikachuVolleyballEnv(gymnasium.Env):
    """Pikachu Volleyball as a Gymnasium environment.

    Player 1 (left) is the RL agent. Player 2 (right) is the rule-based bot.
    """

    metadata: dict[str, Any] = {"render_modes": []}

    def __init__(self, bot_level: int = 1, max_steps: int = 3000) -> None:
        super().__init__()
        self.bot_level = bot_level
        self.max_steps = max_steps

        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(12,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(6)

        self._game = PikachuVolleyball()
        self._bot = RuleBasedBot(level=bot_level)
        self._steps = 0
        self._prev_score1 = 0
        self._prev_score2 = 0
        self._prev_ball_x = 0.0

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed, options=options)
        self._game = PikachuVolleyball()
        self._bot = RuleBasedBot(level=self.bot_level)
        state = self._game.reset()
        self._steps = 0
        self._prev_score1 = 0
        self._prev_score2 = 0
        self._prev_ball_x = float(state.ball.x)
        return self._get_obs(state), {}

    def step(
        self, action: int
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        self._steps += 1

        p1_input = ACTION_MAP[int(action)]

        # Auto power-hit: if jumping and ball is close
        state = self._game._state
        p1 = state.player1
        ball = state.ball
        if p1.is_jumping:
            dist_x = abs(ball.x - p1.x)
            dist_y = abs(ball.y - p1.y)
            if dist_x < 60 and dist_y < 60:
                p1_input = PlayerInput(
                    x_dir=p1_input.x_dir,
                    y_dir=p1_input.y_dir,
                    power_hit=True,
                )

        p2_input = self._bot.get_action(state, is_player2=True)
        new_state = self._game.step(p1_input, p2_input)

        obs = self._get_obs(new_state)
        reward = self._compute_reward(new_state)
        terminated = new_state.score1 >= MAX_SCORE or new_state.score2 >= MAX_SCORE
        truncated = self._steps >= self.max_steps

        self._prev_score1 = new_state.score1
        self._prev_score2 = new_state.score2
        self._prev_ball_x = float(new_state.ball.x)

        info: dict[str, Any] = {
            "score1": new_state.score1,
            "score2": new_state.score2,
            "frame": new_state.frame,
        }

        return obs, reward, terminated, truncated, info

    def _get_obs(self, state: Any) -> np.ndarray:
        """Normalize game state to [-1, 1] observation vector."""
        w = float(GROUND_WIDTH)
        h = float(GROUND_HEIGHT)
        max_v = 20.0  # reasonable velocity clamp

        obs = np.array(
            [
                state.player1.x / w * 2 - 1,
                state.player1.y / h * 2 - 1,
                np.clip(state.player1.vx / max_v, -1, 1),
                np.clip(state.player1.vy / max_v, -1, 1),
                state.player2.x / w * 2 - 1,
                state.player2.y / h * 2 - 1,
                state.ball.x / w * 2 - 1,
                state.ball.y / h * 2 - 1,
                np.clip(state.ball.vx / max_v, -1, 1),
                np.clip(state.ball.vy / max_v, -1, 1),
                np.clip((state.score1 - state.score2) / MAX_SCORE, -1, 1),
                1.0 if state.serving_player == 1 else -1.0,
            ],
            dtype=np.float32,
        )
        return np.clip(obs, -1.0, 1.0)

    def _compute_reward(self, state: Any) -> float:
        """Compute reward based on game events."""
        reward = 0.0

        # Scoring events
        scored = state.score1 - self._prev_score1
        conceded = state.score2 - self._prev_score2

        if scored > 0:
            reward += 10.0
        if conceded > 0:
            reward -= 10.0

        # Game win/loss bonus
        if state.score1 >= MAX_SCORE:
            reward += 20.0
        elif state.score2 >= MAX_SCORE:
            reward -= 20.0

        # Ball touch (rally) — ball changed direction near player
        ball = state.ball
        p1 = state.player1
        if abs(ball.x - p1.x) < 60 and abs(ball.y - p1.y) < 60 and ball.vy < 0:
            reward += 0.5

        # Ball on opponent's side
        if ball.x > NET_PILLAR_X:
            reward += 0.1

        # Time penalty
        reward -= 0.01

        return float(reward)
