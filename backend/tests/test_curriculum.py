"""Tests for curriculum learning auto-progression."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.rl.callbacks import CurriculumCallback
from backend.rl.trainer import TrainingManager


@pytest.fixture
def manager(tmp_path: Path) -> TrainingManager:
    return TrainingManager(
        model_dir=str(tmp_path / "models"),
        replay_dir=str(tmp_path / "replays"),
    )


class TestCurriculumCallback:
    """CurriculumCallback promotes bot_level when win_rate exceeds threshold."""

    def test_initial_state(self) -> None:
        cb = CurriculumCallback(
            initial_level=1,
            max_level=5,
            win_rate_threshold=0.7,
            min_episodes=20,
        )
        assert cb.current_level == 1
        assert cb.max_level == 5

    def test_promote_when_win_rate_exceeds_threshold(self) -> None:
        cb = CurriculumCallback(
            initial_level=1, max_level=5, win_rate_threshold=0.7, min_episodes=4,
        )
        # Simulate 4 wins out of 4 (100% win rate)
        for _ in range(4):
            cb._record_episode(won=True)
        # Should promote from L1 -> L2
        assert cb._should_promote() is True
        cb._apply_promotion()
        assert cb.current_level == 2

    def test_no_promote_when_win_rate_below(self) -> None:
        cb = CurriculumCallback(
            initial_level=1, max_level=5, win_rate_threshold=0.7, min_episodes=4,
        )
        # 2 wins out of 4 (50% win rate) — below 70%
        for won in [True, False, True, False]:
            cb._record_episode(won=won)
        assert cb._should_promote() is False
        assert cb.current_level == 1

    def test_no_promote_before_min_episodes(self) -> None:
        cb = CurriculumCallback(
            initial_level=1, max_level=5, win_rate_threshold=0.7, min_episodes=10,
        )
        # Only 3 episodes with 100% wins — below min_episodes
        for _ in range(3):
            cb._record_episode(won=True)
        assert cb._should_promote() is False

    def test_cap_at_max_level(self) -> None:
        cb = CurriculumCallback(
            initial_level=5, max_level=5, win_rate_threshold=0.7, min_episodes=4,
        )
        for _ in range(4):
            cb._record_episode(won=True)
        assert cb._should_promote() is False

    def test_reset_window_on_promotion(self) -> None:
        """After promotion, the episode window should reset for fair re-eval."""
        cb = CurriculumCallback(
            initial_level=1, max_level=5, win_rate_threshold=0.7, min_episodes=4,
        )
        for _ in range(4):
            cb._record_episode(won=True)
        cb._apply_promotion()
        assert len(cb._recent_results) == 0

    def test_custom_initial_level(self) -> None:
        cb = CurriculumCallback(
            initial_level=3, max_level=5, win_rate_threshold=0.7, min_episodes=4,
        )
        assert cb.current_level == 3


class TestCurriculumIntegration:
    """End-to-end: TrainingManager accepts curriculum config and auto-promotes."""

    @pytest.mark.asyncio
    async def test_curriculum_config_accepted(
        self, manager: TrainingManager,
    ) -> None:
        await manager.start(
            bot_level=1,
            total_timesteps=256,
            n_envs=2,
            hyperparams={
                "n_steps": 128,
                "checkpoint_interval": 128,
                "curriculum": {
                    "enabled": True,
                    "max_level": 5,
                    "win_rate_threshold": 0.7,
                    "min_episodes": 20,
                },
            },
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)
        # Training completed without crash
        assert manager.status == "stopped"

    @pytest.mark.asyncio
    async def test_curriculum_disabled_by_default(
        self, manager: TrainingManager,
    ) -> None:
        """When curriculum is not configured, bot_level stays fixed."""
        await manager.start(
            bot_level=2, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)
        assert manager._bot_level == 2
