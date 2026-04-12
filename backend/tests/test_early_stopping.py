"""Tests for early-stopping callback."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.rl.callbacks import EarlyStoppingCallback
from backend.rl.trainer import TrainingManager


@pytest.fixture
def manager(tmp_path: Path) -> TrainingManager:
    return TrainingManager(
        model_dir=str(tmp_path / "models"),
        replay_dir=str(tmp_path / "replays"),
    )


class TestEarlyStoppingCallback:
    """EarlyStoppingCallback triggers when no improvement over patience window."""

    def test_initial_state(self) -> None:
        cb = EarlyStoppingCallback(
            patience=5, min_delta=0.01, check_interval=1000,
        )
        assert cb.patience == 5
        assert cb.min_delta == 0.01
        assert cb._patience_counter == 0
        assert cb._best_reward == float("-inf")

    def test_improvement_resets_counter(self) -> None:
        cb = EarlyStoppingCallback(patience=3, min_delta=0.1, check_interval=1)
        cb._evaluate_reward(1.0)
        assert cb._patience_counter == 0
        assert cb._best_reward == 1.0
        # Clear improvement (>= min_delta)
        cb._evaluate_reward(1.5)
        assert cb._patience_counter == 0
        assert cb._best_reward == 1.5

    def test_stagnation_increments_counter(self) -> None:
        cb = EarlyStoppingCallback(patience=3, min_delta=0.1, check_interval=1)
        cb._evaluate_reward(1.0)
        # Marginal change below min_delta
        cb._evaluate_reward(1.05)
        assert cb._patience_counter == 1
        cb._evaluate_reward(1.02)
        assert cb._patience_counter == 2

    def test_triggers_after_patience_exhausted(self) -> None:
        cb = EarlyStoppingCallback(patience=3, min_delta=0.1, check_interval=1)
        cb._evaluate_reward(1.0)
        cb._evaluate_reward(1.01)
        cb._evaluate_reward(1.02)
        assert cb.should_stop is False
        cb._evaluate_reward(1.03)  # 3rd stagnation
        assert cb.should_stop is True

    def test_regression_counts_as_stagnation(self) -> None:
        """A drop in reward should also consume patience, not reset it."""
        cb = EarlyStoppingCallback(patience=2, min_delta=0.1, check_interval=1)
        cb._evaluate_reward(1.0)
        cb._evaluate_reward(0.5)
        assert cb._patience_counter == 1
        cb._evaluate_reward(0.3)
        assert cb._patience_counter == 2
        assert cb.should_stop is True


class TestEarlyStoppingIntegration:
    """TrainingManager wires EarlyStoppingCallback when configured."""

    @pytest.mark.asyncio
    async def test_early_stop_config_accepted(
        self, manager: TrainingManager,
    ) -> None:
        await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={
                "n_steps": 128, "checkpoint_interval": 128,
                "early_stopping": {
                    "enabled": True, "patience": 5,
                    "min_delta": 0.01, "check_interval": 128,
                },
            },
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)
        assert manager.status == "stopped"
