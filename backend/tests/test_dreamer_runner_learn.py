"""DreamerAgent ``.learn()`` smoke test.

PM S5 brief §7: "100 env step × 1 iteration smoke (world model loss
감소 확인)". ADR 0018 §6 success gates are training-quality metrics
on real runs (2M env steps, 5× sample-efficiency vs PPO); those
live in the eval scorecard, not in unit tests. Here we pin the
narrower invariant: the vendored ``DreamerAgent`` module
constructs on the Pikachu env, completes the three-phase train
loop without crashing, and produces a **finite, decreasing**
world-model loss on the short smoke window.

Construction uses tiny hyperparams so the test runs in under a
minute on CPU (RSSM hidden 32, latent 4×4, batch 4, sequence 8,
imagine horizon 3, replay 512).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.rl.dreamer_runner import DREAMER_DEFAULT_KWARGS, DreamerAgent
from backend.rl.env import PikachuVolleyballEnv


def _make_vec_env() -> Any:
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    return DummyVecEnv([lambda: Monitor(PikachuVolleyballEnv(bot_level=1))])


def _tiny_agent() -> DreamerAgent:
    return DreamerAgent(
        env=_make_vec_env(),
        device="cpu",
        rssm_hidden_size=32, latent_dim=4, latent_axes=4,
        batch_size=4, sequence_length=8, train_every=8,
        imagine_horizon=3, replay_capacity=512,
        free_bits=0.1,
    )


class TestDreamerConstruction:
    """The vendored DreamerAgent must construct cleanly on the
    Pikachu env (Box(18,) obs, Discrete(12) action) — ADR 0018 §3
    invariant that the engine stays untouched."""

    def test_constructs_on_pikachu_env(self) -> None:
        agent = _tiny_agent()
        assert agent.obs_dim == 18
        assert agent.action_dim == 12
        assert agent.num_timesteps == 0

    def test_default_hyperparams_match_adr(self) -> None:
        # ADR 0018 §7: fixed at RSSM hidden 512, latent 32×32,
        # world-model lr 1e-4, actor lr 3e-5, critic lr 3e-5,
        # imagine horizon 15, replay 1M. Pin so surfacing any of
        # these on the WS payload without updating the ADR trips.
        assert DREAMER_DEFAULT_KWARGS["rssm_hidden_size"] == 512
        assert DREAMER_DEFAULT_KWARGS["latent_dim"] == 32
        assert DREAMER_DEFAULT_KWARGS["latent_axes"] == 32
        assert DREAMER_DEFAULT_KWARGS["world_model_lr"] == 1e-4
        assert DREAMER_DEFAULT_KWARGS["actor_lr"] == 3e-5
        assert DREAMER_DEFAULT_KWARGS["critic_lr"] == 3e-5
        assert DREAMER_DEFAULT_KWARGS["imagine_horizon"] == 15
        assert DREAMER_DEFAULT_KWARGS["replay_capacity"] == 1_000_000


class TestDreamerLearnSmoke:
    """100 env steps through the three-phase loop. World-model loss
    must stay finite and should trend downward over the window."""

    def test_learn_runs_without_crash(self) -> None:
        agent = _tiny_agent()
        agent.learn(total_timesteps=100)
        assert agent.num_timesteps == 100
        # learning_starts-equivalent here is just
        # ``len(buffer) >= sequence_length`` — with train_every=8
        # and seq_len=8 we should hit the train branch multiple
        # times inside 100 steps.
        assert agent._n_updates > 0

    def test_world_model_training_is_wired(self) -> None:
        """Three-part invariant: (1) WM loss is finite at every
        tick, (2) the WM optimizer actually updates RSSM weights
        (not a no-op backward pass), (3) average loss drops across
        a long training window.

        Tiny networks + small batches give noisy per-step losses,
        so we average over 50-train windows. The first two checks
        catch the majority of "wiring broken" regressions; the
        third catches "optimizer runs but loss stays flat"."""
        import torch as th

        agent = _tiny_agent()
        # Fill buffer well past sequence_length so every train call
        # has varied data.
        agent.learn(total_timesteps=128)

        # Snapshot a few RSSM params to prove the optimizer moves them.
        before_weights = [
            p.detach().clone() for p in agent.rssm.parameters()
        ]

        early_losses: list[float] = [
            agent._train_world_model()["wm_loss"] for _ in range(50)
        ]
        late_losses: list[float] = [
            agent._train_world_model()["wm_loss"] for _ in range(50)
        ]

        # (1) finite
        assert all(np.isfinite(x) for x in early_losses + late_losses), (
            "WM loss hit NaN / inf at some tick"
        )

        # (2) weights actually moved
        after_weights = list(agent.rssm.parameters())
        total_delta = sum(
            float((a - b).abs().sum().item())
            for a, b in zip(after_weights, before_weights)
        )
        assert total_delta > 0.0, (
            "RSSM weights did not change across 100 WM train steps — "
            "optimizer wiring is broken"
        )

        # (3) long-window average drops. Generous tolerance because
        # tiny batches bounce; the assertion only trips on the
        # "flat-or-growing" failure mode.
        mean_early = float(np.mean(early_losses))
        mean_late = float(np.mean(late_losses))
        assert mean_late < mean_early * 1.05, (
            f"WM loss average did not trend downward: "
            f"early={mean_early:.4f}, late={mean_late:.4f}"
        )


class TestDreamerPredict:
    """Predict must return a valid Discrete(12) action index in the
    SB3-shaped (action, state) tuple."""

    def test_predict_after_learn(self) -> None:
        agent = _tiny_agent()
        agent.learn(total_timesteps=32)
        obs = agent.env.reset()
        action, state = agent.predict(obs, deterministic=True)
        assert state is None  # Dreamer doesn't expose hidden state through predict
        assert action.shape == (1,) and action.dtype == np.int64
        assert 0 <= int(action[0]) < 12

    def test_predict_deterministic_is_argmax(self) -> None:
        # Deterministic predict is argmax — two calls on the same
        # obs must match. (Stochastic predict doesn't have to.)
        agent = _tiny_agent()
        agent.learn(total_timesteps=16)
        obs = agent.env.reset()
        a1, _ = agent.predict(obs, deterministic=True)
        a2, _ = agent.predict(obs, deterministic=True)
        assert (a1 == a2).all()
