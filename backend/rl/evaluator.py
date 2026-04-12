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
    # Composite metric in [0.0, 1.0] capturing both win frequency
    # and margin of victory. See `compute_dominance_score`.
    dominance_score: float = 0.0


def compute_dominance_score(
    win_rate: float, avg_score: float, avg_opponent_score: float
) -> float:
    """Composite dominance metric in [0.0, 1.0].

    Blends win frequency (60%) with point share (40%) so that:
      - 100% wins, 15-0 blowout       -> 1.00
      - 100% wins, 15-14 close games  -> 0.81
      -  50% wins, even point split   -> 0.50
      -   0% wins, 0-15 sweep         -> 0.00

    Point share = avg_score / (avg_score + avg_opponent_score).
    Returns 0.0 when both scores are 0 (degenerate game).
    """
    total_points = avg_score + avg_opponent_score
    if total_points <= 0.0:
        score_share = 0.0
    else:
        score_share = avg_score / total_points
    dominance = 0.6 * win_rate + 0.4 * score_share
    return float(max(0.0, min(1.0, dominance)))


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

        win_rate = float(np.mean(wins))
        avg_score = float(np.mean(scores))
        avg_opp = float(np.mean(opponent_scores))

        return EvalResult(
            model_path=model_path,
            bot_level=bot_level,
            n_games=n_games,
            win_rate=win_rate,
            avg_score=avg_score,
            avg_opponent_score=avg_opp,
            avg_rally_length=float(np.mean(rally_lengths)),
            avg_episode_length=float(np.mean(episode_lengths)),
            timestamp=datetime.now(timezone.utc).isoformat(),
            dominance_score=compute_dominance_score(win_rate, avg_score, avg_opp),
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
