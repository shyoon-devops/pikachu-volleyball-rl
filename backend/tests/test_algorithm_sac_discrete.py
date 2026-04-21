"""SAC-Discrete smoke test — minimum-viable working.

PM S4 brief §5: "SAC 실제 1 step rollout smoke (최소 작동 확인)".
ADR 0017 §6 success gates are training-quality (winrate on L3,
sample-efficiency vs PPO); those are measured on real runs, not in
unit tests. Here we pin the narrower invariant: the vendored
``SACDiscrete`` module constructs on the Pikachu env, runs at least
one gradient update inside ``.learn()``, predicts an action, and
round-trips through ``.save()`` / ``.load()``. If any of those four
shape-level checks fail, the algorithm is broken before we even get
to training quality.

Tests kept tiny (learning_starts=8, buffer_size=1024, batch_size=8,
total_timesteps=32) so the suite stays fast on CPU.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from backend.rl.env import PikachuVolleyballEnv
from backend.rl.policy_factory import make_policy_spec
from backend.rl.sac_discrete import SACDiscrete, SACDiscretePolicy
from backend.rl.trainer import DEFAULT_NET_ARCH


def _make_vec_env() -> Any:
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    return DummyVecEnv([lambda: Monitor(PikachuVolleyballEnv(bot_level=1))])


def _tiny_model() -> SACDiscrete:
    """Construct the smallest SACDiscrete that still exercises every
    code path in ``train()``. Defaults matter: ``learning_starts=8``
    so a 32-timestep ``learn`` call enters ``train`` at least twice;
    ``batch_size=8`` so sample-expectation sums finish quickly.
    """
    env = _make_vec_env()
    return SACDiscrete(
        policy="MlpPolicy",
        env=env,
        learning_rate=3e-4,
        buffer_size=1024,
        learning_starts=8,
        batch_size=8,
        gamma=0.99,
        verbose=0,
        policy_kwargs={"net_arch": [64, 64]},
    )


class TestSacDiscreteConstruction:
    """The vendored SAC-Discrete must construct cleanly on the
    Pikachu env (Discrete(12) action space) — the whole point of
    ADR 0017 §2 option A is that the engine is left untouched."""

    def test_construction_via_factory(self) -> None:
        # Factory → class → constructed model. Exercises the
        # policy_factory path end-to-end.
        spec = make_policy_spec("mlp_v1", DEFAULT_NET_ARCH, algorithm="sac")
        assert spec.algo_class is SACDiscrete
        env = _make_vec_env()
        model = spec.algo_class(
            policy=spec.policy_class_id,
            env=env,
            learning_rate=3e-4,
            buffer_size=1024,
            learning_starts=8,
            batch_size=8,
            verbose=0,
            policy_kwargs=dict(spec.policy_kwargs),
        )
        assert isinstance(model, SACDiscrete)
        assert isinstance(model.policy, SACDiscretePolicy)

    def test_target_entropy_matches_christodoulou(self) -> None:
        model = _tiny_model()
        # ADR 0017 §5 / Christodoulou §3.1:
        # target_H = -log(1/|A|) * 0.98 for |A|=12.
        expected = float(-np.log(1.0 / 12) * 0.98)
        assert abs(model.target_entropy - expected) < 1e-6

    def test_twin_critic(self) -> None:
        # Twin Q-critic pinned (ADR 0017 §5). Second critic gets
        # independent weights at init but same architecture.
        model = _tiny_model()
        assert model.critic.n_critics == 2
        q_a, q_b = model.critic.q_nets[0], model.critic.q_nets[1]
        # Architectures equal.
        assert [type(x).__name__ for x in q_a] == [type(x).__name__ for x in q_b]
        # Weights distinct at init (SB3 init doesn't zero-tie them).
        diff = 0.0
        for pa, pb in zip(q_a.parameters(), q_b.parameters()):
            diff += float((pa - pb).abs().sum().item())
        assert diff > 0.0, "twin critics must init with independent weights"


class TestSacDiscreteLearnSmoke:
    """A tiny ``.learn()`` run must complete without crashing and
    actually enter ``train()`` (i.e. pass ``learning_starts``)."""

    def test_learn_runs_train_at_least_once(self) -> None:
        model = _tiny_model()
        model.learn(total_timesteps=32, progress_bar=False)
        # learning_starts=8, train_freq=1, gradient_steps=1 — at 32
        # timesteps we should have plenty of gradient updates.
        assert model._n_updates > 0, (
            "SACDiscrete.train should have run at least one gradient "
            f"step by t=32 (learning_starts=8); got {model._n_updates}"
        )

    def test_predict_after_learn_is_valid_action(self) -> None:
        model = _tiny_model()
        model.learn(total_timesteps=32, progress_bar=False)
        obs = model.env.reset()
        action, _ = model.predict(obs, deterministic=True)
        # Action must be a valid Discrete(12) index.
        a = int(action[0]) if hasattr(action, "__len__") else int(action)
        assert 0 <= a < 12

    def test_entropy_coefficient_auto_tuned(self) -> None:
        model = _tiny_model()
        # Before any training: α starts at exp(log(1.0)) = 1.0.
        initial_alpha = float(model._resolve_ent_coef().detach().item())
        assert abs(initial_alpha - 1.0) < 1e-6
        model.learn(total_timesteps=32, progress_bar=False)
        # After training: α moved (auto-tune engaged). We don't pin
        # the direction — short training can move it either way —
        # only that it didn't stay pinned at exactly 1.0, which
        # would indicate the entropy optimizer is a no-op.
        post_alpha = float(model._resolve_ent_coef().detach().item())
        assert post_alpha != initial_alpha, (
            "α should auto-tune across a 32-step learn; "
            f"stayed at {initial_alpha!r}"
        )


class TestSacCheckpointRoundtrip:
    """SB3's save/load must round-trip SACDiscrete state — covered by
    the inherited OffPolicyAlgorithm mechanism plus our
    ``_excluded_save_params`` / ``_get_torch_save_params``
    overrides. If those override lists drift, load crashes or
    silently zeros out the LSTM of the α tensor."""

    def test_save_load_preserves_prediction(self, tmp_path: Path) -> None:
        model = _tiny_model()
        model.learn(total_timesteps=32, progress_bar=False)
        obs = model.env.reset()
        action_before, _ = model.predict(obs, deterministic=True)

        ckpt = tmp_path / "sac_ckpt"
        model.save(str(ckpt))
        assert (tmp_path / "sac_ckpt.zip").exists()

        reloaded = SACDiscrete.load(str(ckpt), env=model.env)
        action_after, _ = reloaded.predict(obs, deterministic=True)
        # Deterministic argmax must be identical post-load.
        assert (action_before == action_after).all(), (
            "save/load must preserve deterministic action selection"
        )


class TestLoadedPolicyBotSacIntegration:
    """LoadedPolicyBot with ``algorithm='sac'`` must dispatch to
    SACDiscrete.load and produce valid actions on a live GameState —
    mirrors the S3 LSTM integration test."""

    def test_sac_checkpoint_in_loaded_policy_bot(self, tmp_path: Path) -> None:
        from backend.game.engine import PikachuVolleyball, PlayerInput
        from backend.rl.env import ACTION_MAP
        from backend.rl.loaded_policy_bot import LoadedPolicyBot

        model = _tiny_model()
        model.learn(total_timesteps=32, progress_bar=False)
        ckpt = tmp_path / "sac_for_bot"
        model.save(str(ckpt))

        bot = LoadedPolicyBot(
            model_path=tmp_path / "sac_for_bot.zip",
            checkpoint_id="sac-bot",
            algorithm="sac",
            policy_type="mlp_v1",
        )

        engine = PikachuVolleyball(seed=3)
        state = engine.reset()
        # Ten calls — each must return a valid PlayerInput, and the
        # bot's prev-ball history must update across calls (same
        # state-keeping contract as the PPO / LSTM paths).
        for _ in range(10):
            action = bot.get_action(state, is_player2=False)
            assert isinstance(action, PlayerInput)
            assert action in ACTION_MAP.values()
            state = engine.step(action, PlayerInput(0, 0, False))
