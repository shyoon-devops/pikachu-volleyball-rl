"""Gymnasium environment for Pikachu Volleyball RL training."""

from __future__ import annotations

from typing import Any

import numpy as np

import gymnasium
from gymnasium import spaces

from backend.game.bot import RuleBasedBot
from backend.game.constants import (
    BALL_RADIUS,
    GROUND_HEIGHT,
    GROUND_WIDTH,
    MAX_SCORE,
    NET_PILLAR_X,
    PLAYER_HALF_LENGTH,
)
from backend.game.engine import PikachuVolleyball, PlayerInput

# Action mapping: 12 actions covering (x_dir, y_dir, power_hit) combos
# 0=noop, 1=left, 2=right, 3=jump, 4=left+jump, 5=right+jump,
# 6=power, 7=left+power, 8=right+power,
# 9=jump+power, 10=left+jump+power, 11=right+jump+power
ACTION_MAP: dict[int, PlayerInput] = {
    0: PlayerInput(x_dir=0, y_dir=0, power_hit=False),
    1: PlayerInput(x_dir=-1, y_dir=0, power_hit=False),
    2: PlayerInput(x_dir=1, y_dir=0, power_hit=False),
    3: PlayerInput(x_dir=0, y_dir=-1, power_hit=False),
    4: PlayerInput(x_dir=-1, y_dir=-1, power_hit=False),
    5: PlayerInput(x_dir=1, y_dir=-1, power_hit=False),
    6: PlayerInput(x_dir=0, y_dir=0, power_hit=True),
    7: PlayerInput(x_dir=-1, y_dir=0, power_hit=True),
    8: PlayerInput(x_dir=1, y_dir=0, power_hit=True),
    9: PlayerInput(x_dir=0, y_dir=-1, power_hit=True),
    10: PlayerInput(x_dir=-1, y_dir=-1, power_hit=True),
    11: PlayerInput(x_dir=1, y_dir=-1, power_hit=True),
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
            low=-1.0, high=1.0, shape=(18,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(12)

        self._game = PikachuVolleyball()
        self._bot = RuleBasedBot(level=bot_level)
        self._steps = 0
        self._prev_score1 = 0
        self._prev_score2 = 0
        self._prev_ball_x = 0.0
        self._prev_ball_y = 0.0
        self._prev_ball_vy = 0.0
        self._prev_p1_x = 0.0

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
        self._prev_ball_y = float(state.ball.y)
        self._prev_ball_vy = float(state.ball.vy)
        self._prev_p1_x = float(state.player1.x)
        return self._get_obs(state), {}

    def step(
        self, action: int
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        self._steps += 1

        p1_input = ACTION_MAP[int(action)]

        # Auto power-hit: if jumping and ball is close, force power_hit
        state = self._game._state
        p1 = state.player1
        ball = state.ball
        if p1.is_jumping and not p1_input.power_hit:
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
        self._prev_ball_y = float(new_state.ball.y)
        self._prev_ball_vy = float(new_state.ball.vy)
        self._prev_p1_x = float(new_state.player1.x)

        info: dict[str, Any] = {
            "score1": new_state.score1,
            "score2": new_state.score2,
            "frame": new_state.frame,
        }

        return obs, reward, terminated, truncated, info

    def _get_obs(self, state: Any) -> np.ndarray:
        """Normalize game state to [-1, 1] observation vector (18 floats).

        Layout:
          [0-4]   Player 1: x, y, vx, vy, airborne_state
          [5-7]   Player 2: x, y, vy
          [8-11]  Ball: x, y, vx, vy
          [12-13] Ball trajectory delta: dx, dy
          [14-15] Ball-agent relationship: relative_x, ball_side
          [16-17] Game state: score_diff, serving
        """
        w = float(GROUND_WIDTH)
        h = float(GROUND_HEIGHT)
        max_v = 20.0

        # Player airborne state: jumping=1, diving=-1, grounded=0
        if state.player1.is_jumping:
            p1_air = 1.0
        elif state.player1.is_diving:
            p1_air = -1.0
        else:
            p1_air = 0.0

        obs = np.array(
            [
                # Player 1 (agent) — 5 values
                state.player1.x / w * 2 - 1,
                state.player1.y / h * 2 - 1,
                np.clip(state.player1.vx / max_v, -1, 1),
                np.clip(state.player1.vy / max_v, -1, 1),
                p1_air,
                # Player 2 (opponent) — 3 values
                state.player2.x / w * 2 - 1,
                state.player2.y / h * 2 - 1,
                np.clip(state.player2.vy / max_v, -1, 1),
                # Ball — 4 values
                state.ball.x / w * 2 - 1,
                state.ball.y / h * 2 - 1,
                np.clip(state.ball.vx / max_v, -1, 1),
                np.clip(state.ball.vy / max_v, -1, 1),
                # Ball trajectory delta — 2 values
                np.clip(
                    (float(state.ball.x) - self._prev_ball_x) / max_v, -1, 1
                ),
                np.clip(
                    (float(state.ball.y) - self._prev_ball_y) / max_v, -1, 1
                ),
                # Ball-agent relationship — 2 values
                np.clip(
                    (float(state.ball.x) - float(state.player1.x)) / w, -1, 1
                ),
                1.0 if state.ball.x <= NET_PILLAR_X else -1.0,
                # Game state — 2 values
                np.clip((state.score1 - state.score2) / MAX_SCORE, -1, 1),
                1.0 if state.serving_player == 1 else -1.0,
            ],
            dtype=np.float32,
        )
        return np.clip(obs, -1.0, 1.0)

    def _compute_reward(self, state: Any) -> float:
        """Compute shaped reward for faster PPO convergence.

        Reward hierarchy (largest to smallest):
          1. Game outcome:  win +20 / loss -20
          2. Scoring:       score +10 / concede -10
          3. Ball touch:    successful hit +3.0  (once per collision)
          4. Net crossing:  ball sent to opponent's court +1.0
          5. Approach ball: move toward ball on own side +0.05/frame
          6. Ready position: near court center when ball on opp side +0.01
        """
        reward = 0.0
        ball = state.ball
        p1 = state.player1

        # --- PRIMARY: scoring events ---
        scored = state.score1 - self._prev_score1
        conceded = state.score2 - self._prev_score2
        if scored > 0:
            reward += 10.0
        if conceded > 0:
            reward -= 10.0
        if state.score1 >= MAX_SCORE:
            reward += 20.0
        elif state.score2 >= MAX_SCORE:
            reward -= 20.0

        # --- AUX 1: ball touch (vy-flip detection) ---
        # Engine sets ball.vy = min(vy, -15) on player collision.
        # Detect: ball was falling/flat, now sharply upward, near player1.
        collision_dist = PLAYER_HALF_LENGTH + BALL_RADIUS
        if self._prev_ball_vy >= 0 and ball.vy <= -14:
            if abs(ball.x - p1.x) < collision_dist * 3:
                reward += 3.0

        # --- AUX 2: net crossing ---
        prev_on_p1_side = self._prev_ball_x <= NET_PILLAR_X
        now_on_p2_side = ball.x > NET_PILLAR_X
        if prev_on_p1_side and now_on_p2_side and ball.vx > 0:
            reward += 1.0

        # --- AUX 3: approach ball (gradient for early training) ---
        if ball.x <= NET_PILLAR_X and not state.is_round_over:
            prev_dist = abs(self._prev_ball_x - self._prev_p1_x)
            curr_dist = abs(float(ball.x) - float(p1.x))
            if curr_dist < prev_dist:
                reward += 0.05

        # --- AUX 4: ready position (defensive positioning) ---
        if ball.x > NET_PILLAR_X and not state.is_round_over:
            ready_x = NET_PILLAR_X * 0.5
            dist_from_ready = abs(float(p1.x) - ready_x)
            max_dist = NET_PILLAR_X * 0.5
            reward += 0.01 * max(0.0, 1.0 - dist_from_ready / max_dist)

        return float(reward)
