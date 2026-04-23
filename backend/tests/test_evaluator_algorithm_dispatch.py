"""Evaluator loads the right algorithm checkpoint class.

bench-B 2026-04-23 hit ``PPO.load`` hardcoded in ``ModelEvaluator.evaluate``
against a Dreamer checkpoint — failed at unzip. This suite pins the
three-way dispatch (ppo / sac / dreamer_v3) + the manifest-based
auto-detection fallback so a future refactor that drops one path
fires immediately instead of burning batch-eval wall-clock.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.rl.env import PikachuVolleyballEnv
from backend.rl.evaluator import (
    VALID_EVAL_ALGORITHMS,
    ModelEvaluator,
    _detect_algorithm_from_manifest,
    _load_model,
)


def _train_and_save_ppo(tmp_path: Path) -> Path:
    from stable_baselines3 import PPO
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    env = DummyVecEnv([lambda: Monitor(PikachuVolleyballEnv(bot_level=1))])
    m = PPO(
        "MlpPolicy", env, n_steps=16, batch_size=4, n_epochs=1,
        verbose=0, policy_kwargs={"net_arch": [16, 16]},
    )
    m.learn(total_timesteps=16)
    p = tmp_path / "ppo_ckpt"
    m.save(str(p))
    return tmp_path / "ppo_ckpt.zip"


def _train_and_save_sac(tmp_path: Path) -> Path:
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    from backend.rl.sac_discrete import SACDiscrete

    env = DummyVecEnv([lambda: Monitor(PikachuVolleyballEnv(bot_level=1))])
    m = SACDiscrete(
        policy="MlpPolicy", env=env, learning_starts=4,
        batch_size=4, buffer_size=256, verbose=0,
        policy_kwargs={"net_arch": [16, 16]},
    )
    m.learn(total_timesteps=16)
    p = tmp_path / "sac_ckpt"
    m.save(str(p))
    return tmp_path / "sac_ckpt.zip"


def _train_and_save_dreamer(tmp_path: Path) -> Path:
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    from backend.rl.dreamer_runner import DreamerAgent

    env = DummyVecEnv([lambda: Monitor(PikachuVolleyballEnv(bot_level=1))])
    agent = DreamerAgent(
        env=env, device="cpu",
        rssm_hidden_size=16, latent_dim=4, latent_axes=4,
        batch_size=4, sequence_length=8, train_every=8,
        imagine_horizon=3, replay_capacity=256, free_bits=0.1,
    )
    agent.learn(total_timesteps=16)
    p = tmp_path / "dreamer_ckpt"
    agent.save(str(p))
    return tmp_path / "dreamer_ckpt.zip"


class TestAlgorithmDispatch:
    """_load_model routes to the correct class for each enum value.
    These are the direct call targets that ``ModelEvaluator.evaluate``
    dispatches through — a wrong class here corrupts the checkpoint
    at unpickle."""

    def test_ppo_routes_to_sb3_ppo(self, tmp_path: Path) -> None:
        from stable_baselines3 import PPO

        ckpt = _train_and_save_ppo(tmp_path)
        model = _load_model(str(ckpt), "ppo", env=None)
        assert isinstance(model, PPO)

    def test_sac_routes_to_sac_discrete(self, tmp_path: Path) -> None:
        from backend.rl.sac_discrete import SACDiscrete

        ckpt = _train_and_save_sac(tmp_path)
        model = _load_model(str(ckpt), "sac", env=None)
        assert isinstance(model, SACDiscrete)

    def test_dreamer_routes_to_dreamer_agent(self, tmp_path: Path) -> None:
        from backend.rl.dreamer_runner import DreamerAgent

        ckpt = _train_and_save_dreamer(tmp_path)
        # DreamerAgent.load requires env= for shape info.
        model = _load_model(
            str(ckpt), "dreamer_v3",
            env=PikachuVolleyballEnv(bot_level=1, max_steps=200),
        )
        assert isinstance(model, DreamerAgent)

    def test_unknown_algorithm_rejected(self) -> None:
        with pytest.raises(ValueError, match="algorithm must be one of"):
            _load_model("/nonexistent.zip", "random_forest", env=None)


class TestManifestDetection:
    """``_detect_algorithm_from_manifest`` picks up a sibling
    ``training_manifest.json`` and returns its algorithm field.
    Missing or malformed manifest → None (caller falls back)."""

    def test_missing_manifest_returns_none(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "some_ckpt.zip"
        ckpt.write_bytes(b"PK\x03\x04")  # empty-ish zip header
        assert _detect_algorithm_from_manifest(str(ckpt)) is None

    def test_manifest_with_valid_algorithm(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "run1" / "ckpt.zip"
        ckpt.parent.mkdir()
        ckpt.write_bytes(b"PK\x03\x04")
        (ckpt.parent / "training_manifest.json").write_text(
            json.dumps({"algorithm": "dreamer_v3", "experiment_id": "xxx"})
        )
        assert _detect_algorithm_from_manifest(str(ckpt)) == "dreamer_v3"

    def test_manifest_with_unknown_algorithm(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "run2" / "ckpt.zip"
        ckpt.parent.mkdir()
        ckpt.write_bytes(b"PK\x03\x04")
        (ckpt.parent / "training_manifest.json").write_text(
            json.dumps({"algorithm": "qrdqn"})
        )
        # Unknown algorithm in manifest falls back to None — evaluator
        # then uses the explicit arg / ppo default.
        assert _detect_algorithm_from_manifest(str(ckpt)) is None

    def test_malformed_manifest_returns_none(self, tmp_path: Path) -> None:
        ckpt = tmp_path / "run3" / "ckpt.zip"
        ckpt.parent.mkdir()
        ckpt.write_bytes(b"PK\x03\x04")
        (ckpt.parent / "training_manifest.json").write_text("not json {")
        assert _detect_algorithm_from_manifest(str(ckpt)) is None


class TestEvaluateSmokePerAlgorithm:
    """End-to-end smoke — ``ModelEvaluator.evaluate`` runs a short
    game batch per algorithm without crashing. n=2 games keeps each
    under a minute on CPU; the contract being tested is "no
    AttributeError", not "good score"."""

    def test_ppo_evaluate_smoke(self, tmp_path: Path) -> None:
        ckpt = _train_and_save_ppo(tmp_path)
        result = ModelEvaluator().evaluate(
            str(ckpt), bot_level=1, n_games=2, algorithm="ppo",
        )
        assert 0.0 <= result.win_rate <= 1.0
        assert result.n_games == 2

    def test_dreamer_evaluate_smoke(self, tmp_path: Path) -> None:
        """The exact bench-B failure path, inverted — evaluator must
        load a Dreamer checkpoint and run n_games games without the
        hardcoded-PPO.load crash."""
        ckpt = _train_and_save_dreamer(tmp_path)
        result = ModelEvaluator().evaluate(
            str(ckpt), bot_level=1, n_games=2, algorithm="dreamer_v3",
        )
        assert 0.0 <= result.win_rate <= 1.0
        assert result.n_games == 2


class TestValidAlgorithmsConstant:
    def test_contains_expected_three(self) -> None:
        assert set(VALID_EVAL_ALGORITHMS) == {"ppo", "sac", "dreamer_v3"}
