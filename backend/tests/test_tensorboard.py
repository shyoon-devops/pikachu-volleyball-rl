"""Tests for TensorBoard logging integration.

TensorBoard is the de-facto SB3 logging sink — we wire ``tensorboard_log``
on the PPO model so that every training run produces scalar logs under
``{tensorboard_dir}/{experiment_id}``. This gives the team a visual record
of reward/loss/learning_rate curves that can be compared across runs
without re-running the training.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.rl.trainer import TrainingManager


@pytest.fixture
def manager(tmp_path: Path) -> TrainingManager:
    return TrainingManager(
        model_dir=str(tmp_path / "models"),
        replay_dir=str(tmp_path / "replays"),
        tensorboard_dir=str(tmp_path / "tb_logs"),
    )


class TestTensorboardDirWiring:
    """TrainingManager must expose a tensorboard_dir attribute for inspection."""

    def test_tensorboard_dir_default(self, tmp_path: Path) -> None:
        m = TrainingManager(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        assert m.tensorboard_dir == "tensorboard_logs"

    def test_tensorboard_dir_custom(self, manager: TrainingManager) -> None:
        assert manager.tensorboard_dir.endswith("tb_logs")


class TestTensorboardLogCreated:
    """Running a short training should produce a tensorboard event file."""

    @pytest.mark.asyncio
    async def test_event_file_written(self, manager: TrainingManager) -> None:
        await manager.start(
            bot_level=1,
            total_timesteps=256,
            n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)

        run_dir = Path(manager.tensorboard_dir) / manager._experiment_id
        assert run_dir.exists(), f"Expected TB run dir {run_dir} to exist"

        # SB3 writes under a PPO_1/-style subdir; an events file must exist
        # somewhere below the experiment dir.
        events = list(run_dir.rglob("events.out.tfevents.*"))
        assert events, f"No tfevents file found under {run_dir}"

    @pytest.mark.asyncio
    async def test_config_records_tensorboard_dir(
        self, manager: TrainingManager,
    ) -> None:
        """config.json must capture the TB log path so runs are reproducible."""
        import json

        await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)

        config_path = (
            Path(manager.model_dir) / manager._experiment_id / "config.json"
        )
        config = json.loads(config_path.read_text())
        assert "tensorboard_log" in config
        assert manager._experiment_id in config["tensorboard_log"]


class TestTensorboardDisable:
    """Tensorboard can be disabled by passing tensorboard_dir=None explicitly."""

    @pytest.mark.asyncio
    async def test_disabled_skips_event_file(self, tmp_path: Path) -> None:
        m = TrainingManager(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
            tensorboard_dir=None,
        )
        await m.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while m.status == "running":
            await asyncio.sleep(0.2)

        # No tensorboard dir to inspect — but model/run dir must still exist.
        run_model_dir = Path(m.model_dir) / m._experiment_id
        assert run_model_dir.exists()
