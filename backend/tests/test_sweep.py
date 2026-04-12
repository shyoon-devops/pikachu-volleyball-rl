"""Tests for hyperparameter grid-search sweep."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.rl.sweep import HyperparamSweep, SweepResult, expand_grid


class TestExpandGrid:
    """expand_grid() produces Cartesian product of sweep config."""

    def test_single_param(self) -> None:
        grid = expand_grid({"learning_rate": [1e-4, 3e-4]})
        assert len(grid) == 2
        assert {"learning_rate": 1e-4} in grid
        assert {"learning_rate": 3e-4} in grid

    def test_two_params_cartesian(self) -> None:
        grid = expand_grid({"learning_rate": [1e-4, 3e-4], "gamma": [0.99, 0.95]})
        assert len(grid) == 4
        assert {"learning_rate": 1e-4, "gamma": 0.99} in grid
        assert {"learning_rate": 3e-4, "gamma": 0.95} in grid

    def test_three_params(self) -> None:
        grid = expand_grid({
            "learning_rate": [1e-4, 3e-4],
            "gamma": [0.99, 0.95],
            "ent_coef": [0.0, 0.01],
        })
        assert len(grid) == 8

    def test_empty_grid(self) -> None:
        assert expand_grid({}) == [{}]

    def test_scalar_passthrough(self) -> None:
        """Non-list values become single-element lists."""
        grid = expand_grid({"learning_rate": 3e-4, "gamma": [0.99, 0.95]})
        assert len(grid) == 2
        for g in grid:
            assert g["learning_rate"] == 3e-4


class TestHyperparamSweep:
    """HyperparamSweep runs multiple short trainings and collects results."""

    @pytest.fixture
    def tmp_dirs(self, tmp_path: Path) -> tuple[str, str, str]:
        return (
            str(tmp_path / "models"),
            str(tmp_path / "replays"),
            str(tmp_path / "sweeps"),
        )

    @pytest.mark.asyncio
    async def test_sweep_runs_all_combinations(
        self, tmp_dirs: tuple[str, str, str],
    ) -> None:
        model_dir, replay_dir, sweep_dir = tmp_dirs
        sweep = HyperparamSweep(
            model_dir=model_dir,
            replay_dir=replay_dir,
            sweep_dir=sweep_dir,
        )
        results = await sweep.run(
            grid={"learning_rate": [1e-4, 3e-4]},
            base_hyperparams={"n_steps": 128, "checkpoint_interval": 128},
            bot_level=1,
            total_timesteps=256,
            n_envs=2,
        )
        assert len(results) == 2
        for r in results:
            assert isinstance(r, SweepResult)
            assert r.experiment_id
            assert "learning_rate" in r.hyperparams
            assert r.total_timesteps == 256

    @pytest.mark.asyncio
    async def test_sweep_saves_summary_json(
        self, tmp_dirs: tuple[str, str, str],
    ) -> None:
        model_dir, replay_dir, sweep_dir = tmp_dirs
        sweep = HyperparamSweep(
            model_dir=model_dir, replay_dir=replay_dir, sweep_dir=sweep_dir,
        )
        results = await sweep.run(
            grid={"gamma": [0.99, 0.95]},
            base_hyperparams={"n_steps": 128, "checkpoint_interval": 128},
            bot_level=1, total_timesteps=256, n_envs=2,
        )
        summary_path = Path(sweep_dir) / sweep.sweep_id / "summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text())
        assert summary["n_runs"] == 2
        assert len(summary["runs"]) == 2
        assert summary["grid"] == {"gamma": [0.99, 0.95]}

    @pytest.mark.asyncio
    async def test_sweep_best_run(
        self, tmp_dirs: tuple[str, str, str],
    ) -> None:
        """best_run() returns the run with highest final mean_reward."""
        model_dir, replay_dir, sweep_dir = tmp_dirs
        sweep = HyperparamSweep(
            model_dir=model_dir, replay_dir=replay_dir, sweep_dir=sweep_dir,
        )
        results = await sweep.run(
            grid={"learning_rate": [1e-4, 3e-4]},
            base_hyperparams={"n_steps": 128, "checkpoint_interval": 128},
            bot_level=1, total_timesteps=256, n_envs=2,
        )
        best = sweep.best_run()
        assert best is not None
        assert best in results
        assert best.final_mean_reward >= max(r.final_mean_reward for r in results) - 1e-9
