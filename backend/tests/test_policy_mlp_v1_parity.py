"""Bit-parity: policy_type='mlp_v1' reproduces the pre-Sprint-3
construction exactly.

ADR 0016 §3 ("Default `mlp_v1`; callers that omit the field keep
MLP") must hold at the byte level — every existing bot_ladder run
predates Sprint 3, so the factory-driven path MUST produce the same
model shape as the hardcoded ``PPO(policy="MlpPolicy", ...,
policy_kwargs={"net_arch": [256, 256]})`` that lived in trainer.py
pre-refactor.

We don't train here — just construct the model and compare the
architectural parts (algo class, policy class, net_arch, observation
/ action spaces). Weight-level parity is covered separately by SB3's
own seeded-init contract; what we pin here is that the trainer's
dispatch doesn't sneak extra kwargs in that would alter learning.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.rl.env import PikachuVolleyballEnv
from backend.rl.policy_factory import make_policy_spec
from backend.rl.trainer import DEFAULT_HYPERPARAMS, DEFAULT_NET_ARCH


def _make_vec_env() -> Any:
    # Single-env DummyVecEnv is the minimal surface SB3 needs for
    # model construction. We don't call .learn() so the test stays
    # fast even without GPU.
    from stable_baselines3.common.vec_env import DummyVecEnv

    return DummyVecEnv([lambda: PikachuVolleyballEnv(bot_level=1)])


class TestMlpV1ConstructorParity:
    """The factory-built mlp_v1 model must match a hand-built PPO
    with identical kwargs — same class, same policy, same net_arch.
    Any drift here flags trainer.py reaching into the factory output
    in a way that diverges from the v1.0.0 constructor."""

    def test_factory_mlp_v1_matches_hardcoded_ppo(self) -> None:
        from stable_baselines3 import PPO

        env_a = _make_vec_env()
        env_b = _make_vec_env()

        hp = DEFAULT_HYPERPARAMS
        spec = make_policy_spec("mlp_v1", DEFAULT_NET_ARCH)

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

        # Path B: hardcoded — what trainer.py did before Sprint 3.
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

        # Same algorithm.
        assert type(model_a).__name__ == type(model_b).__name__ == "PPO"
        # Same policy class.
        assert type(model_a.policy).__name__ == type(model_b.policy).__name__
        # Same MLP architecture (shape of every param layer must match).
        params_a = [(n, tuple(p.shape)) for n, p in model_a.policy.named_parameters()]
        params_b = [(n, tuple(p.shape)) for n, p in model_b.policy.named_parameters()]
        assert params_a == params_b, (
            "mlp_v1 factory path must produce a parameter layout "
            "identical to the pre-Sprint-3 hardcoded constructor"
        )

    def test_default_is_mlp_v1(self) -> None:
        # The TrainingManager's default must stay mlp_v1 so callers
        # that never set policy_type keep the v1.0.0 behaviour.
        from backend.rl.trainer import TrainingManager

        tm = TrainingManager(model_dir="/tmp/ignored", replay_dir="/tmp/ignored")
        assert tm._policy_type == "mlp_v1"


class TestManagerStartValidation:
    """TrainingManager.start() mirrors ``reward_model`` validation.
    Unknown policy_type must fail before the training thread spawns."""

    @pytest.mark.asyncio
    async def test_unknown_policy_type_rejected(self) -> None:
        from backend.rl.trainer import TrainingManager

        tm = TrainingManager(model_dir="/tmp/ignored", replay_dir="/tmp/ignored")
        with pytest.raises(ValueError, match="policy_type"):
            await tm.start(policy_type="mlp_v2")

    @pytest.mark.asyncio
    async def test_reserved_policy_type_accepted_at_start(self) -> None:
        """ADR 0016 §8: reserved values (``gru_v1`` / ``transformer_v1``)
        parse through ``start()`` and land on ``_policy_type`` so the
        run record + audit trail preserve the caller's intent. The
        actual "not implemented" guard fires inside ``_train_loop``
        when ``make_policy_spec`` runs — covered by the factory's own
        unit test."""
        from unittest.mock import patch
        from backend.rl.trainer import TrainingManager

        tm = TrainingManager(model_dir="/tmp/ignored", replay_dir="/tmp/ignored")
        # Patch threading.Thread so start() doesn't actually spawn the
        # _train_loop (which would crash on the factory call).
        with patch("threading.Thread") as _MockThread:
            _MockThread.return_value.start = lambda: None
            await tm.start(policy_type="gru_v1")
        assert tm._policy_type == "gru_v1"
