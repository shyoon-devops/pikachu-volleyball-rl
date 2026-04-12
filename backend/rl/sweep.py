"""Hyperparameter grid-search sweep for PPO training.

Runs multiple short trainings sequentially, one per hyperparameter
combination, and records the final mean_reward / win_rate of each run.
Results are persisted to ``sweep_dir/<sweep_id>/summary.json`` so
they can be compared after the sweep completes.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.rl.trainer import TrainingManager

logger = logging.getLogger(__name__)


def expand_grid(grid: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a sweep config into a list of concrete hyperparameter dicts.

    Scalar values pass through as single-element lists, so callers can mix
    fixed values with swept values in the same dict.
    """
    if not grid:
        return [{}]
    keys: list[str] = []
    values: list[list[Any]] = []
    for k, v in grid.items():
        keys.append(k)
        values.append(list(v) if isinstance(v, (list, tuple)) else [v])

    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


@dataclass
class SweepResult:
    """Outcome of a single sweep run."""

    experiment_id: str
    hyperparams: dict[str, Any]
    total_timesteps: int
    final_mean_reward: float = 0.0
    final_win_rate: float = 0.0
    metrics_history: list[dict[str, Any]] = field(default_factory=list)


class HyperparamSweep:
    """Sequential grid-search over PPO hyperparameters.

    Each run uses a fresh TrainingManager instance and trains for the same
    number of steps, so the final mean_reward is comparable across runs.
    """

    def __init__(
        self,
        model_dir: str = "models",
        replay_dir: str = "replays",
        sweep_dir: str = "sweeps",
    ) -> None:
        self.model_dir = model_dir
        self.replay_dir = replay_dir
        self.sweep_dir = sweep_dir
        self.sweep_id: str = str(uuid.uuid4())
        self._results: list[SweepResult] = []

    async def run(
        self,
        grid: dict[str, Any],
        base_hyperparams: dict[str, Any] | None = None,
        bot_level: int = 1,
        total_timesteps: int = 100_000,
        n_envs: int = 4,
    ) -> list[SweepResult]:
        """Run the full grid sequentially. Returns list of results."""
        base = dict(base_hyperparams or {})
        combinations = expand_grid(grid)
        logger.info(
            "Sweep %s: %d combinations × %d steps each",
            self.sweep_id, len(combinations), total_timesteps,
        )

        sweep_out = Path(self.sweep_dir) / self.sweep_id
        sweep_out.mkdir(parents=True, exist_ok=True)

        self._results = []
        for i, overrides in enumerate(combinations):
            hp = {**base, **overrides}
            logger.info(
                "Sweep %s run %d/%d: %s",
                self.sweep_id, i + 1, len(combinations), overrides,
            )
            result = await self._run_single(
                hp=hp, bot_level=bot_level,
                total_timesteps=total_timesteps, n_envs=n_envs,
                overrides=overrides,
            )
            self._results.append(result)
            self._save_summary(grid, sweep_out)

        return self._results

    async def _run_single(
        self,
        hp: dict[str, Any],
        bot_level: int,
        total_timesteps: int,
        n_envs: int,
        overrides: dict[str, Any],
    ) -> SweepResult:
        manager = TrainingManager(
            model_dir=self.model_dir, replay_dir=self.replay_dir,
        )
        exp_id = await manager.start(
            bot_level=bot_level,
            total_timesteps=total_timesteps,
            n_envs=n_envs,
            hyperparams=hp,
        )
        while manager.status == "running":
            await asyncio.sleep(0.5)

        history: list[dict[str, Any]] = []
        while not manager.metrics_queue.empty():
            history.append(manager.metrics_queue.get_nowait())

        final_reward = history[-1].get("mean_reward", 0.0) if history else 0.0
        final_wr = history[-1].get("win_rate", 0.0) if history else 0.0

        return SweepResult(
            experiment_id=exp_id,
            hyperparams=overrides,
            total_timesteps=total_timesteps,
            final_mean_reward=float(final_reward),
            final_win_rate=float(final_wr),
            metrics_history=history,
        )

    def _save_summary(self, grid: dict[str, Any], sweep_out: Path) -> None:
        summary = {
            "sweep_id": self.sweep_id,
            "grid": {
                k: list(v) if isinstance(v, (list, tuple)) else [v]
                for k, v in grid.items()
            },
            "n_runs": len(self._results),
            "runs": [
                {
                    "experiment_id": r.experiment_id,
                    "hyperparams": r.hyperparams,
                    "total_timesteps": r.total_timesteps,
                    "final_mean_reward": r.final_mean_reward,
                    "final_win_rate": r.final_win_rate,
                }
                for r in self._results
            ],
        }
        (sweep_out / "summary.json").write_text(json.dumps(summary, indent=2))

    def best_run(self) -> SweepResult | None:
        """Return the run with the highest final_mean_reward, or None if empty."""
        if not self._results:
            return None
        return max(self._results, key=lambda r: r.final_mean_reward)
