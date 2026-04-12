"""Tests for the training pipeline: TrainingManager, callbacks, and replays."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from backend.rl.callbacks import CheckpointCallback, MetricsCallback
from backend.rl.trainer import TrainingManager


@pytest.fixture
def tmp_dirs(tmp_path: Path) -> tuple[str, str]:
    model_dir = str(tmp_path / "models")
    replay_dir = str(tmp_path / "replays")
    return model_dir, replay_dir


@pytest.fixture
def manager(tmp_dirs: tuple[str, str]) -> TrainingManager:
    model_dir, replay_dir = tmp_dirs
    return TrainingManager(model_dir=model_dir, replay_dir=replay_dir)


class TestTrainingManagerStart:
    """TrainingManager.start() launches training and produces checkpoints."""

    @pytest.mark.asyncio
    async def test_start_returns_experiment_id(
        self, manager: TrainingManager
    ) -> None:
        exp_id = await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        assert isinstance(exp_id, str) and len(exp_id) > 0
        # Wait for training to finish
        while manager.status == "running":
            await asyncio.sleep(0.2)

    @pytest.mark.asyncio
    async def test_start_creates_checkpoint(
        self, manager: TrainingManager
    ) -> None:
        await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)

        checkpoint_dir = Path(manager.model_dir) / manager._experiment_id
        zips = list(checkpoint_dir.glob("*.zip"))
        assert len(zips) >= 1, "Expected at least one checkpoint file"


class TestTrainingManagerStop:
    """TrainingManager.stop() gracefully stops training."""

    @pytest.mark.asyncio
    async def test_stop_sets_status_stopped(
        self, manager: TrainingManager
    ) -> None:
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        assert manager.status == "running"
        await asyncio.sleep(1)
        await manager.stop()
        assert manager.status == "stopped"


class TestTrainingManagerResume:
    """TrainingManager.resume() loads from checkpoint and continues."""

    @pytest.mark.asyncio
    async def test_resume_after_stop(
        self, manager: TrainingManager
    ) -> None:
        await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)

        # Now resume
        await manager.resume(total_timesteps=256, n_envs=2)
        assert manager.status == "running"
        while manager.status == "running":
            await asyncio.sleep(0.2)
        assert manager.status == "stopped"


class TestMetricsCallback:
    """MetricsCallback pushes metrics to the queue."""

    @pytest.mark.asyncio
    async def test_metrics_pushed_to_queue(
        self, manager: TrainingManager
    ) -> None:
        await manager.start(
            bot_level=1, total_timesteps=512, n_envs=2,
            hyperparams={"n_steps": 128, "metrics_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)

        collected: list[dict] = []
        while not manager.metrics_queue.empty():
            collected.append(manager.metrics_queue.get_nowait())

        assert len(collected) >= 1, "Expected at least one metrics entry"
        sample = collected[0]
        assert "step" in sample
        assert "mean_reward" in sample
        assert "win_rate" in sample


class TestCheckpointCallback:
    """CheckpointCallback creates checkpoint files on disk."""

    @pytest.mark.asyncio
    async def test_checkpoint_files_created(
        self, manager: TrainingManager
    ) -> None:
        await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)

        checkpoint_dir = Path(manager.model_dir) / manager._experiment_id
        assert checkpoint_dir.exists()
        zips = list(checkpoint_dir.glob("*.zip"))
        assert len(zips) >= 1
