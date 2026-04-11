"""Model evaluation system for Pikachu Volleyball RL agents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from stable_baselines3 import PPO

from backend.game.constants import MAX_SCORE, NET_PILLAR_X
from backend.rl.env import PikachuVolleyballEnv


@dataclass
class EvalResult:
    model_path: str
    bot_level: int
    n_games: int
    win_rate: float
    avg_score: float
    avg_opponent_score: float
    avg_rally_length: float
    avg_episode_length: float
    timestamp: str


class ModelEvaluator:
    """Evaluate trained RL models against rule-based bots."""

    def evaluate(
        self, model_path: str, bot_level: int, n_games: int = 50
    ) -> EvalResult:
        """Load a model and run N games against a bot. Return aggregated results."""
        model = PPO.load(model_path)
        env = PikachuVolleyballEnv(bot_level=bot_level, max_steps=10000)

        wins: list[int] = []
        scores: list[int] = []
        opponent_scores: list[int] = []
        rally_lengths: list[int] = []
        episode_lengths: list[int] = []

        for _ in range(n_games):
            obs, _ = env.reset()
            rallies = 0
            prev_ball_side: bool | None = None  # True = right side

            terminated = False
            truncated = False
            while not terminated and not truncated:
                action, _ = model.predict(obs, deterministic=True)
                obs, _, terminated, truncated, info = env.step(int(action))

                # Track rallies: count net crossings
                ball_on_right = env._game._state.ball.x > NET_PILLAR_X
                if prev_ball_side is not None and ball_on_right != prev_ball_side:
                    rallies += 1
                prev_ball_side = ball_on_right

            final_score1 = info["score1"]
            final_score2 = info["score2"]

            wins.append(1 if final_score1 >= MAX_SCORE else 0)
            scores.append(final_score1)
            opponent_scores.append(final_score2)
            rally_lengths.append(rallies)
            episode_lengths.append(info["frame"])

        env.close()

        return EvalResult(
            model_path=model_path,
            bot_level=bot_level,
            n_games=n_games,
            win_rate=float(np.mean(wins)),
            avg_score=float(np.mean(scores)),
            avg_opponent_score=float(np.mean(opponent_scores)),
            avg_rally_length=float(np.mean(rally_lengths)),
            avg_episode_length=float(np.mean(episode_lengths)),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def evaluate_all_levels(
        self, model_path: str, n_games: int = 50
    ) -> list[EvalResult]:
        """Evaluate against all bot levels (1-5)."""
        return [
            self.evaluate(model_path, bot_level=level, n_games=n_games)
            for level in range(1, 6)
        ]

    def compare_checkpoints(
        self, model_paths: list[str], bot_level: int, n_games: int = 50
    ) -> list[EvalResult]:
        """Compare multiple model checkpoints under the same conditions."""
        return [
            self.evaluate(path, bot_level=bot_level, n_games=n_games)
            for path in model_paths
        ]
