"""LSTM hidden-state reset on episode boundaries (ADR 0016 §7).

sb3-contrib's ``RecurrentRolloutBuffer`` zeroes the hidden state on
``dones=True``. We don't reimplement that — the ADR explicitly relies
on it. These tests pin two things:

1. The trainer actually builds a ``RecurrentPPO`` model when
   ``policy_type='lstm_v1'`` is selected — a silent fallback to PPO
   would make the whole architecture dead code.
2. One ``.learn()`` call completes end-to-end with episode
   terminations, proving the reset path is exercised in the buffer
   (SB3 would crash on shape mismatch otherwise).

We keep ``total_timesteps`` + ``n_steps`` tiny so the test still
finishes in < 30 s on CPU — this is a behavioural smoke test, not a
training quality gate.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.rl.env import PikachuVolleyballEnv
from backend.rl.policy_factory import make_policy_spec
from backend.rl.trainer import DEFAULT_NET_ARCH


def _make_env() -> Any:
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    return DummyVecEnv([lambda: Monitor(PikachuVolleyballEnv(bot_level=1))])


class TestLstmModelConstruction:
    def test_lstm_v1_builds_recurrent_model(self) -> None:
        from sb3_contrib import RecurrentPPO

        spec = make_policy_spec("lstm_v1", DEFAULT_NET_ARCH)
        env = _make_env()
        model = spec.algo_class(
            policy=spec.policy_class_id,
            env=env,
            n_steps=16,       # tiny rollout for speed
            batch_size=8,
            n_epochs=1,
            verbose=0,
            policy_kwargs=dict(spec.policy_kwargs),
        )
        assert isinstance(model, RecurrentPPO)
        # sb3-contrib registers "MlpLstmPolicy" to
        # RecurrentActorCriticPolicy; we pin that the resolved
        # policy is the recurrent one so the factory's string-id
        # choice actually lands on the LSTM class.
        assert type(model.policy).__name__ == "RecurrentActorCriticPolicy"

    def test_lstm_hidden_size_pinned(self) -> None:
        spec = make_policy_spec("lstm_v1", DEFAULT_NET_ARCH)
        env = _make_env()
        model = spec.algo_class(
            policy=spec.policy_class_id,
            env=env,
            n_steps=16,
            batch_size=8,
            n_epochs=1,
            verbose=0,
            policy_kwargs=dict(spec.policy_kwargs),
        )
        # LSTM module's ``hidden_size`` attribute is the SB3-exposed
        # contract; asserting it pins ADR 0016 §3 at the ground level
        # (not just on the kwargs dict).
        assert model.policy.lstm_actor.hidden_size == 128
        assert model.policy.lstm_actor.num_layers == 1


class TestLstmEpisodeBoundaryLearn:
    """Smoke test — a full .learn() cycle that completes episodes
    inside the rollout. If sb3-contrib's hidden-state reset weren't
    wired, this would crash on a shape-mismatched hidden-state carry
    from the previous episode (the buffer's ``dones`` mask drives the
    reset)."""

    def test_short_learn_does_not_crash_on_episode_boundary(self) -> None:
        spec = make_policy_spec("lstm_v1", DEFAULT_NET_ARCH)
        env = _make_env()
        model = spec.algo_class(
            policy=spec.policy_class_id,
            env=env,
            n_steps=64,
            batch_size=16,
            n_epochs=1,
            verbose=0,
            policy_kwargs=dict(spec.policy_kwargs),
        )
        # 128 steps ≈ a few short rallies — enough for at least one
        # env episode to terminate inside the rollout so the reset
        # code path actually runs.
        model.learn(total_timesteps=128, progress_bar=False)


class TestLoadedPolicyBotHiddenStateReset:
    """``LoadedPolicyBot.reset_history()`` must clear both the
    ball-history AND the recurrent state (ADR 0016 §7 — per-match
    reset). Without this, a new match inherits the previous match's
    intent estimate."""

    def test_reset_clears_lstm_state(self) -> None:
        from backend.rl.loaded_policy_bot import LoadedPolicyBot

        # Stub policy that returns zero action + a synthetic state
        # object we can compare by identity.
        class _StubPolicy:
            def predict(
                self,
                obs: np.ndarray,
                state: Any = None,
                episode_start: Any = None,
                *,
                deterministic: bool = True,
            ) -> tuple[np.ndarray, Any]:
                # Track what we were called with so the test can pin
                # the episode_start flag flip.
                self.last_state = state
                self.last_episode_start = (
                    None if episode_start is None else bool(episode_start[0])
                )
                return np.array(0), ("hidden", "cell")

        stub = _StubPolicy()
        bot = LoadedPolicyBot(
            model_path="/nonexistent.zip",
            checkpoint_id="stub-ckpt",
            policy_loader=lambda _p: stub,
            policy_type="lstm_v1",
        )

        # Fabricate a GameState-like object with just the attrs
        # _build_obs reads — avoids dragging the full engine into
        # this test.
        from backend.game.engine import PikachuVolleyball

        state = PikachuVolleyball(seed=1).reset()

        bot.get_action(state, is_player2=False)
        assert stub.last_episode_start is True, (
            "first call after construction must flag episode_start=True"
        )
        bot.get_action(state, is_player2=False)
        assert stub.last_episode_start is False, (
            "subsequent calls must flip episode_start=False"
        )
        assert bot._lstm_state == ("hidden", "cell")

        bot.reset_history()
        assert bot._lstm_state is None, (
            "reset_history must clear recurrent state (ADR 0016 §7)"
        )
        # Next call after reset flags episode_start=True again — the
        # buffer treats this call as the first tick of a new episode.
        bot.get_action(state, is_player2=False)
        assert stub.last_episode_start is True

    def test_mlp_v1_bot_ignores_lstm_state(self) -> None:
        from backend.rl.loaded_policy_bot import LoadedPolicyBot

        # Stub that records whether ``state`` was forwarded. For an
        # mlp_v1 bot, state must NOT be passed — otherwise PPO.predict
        # would accept and ignore it, hiding bugs in the dispatch.
        calls: list[dict[str, Any]] = []

        class _StubPolicy:
            def predict(
                self,
                obs: np.ndarray,
                *args: Any,
                **kwargs: Any,
            ) -> tuple[np.ndarray, Any]:
                calls.append({"args": args, "kwargs": kwargs})
                return np.array(3), None

        bot = LoadedPolicyBot(
            model_path="/nonexistent.zip",
            checkpoint_id="stub-ckpt",
            policy_loader=lambda _p: _StubPolicy(),
            policy_type="mlp_v1",
        )
        from backend.game.engine import PikachuVolleyball
        bot.get_action(PikachuVolleyball(seed=2).reset(), is_player2=False)
        # Exactly one call with no positional args and only
        # deterministic in kwargs — the LSTM-specific state /
        # episode_start kwargs must not appear.
        assert len(calls) == 1
        assert calls[0]["args"] == ()
        assert "state" not in calls[0]["kwargs"]
        assert "episode_start" not in calls[0]["kwargs"]
