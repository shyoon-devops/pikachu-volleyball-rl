"""Model evaluation system for Pikachu Volleyball RL agents."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.game.constants import MAX_SCORE, NET_PILLAR_X
from backend.rl.env import PikachuVolleyballEnv

logger = logging.getLogger(__name__)

# Checkpoint-adjacent manifest file written by the trainer (when
# available). Used to auto-detect ``algorithm`` so harness callers
# don't have to thread it through every CLI invocation. Missing
# manifest falls back to the explicit ``algorithm=`` arg.
TRAINING_MANIFEST_FILENAME = "training_manifest.json"
VALID_EVAL_ALGORITHMS: tuple[str, ...] = ("ppo", "sac", "dreamer_v3")


def _detect_algorithm_from_manifest(model_path: str) -> str | None:
    """Look for ``training_manifest.json`` in the ckpt's parent dir
    and return its ``algorithm`` field. Returns None if missing or
    unreadable — caller falls back to the explicit arg."""
    try:
        manifest = Path(model_path).resolve().parent / TRAINING_MANIFEST_FILENAME
        if not manifest.is_file():
            return None
        data = json.loads(manifest.read_text())
        algo = data.get("algorithm")
        if isinstance(algo, str) and algo in VALID_EVAL_ALGORITHMS:
            return algo
        return None
    except Exception:  # noqa: BLE001 — manifest is best-effort
        logger.exception("failed to read %s near %s", TRAINING_MANIFEST_FILENAME, model_path)
        return None


def _load_model(
    model_path: str, algorithm: str, env: Any = None,
) -> Any:
    """Dispatch checkpoint load on ``algorithm`` (ADR 0015/0017/0018).

    Mirrors ``LoadedPolicyBot._load`` exactly so there's one contract
    across the training-runtime and eval-harness sides. Raises
    ``ValueError`` on unknown algorithm — caller must have validated.
    """
    if algorithm == "dreamer_v3":
        from backend.rl.dreamer_runner import DreamerAgent  # noqa: PLC0415

        return DreamerAgent.load(model_path, env=env, device="cpu")
    if algorithm == "sac":
        from backend.rl.sac_discrete import SACDiscrete  # noqa: PLC0415

        return SACDiscrete.load(model_path)
    if algorithm == "ppo":
        from stable_baselines3 import PPO  # noqa: PLC0415

        return PPO.load(model_path)
    raise ValueError(
        f"algorithm must be one of {VALID_EVAL_ALGORITHMS}, got {algorithm!r}"
    )


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
        self,
        model_path: str,
        bot_level: int,
        n_games: int = 50,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        algorithm: str | None = None,
        seed: int | None = None,
        deterministic: bool = True,
    ) -> EvalResult:
        """Load a model and run N games against a bot. Return aggregated results.

        ``algorithm`` — one of ``ppo`` / ``sac`` / ``dreamer_v3``. When
        ``None``, the harness auto-detects by reading
        ``training_manifest.json`` next to the checkpoint; if no
        manifest is present, falls back to ``ppo`` for back-compat
        with pre-Sprint-5 eval harness calls.

        ``seed`` — optional seed forwarded to ``env.reset(seed=seed)``
        and to ``torch``/``numpy`` global RNGs. Lets ``batch_evaluate
        --seeds`` produce distinct trajectories across seeds for the
        same checkpoint.

        ``progress_callback`` — optional ``(games_completed, total_games)``
        hook invoked once per completed game. Exceptions from the
        callback are caught; they do NOT abort the evaluation.
        """
        resolved_algo = (
            algorithm
            or _detect_algorithm_from_manifest(model_path)
            or "ppo"
        )
        if resolved_algo not in VALID_EVAL_ALGORITHMS:
            raise ValueError(
                f"algorithm must be one of {VALID_EVAL_ALGORITHMS}, "
                f"got {resolved_algo!r}"
            )
        env = PikachuVolleyballEnv(bot_level=bot_level, max_steps=10000)
        # Dreamer.load needs env= for shape info; pass our single env.
        model = _load_model(model_path, resolved_algo, env=env)

        # Seed the global RNGs too — Dreamer's categorical sampling in
        # non-deterministic predict reads torch's global generator,
        # and the env reset already consumes numpy's.
        if seed is not None:
            try:
                import torch as th  # noqa: PLC0415

                th.manual_seed(seed)
            except Exception:  # noqa: BLE001 — torch unavailable in minimal test envs
                pass
            np.random.seed(seed)

        wins: list[int] = []
        scores: list[int] = []
        opponent_scores: list[int] = []
        rally_lengths: list[int] = []
        episode_lengths: list[int] = []

        for game_idx in range(n_games):
            # Per-game seed variation: offset the caller's seed by
            # game index so two games in the same run diverge but
            # the whole run is reproducible from the base seed.
            reset_seed = (seed + game_idx) if seed is not None else None
            obs, _ = env.reset(seed=reset_seed)
            rallies = 0
            prev_ball_side: bool | None = None  # True = right side

            terminated = False
            truncated = False
            while not terminated and not truncated:
                action, _ = model.predict(obs, deterministic=deterministic)
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

            if progress_callback is not None:
                # Best-effort observability hook; any failure inside the
                # callback must NOT abort the evaluation run. Keep the
                # exception local and move on to the next game.
                try:
                    progress_callback(game_idx + 1, n_games)
                except Exception:  # noqa: BLE001
                    pass

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
