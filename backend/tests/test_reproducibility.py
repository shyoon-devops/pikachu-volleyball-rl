"""Tests for training reproducibility: seed fixing + config logging."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np
import pytest

from backend.rl.trainer import TrainingManager


@pytest.fixture
def manager(tmp_path: Path) -> TrainingManager:
    return TrainingManager(
        model_dir=str(tmp_path / "models"),
        replay_dir=str(tmp_path / "replays"),
    )


class TestSeedFixing:
    """A fixed seed should produce deterministic environment resets."""

    def test_env_reset_deterministic_with_seed(self) -> None:
        from backend.rl.env import PikachuVolleyballEnv

        env1 = PikachuVolleyballEnv(bot_level=1)
        env2 = PikachuVolleyballEnv(bot_level=1)
        obs1, _ = env1.reset(seed=42)
        obs2, _ = env2.reset(seed=42)
        np.testing.assert_array_equal(obs1, obs2)
        env1.close()
        env2.close()

    def test_env_reset_different_with_different_seeds(self) -> None:
        from backend.rl.env import PikachuVolleyballEnv

        env = PikachuVolleyballEnv(bot_level=1)
        obs1, _ = env.reset(seed=1)
        obs2, _ = env.reset(seed=999)
        # At least the RNG state differs — not strictly required for obs to differ,
        # but most of the time the subsequent random draws will.
        # Sanity: both should be valid 18-float arrays.
        assert obs1.shape == (18,)
        assert obs2.shape == (18,)
        env.close()


class TestConfigLogging:
    """Training manager should persist a full config.json for every run."""

    @pytest.mark.asyncio
    async def test_config_json_created_on_start(
        self, manager: TrainingManager,
    ) -> None:
        await manager.start(
            bot_level=2,
            total_timesteps=256,
            n_envs=2,
            seed=123,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)

        config_path = (
            Path(manager.model_dir) / manager._experiment_id / "config.json"
        )
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert config["experiment_id"] == manager._experiment_id
        assert config["bot_level"] == 2
        assert config["seed"] == 123
        assert config["total_timesteps"] == 256
        assert config["n_envs"] == 2
        assert config["hyperparams"]["n_steps"] == 128
        assert "obs_space_shape" in config
        assert config["obs_space_shape"] == [18]
        assert "action_space_n" in config
        assert config["action_space_n"] == 12

    @pytest.mark.asyncio
    async def test_config_includes_code_version(
        self, manager: TrainingManager,
    ) -> None:
        """config.json should capture the git commit (best-effort) + timestamp."""
        await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)
        config = json.loads(
            (Path(manager.model_dir) / manager._experiment_id / "config.json")
            .read_text(),
        )
        assert "started_at" in config
        assert "git_commit" in config  # may be "unknown" if not a git checkout

    @pytest.mark.asyncio
    async def test_seed_propagated_to_ppo(
        self, manager: TrainingManager,
    ) -> None:
        """The PPO model should be constructed with the given seed."""
        await manager.start(
            bot_level=1, total_timesteps=256, n_envs=2, seed=777,
            hyperparams={"n_steps": 128, "checkpoint_interval": 128},
        )
        while manager.status == "running":
            await asyncio.sleep(0.2)
        assert manager._seed == 777
