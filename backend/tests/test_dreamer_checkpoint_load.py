"""Dreamer V3 save/load roundtrip via LoadedPolicyBot.

PM S5 brief §7: "학습 후 저장 → LoadedPolicyBot 으로 재load → predict
성공". Mirrors the ADR 0017 §9 contract — a trained
``DreamerAgent`` must survive the same checkpoint pipeline that
PPO / SAC / RecurrentPPO use (slug-prefixed zip on disk, reload
via `LoadedPolicyBot`), and the reloaded bot must produce valid
actions against a live ``GameState``.

ADR 0018 §10 is explicit that Dreamer checkpoints are NOT
cross-loadable with PPO / SAC — the internals are an RSSM + actor
+ critic state-dict, not an SB3 ``BaseAlgorithm.save`` payload. We
pin that contract here too: a Dreamer checkpoint opened as PPO
(or vice versa) must fail loudly rather than silently produce a
corrupt policy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.game.engine import PikachuVolleyball, PlayerInput
from backend.rl.dreamer_runner import DreamerAgent
from backend.rl.env import ACTION_MAP, PikachuVolleyballEnv
from backend.rl.loaded_policy_bot import LoadedPolicyBot


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
        imagine_horizon=3, replay_capacity=512, free_bits=0.1,
    )


class TestDreamerCheckpointRoundtrip:
    """Full save → load cycle via the DreamerAgent classmethod —
    deterministic prediction must match across the roundtrip."""

    def test_save_load_preserves_prediction(self, tmp_path: Path) -> None:
        agent = _tiny_agent()
        agent.learn(total_timesteps=48)

        obs = agent.env.reset()
        action_before, _ = agent.predict(obs, deterministic=True)

        ckpt = tmp_path / "dreamer_ckpt"
        agent.save(str(ckpt))
        assert (tmp_path / "dreamer_ckpt.zip").exists(), (
            "DreamerAgent.save must emit a .zip container matching the "
            "{slug}__{exp8}__final.zip pattern used by the checkpoint "
            "discovery code in trainer._find_latest_checkpoint"
        )

        reloaded = DreamerAgent.load(
            str(ckpt), env=_make_vec_env(), device="cpu",
        )
        action_after, _ = reloaded.predict(obs, deterministic=True)
        assert (action_before == action_after).all(), (
            "save/load must preserve deterministic action selection — "
            "if this fails, state_dict coverage is incomplete "
            "(actor / critic / rssm / decoder all need persisting)"
        )

    def test_preserved_step_counter(self, tmp_path: Path) -> None:
        # num_timesteps / _n_updates are the run-record + dashboard
        # counters; losing them across save/load would break resume
        # bookkeeping and metric series continuity.
        agent = _tiny_agent()
        agent.learn(total_timesteps=32)
        saved_steps = agent.num_timesteps
        saved_updates = agent._n_updates

        ckpt = tmp_path / "dreamer_counters"
        agent.save(str(ckpt))
        reloaded = DreamerAgent.load(
            str(ckpt), env=_make_vec_env(), device="cpu",
        )
        assert reloaded.num_timesteps == saved_steps
        assert reloaded._n_updates == saved_updates


class TestDreamerLoadedPolicyBotIntegration:
    """LoadedPolicyBot with ``algorithm='dreamer_v3'`` must
    dispatch to ``DreamerAgent.load`` and produce valid
    ``PlayerInput`` values on a live engine — ADR 0018 §4: the bot
    contract is unchanged from PPO / SAC (get_action returns
    ``PlayerInput``, reset_history clears per-match state)."""

    def test_dreamer_checkpoint_in_loaded_policy_bot(
        self, tmp_path: Path
    ) -> None:
        agent = _tiny_agent()
        agent.learn(total_timesteps=48)
        ckpt = tmp_path / "dreamer_for_bot"
        agent.save(str(ckpt))

        bot = LoadedPolicyBot(
            model_path=tmp_path / "dreamer_for_bot.zip",
            checkpoint_id="dreamer-bot",
            algorithm="dreamer_v3",
            # policy_type is **ignored** on this path (ADR 0018 §4)
            # — set it to a random value to pin that.
            policy_type="mlp_v1",
        )

        engine = PikachuVolleyball(seed=13)
        state = engine.reset()
        for _ in range(10):
            action = bot.get_action(state, is_player2=False)
            assert isinstance(action, PlayerInput), (
                "LoadedPolicyBot(algorithm='dreamer_v3') must return "
                "PlayerInput, matching the PPO/SAC contract"
            )
            assert action in ACTION_MAP.values()
            state = engine.step(action, PlayerInput(0, 0, False))

    def test_dreamer_ignores_policy_type(self, tmp_path: Path) -> None:
        # Both implemented policy_types must load the same Dreamer
        # checkpoint (policy_type is orthogonal on this path).
        agent = _tiny_agent()
        agent.learn(total_timesteps=32)
        ckpt = tmp_path / "dreamer_pt_check"
        agent.save(str(ckpt))

        for pt in ("mlp_v1", "lstm_v1"):
            bot = LoadedPolicyBot(
                model_path=tmp_path / "dreamer_pt_check.zip",
                checkpoint_id=f"dreamer-{pt}",
                algorithm="dreamer_v3",
                policy_type=pt,
            )
            # _load is lazy — call get_action once to force it.
            engine = PikachuVolleyball(seed=17)
            state = engine.reset()
            action = bot.get_action(state, is_player2=False)
            assert isinstance(action, PlayerInput)


class TestCrossAlgoLoadRefused:
    """ADR 0018 §10: Dreamer checkpoints are NOT cross-loadable
    with PPO / SAC. A DreamerAgent.load on an SB3 SAC/PPO
    checkpoint must fail loudly (zipfile layout mismatch — SB3
    uses ``pytorch_variables.pth`` / ``data.json`` / ``pytorch_variables.pth``,
    our vendored Dreamer uses ``data.pt``)."""

    def test_dreamer_refuses_ppo_checkpoint(self, tmp_path: Path) -> None:
        # Train a tiny PPO to disk, then try to open it as Dreamer.
        from stable_baselines3 import PPO
        from stable_baselines3.common.monitor import Monitor
        from stable_baselines3.common.vec_env import DummyVecEnv

        ppo_env = DummyVecEnv([lambda: Monitor(PikachuVolleyballEnv(bot_level=1))])
        ppo = PPO(
            "MlpPolicy", ppo_env, n_steps=16, batch_size=4, n_epochs=1,
            verbose=0, policy_kwargs={"net_arch": [16, 16]},
        )
        ppo.learn(total_timesteps=16)
        ppo_ckpt = tmp_path / "ppo_looks_like_dreamer"
        ppo.save(str(ppo_ckpt))

        # Opening a PPO checkpoint as Dreamer — the zip layout has
        # no "data.pt", so our load raises at the zipfile read.
        with pytest.raises(Exception):
            DreamerAgent.load(
                str(ppo_ckpt), env=_make_vec_env(), device="cpu",
            )
