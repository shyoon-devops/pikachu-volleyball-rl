"""Bit-parity: ``algorithm='ppo'`` (or default) reproduces the
pre-S4 construction exactly.

ADR 0017 §3 + PM S4 brief: "Default ``ppo`` (기존 동작 보존 —
bit-level parity)". Every callsite that omits the algorithm axis or
passes ``"ppo"`` must produce a model architecturally identical to
what trainer.py built pre-S4 — otherwise every existing run-record,
checkpoint, and S3 parity test becomes a false-positive.

We pin the architectural slice (class, policy, param shapes). The
reward / LSTM / algorithm factory tests cover other axes.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.rl.env import PikachuVolleyballEnv
from backend.rl.policy_factory import make_policy_spec
from backend.rl.trainer import DEFAULT_HYPERPARAMS, DEFAULT_NET_ARCH, TrainingManager


def _make_vec_env() -> Any:
    from stable_baselines3.common.vec_env import DummyVecEnv

    return DummyVecEnv([lambda: PikachuVolleyballEnv(bot_level=1)])


class TestDefaultAlgorithmIsPpo:
    """Bare-construction invariants — the entire pre-S4 callsite
    universe relies on the default being ``ppo``."""

    def test_manager_default_algorithm_is_ppo(self) -> None:
        tm = TrainingManager(model_dir="/tmp/ignored", replay_dir="/tmp/ignored")
        assert tm._algorithm == "ppo"

    def test_factory_implicit_algorithm_is_ppo(self) -> None:
        from stable_baselines3 import PPO

        spec_implicit = make_policy_spec("mlp_v1", DEFAULT_NET_ARCH)
        assert spec_implicit.algo_class is PPO
        assert spec_implicit.policy_class_id == "MlpPolicy"


class TestPpoConstructorParity:
    """Factory-built ppo × mlp_v1 must match a hand-built PPO using
    the pre-S4 kwargs — same class, same policy, same net_arch, same
    per-parameter shapes. Duplicates the S3 parity test under the
    new signature so drift between the two is immediately visible."""

    def test_factory_ppo_mlp_v1_matches_hardcoded(self) -> None:
        from stable_baselines3 import PPO

        env_a = _make_vec_env()
        env_b = _make_vec_env()
        hp = DEFAULT_HYPERPARAMS
        spec = make_policy_spec("mlp_v1", DEFAULT_NET_ARCH, algorithm="ppo")

        # Path A: factory-driven (what trainer.py now does).
        model_a = spec.algo_class(
            policy=spec.policy_class_id,
            env=env_a,
            learning_rate=hp["learning_rate"],
            n_steps=hp["n_steps"],
            batch_size=hp["batch_size"],
            n_epochs=hp["n_epochs"],
            gamma=hp["gamma"],
            gae_lambda=hp["gae_lambda"],
            clip_range=hp["clip_range"],
            ent_coef=hp["ent_coef"],
            verbose=0,
            policy_kwargs=dict(spec.policy_kwargs),
        )

        # Path B: hardcoded — what trainer.py did pre-S4 (the exact
        # call that shipped in v1.0.0).
        model_b = PPO(
            policy="MlpPolicy",
            env=env_b,
            learning_rate=hp["learning_rate"],
            n_steps=hp["n_steps"],
            batch_size=hp["batch_size"],
            n_epochs=hp["n_epochs"],
            gamma=hp["gamma"],
            gae_lambda=hp["gae_lambda"],
            clip_range=hp["clip_range"],
            ent_coef=hp["ent_coef"],
            verbose=0,
            policy_kwargs={"net_arch": [256, 256]},
        )

        assert type(model_a).__name__ == type(model_b).__name__ == "PPO"
        assert type(model_a.policy).__name__ == type(model_b.policy).__name__
        params_a = [(n, tuple(p.shape)) for n, p in model_a.policy.named_parameters()]
        params_b = [(n, tuple(p.shape)) for n, p in model_b.policy.named_parameters()]
        assert params_a == params_b, (
            "ppo factory path must produce a parameter layout "
            "identical to the pre-S4 hardcoded constructor"
        )


class TestManagerStartAcceptsAlgorithm:
    """``TrainingManager.start`` lands ``algorithm`` on ``_algorithm``
    before the training thread launches — same pattern as reward_model
    / policy_type."""

    @pytest.mark.asyncio
    async def test_default_is_ppo(self, tmp_path) -> None:
        from unittest.mock import patch

        tm = TrainingManager(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        with patch("threading.Thread") as _MockThread:
            _MockThread.return_value.start = lambda: None
            await tm.start()
        assert tm._algorithm == "ppo"

    @pytest.mark.asyncio
    async def test_sac_value_accepted(self, tmp_path) -> None:
        from unittest.mock import patch

        tm = TrainingManager(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        with patch("threading.Thread") as _MockThread:
            _MockThread.return_value.start = lambda: None
            await tm.start(algorithm="sac")
        assert tm._algorithm == "sac"

    @pytest.mark.asyncio
    async def test_unknown_algorithm_rejected(self, tmp_path) -> None:
        tm = TrainingManager(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        with pytest.raises(ValueError, match="algorithm"):
            await tm.start(algorithm="dqn")
        # Status must not flip to running on a rejected value.
        assert tm.status == "stopped"
