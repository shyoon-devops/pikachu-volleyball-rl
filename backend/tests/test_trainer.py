"""Tests for the training pipeline: TrainingManager, callbacks, and replays."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from backend.rl.callbacks import CheckpointCallback, MetricsCallback
from backend.rl.trainer import (
    STOP_PROTECTION_THRESHOLD,
    TrainingManager,
    _INTERRUPTED_META_FILENAME,
)


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
        result = await manager.stop()
        assert manager.status == "stopped"
        assert result["stopped"] is True
        assert result["reason"] == "stopped"

    @pytest.mark.asyncio
    async def test_stop_not_running_returns_not_running(
        self, manager: TrainingManager
    ) -> None:
        result = await manager.stop()
        assert result["stopped"] is True
        assert result["reason"] == "not_running"

    @pytest.mark.asyncio
    async def test_stop_rejected_when_protected(
        self, manager: TrainingManager
    ) -> None:
        """Stop without force is rejected once current_step >= threshold."""
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await asyncio.sleep(1)
        # Simulate many steps completed
        manager.current_step = STOP_PROTECTION_THRESHOLD + 1
        result = await manager.stop(force=False)
        assert result["stopped"] is False
        assert result["reason"] == "protected"
        assert manager.status == "running"
        # Clean up — force stop
        await manager.stop(force=True)

    @pytest.mark.asyncio
    async def test_stop_forced_when_protected(
        self, manager: TrainingManager
    ) -> None:
        """Stop with force=True succeeds even past threshold."""
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await asyncio.sleep(1)
        manager.current_step = STOP_PROTECTION_THRESHOLD + 1
        result = await manager.stop(force=True)
        assert result["stopped"] is True
        assert result["reason"] == "stopped"
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


async def _wait_for_model_ready(
    manager: TrainingManager, timeout: float = 30,
) -> None:
    """Wait until the training thread has created the model and started stepping."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if manager._model is not None and manager.current_step > 0:
            return
        await asyncio.sleep(0.3)
    raise TimeoutError("Model did not become ready within timeout")


class TestEmergencySave:
    """SIGTERM emergency checkpoint save and resume."""

    @pytest.mark.asyncio
    async def test_emergency_save_creates_checkpoint_and_meta(
        self, manager: TrainingManager
    ) -> None:
        """_emergency_save writes interrupted.zip + interrupted.json."""
        await manager.start(
            bot_level=2, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await _wait_for_model_ready(manager)
        assert manager.status == "running"

        manager._emergency_save()

        checkpoint_dir = Path(manager.model_dir) / manager._experiment_id
        assert (checkpoint_dir / "interrupted.zip").exists()

        meta_path = Path(manager.model_dir) / _INTERRUPTED_META_FILENAME
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["experiment_id"] == manager._experiment_id
        assert meta["bot_level"] == 2
        assert meta["current_step"] >= 0

        await manager.stop(force=True)

    @pytest.mark.asyncio
    async def test_get_interrupted_session_returns_none_when_clean(
        self, manager: TrainingManager
    ) -> None:
        assert manager.get_interrupted_session() is None

    @pytest.mark.asyncio
    async def test_get_interrupted_session_returns_meta(
        self, manager: TrainingManager
    ) -> None:
        """After emergency save, get_interrupted_session returns metadata."""
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await _wait_for_model_ready(manager)
        manager._emergency_save()
        await manager.stop(force=True)

        meta = manager.get_interrupted_session()
        assert meta is not None
        assert meta["experiment_id"] == manager._experiment_id

    @pytest.mark.asyncio
    async def test_resume_interrupted_restores_session(
        self, manager: TrainingManager
    ) -> None:
        """resume_interrupted picks up from the emergency checkpoint."""
        await manager.start(
            bot_level=3, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await _wait_for_model_ready(manager)
        original_exp_id = manager._experiment_id
        manager._emergency_save()
        await manager.stop(force=True)

        manager2 = TrainingManager(
            model_dir=manager.model_dir,
            replay_dir=manager.replay_dir,
        )
        resumed_id = await manager2.resume_interrupted(
            total_timesteps=256, n_envs=2,
        )
        assert resumed_id == original_exp_id
        assert manager2.status == "running"
        assert manager2._bot_level == 3

        while manager2.status == "running":
            await asyncio.sleep(0.2)

    @pytest.mark.asyncio
    async def test_clear_interrupted_session(
        self, manager: TrainingManager
    ) -> None:
        """clear_interrupted_session removes the marker file."""
        await manager.start(
            bot_level=1, total_timesteps=100_000, n_envs=2,
            hyperparams={"n_steps": 128},
        )
        await _wait_for_model_ready(manager)
        manager._emergency_save()
        await manager.stop(force=True)

        assert manager.get_interrupted_session() is not None
        manager.clear_interrupted_session()
        assert manager.get_interrupted_session() is None
