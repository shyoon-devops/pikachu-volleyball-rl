"""LoadedPolicyBot end-to-end with a real RecurrentPPO checkpoint.

The stubbed-policy test in ``test_policy_lstm_hidden_state_reset.py``
already covers the bot's state-management logic. This test pins the
other half: can a ``RecurrentPPO.save`` checkpoint written in one
process be re-opened via ``LoadedPolicyBot`` and produce actions on a
live ``GameState``? That exercise covers:

  * ``_load()`` dispatch picking the right algo class
    (``RecurrentPPO.load`` vs ``PPO.load``).
  * ``get_action`` threading the hidden state across successive calls
    without crashing on shape mismatch.
  * ``reset_history`` re-zeroing state between matches.

We keep the checkpoint tiny (16-step rollout, one epoch) — this is a
shape / dispatch test, not a quality test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.game.engine import PikachuVolleyball, PlayerInput
from backend.rl.env import ACTION_MAP, PikachuVolleyballEnv
from backend.rl.loaded_policy_bot import LoadedPolicyBot
from backend.rl.policy_factory import make_policy_spec
from backend.rl.trainer import DEFAULT_NET_ARCH


def _train_and_save_lstm(tmp_path: Path) -> Path:
    """Build a minimal RecurrentPPO, learn briefly, and save."""
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    spec = make_policy_spec("lstm_v1", DEFAULT_NET_ARCH)
    env = DummyVecEnv([lambda: Monitor(PikachuVolleyballEnv(bot_level=1))])
    model = spec.algo_class(
        policy=spec.policy_class_id,
        env=env,
        n_steps=32,
        batch_size=8,
        n_epochs=1,
        verbose=0,
        policy_kwargs=dict(spec.policy_kwargs),
    )
    model.learn(total_timesteps=32, progress_bar=False)
    ckpt_path = tmp_path / "lstm_tiny"
    model.save(str(ckpt_path))
    # Stable Baselines3 always writes .zip; caller should load without
    # the extension (SB3's load() appends it back).
    assert (tmp_path / "lstm_tiny.zip").exists()
    return tmp_path / "lstm_tiny.zip"


def _train_and_save_mlp(tmp_path: Path) -> Path:
    """Build a minimal PPO, learn briefly, and save."""
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    spec = make_policy_spec("mlp_v1", DEFAULT_NET_ARCH)
    env = DummyVecEnv([lambda: Monitor(PikachuVolleyballEnv(bot_level=1))])
    model = spec.algo_class(
        policy=spec.policy_class_id,
        env=env,
        n_steps=32,
        batch_size=8,
        n_epochs=1,
        verbose=0,
        policy_kwargs=dict(spec.policy_kwargs),
    )
    model.learn(total_timesteps=32, progress_bar=False)
    ckpt_path = tmp_path / "mlp_tiny"
    model.save(str(ckpt_path))
    return tmp_path / "mlp_tiny.zip"


class TestLoadedPolicyBotLstmRoundtrip:
    """Full save → load → predict loop for an lstm_v1 checkpoint."""

    def test_lstm_checkpoint_loads_and_acts(self, tmp_path: Path) -> None:
        ckpt = _train_and_save_lstm(tmp_path)

        bot = LoadedPolicyBot(
            model_path=ckpt,
            checkpoint_id="lstm-test",
            policy_type="lstm_v1",
        )

        engine = PikachuVolleyball(seed=7)
        state = engine.reset()

        # Twenty consecutive calls exercise the hidden-state carry
        # path — if the state tuple had the wrong shape SB3 would
        # raise inside torch.nn.LSTM.forward on the second call.
        for _ in range(20):
            action = bot.get_action(state, is_player2=False)
            assert isinstance(action, PlayerInput)
            # Step the engine so the observation delta changes —
            # a frozen state would not exercise prev_ball tracking.
            state = engine.step(action, PlayerInput(0, 0, False))
        # After 20 calls the bot's recurrent state must be populated.
        assert bot._lstm_state is not None

    def test_reset_history_zeroes_state_between_matches(
        self, tmp_path: Path
    ) -> None:
        ckpt = _train_and_save_lstm(tmp_path)
        bot = LoadedPolicyBot(
            model_path=ckpt,
            checkpoint_id="lstm-test",
            policy_type="lstm_v1",
        )

        engine = PikachuVolleyball(seed=11)
        state = engine.reset()
        for _ in range(5):
            bot.get_action(state, is_player2=False)
            state = engine.step(
                PlayerInput(0, 0, False), PlayerInput(0, 0, False)
            )
        assert bot._lstm_state is not None

        bot.reset_history()
        assert bot._lstm_state is None
        # episode_starts flipped back to True — pin it here rather
        # than re-calling predict (which would re-populate state and
        # defeat the assertion).
        assert bool(bot._episode_starts[0]) is True


class TestLoadedPolicyBotMlpRoundtripUnchanged:
    """mlp_v1 checkpoint loading must continue to work unchanged —
    the Sprint 3 changes are additive, not a replacement."""

    def test_mlp_checkpoint_still_loads(self, tmp_path: Path) -> None:
        ckpt = _train_and_save_mlp(tmp_path)

        bot = LoadedPolicyBot(
            model_path=ckpt,
            checkpoint_id="mlp-test",
            # Default policy_type is mlp_v1; make it explicit here so
            # a future default change doesn't silently break the test.
            policy_type="mlp_v1",
        )

        engine = PikachuVolleyball(seed=13)
        state = engine.reset()
        for _ in range(10):
            action = bot.get_action(state, is_player2=False)
            assert isinstance(action, PlayerInput)
            state = engine.step(action, PlayerInput(0, 0, False))
        # mlp_v1 bot never populates recurrent state.
        assert bot._lstm_state is None

    def test_default_policy_type_is_mlp_v1(self, tmp_path: Path) -> None:
        ckpt = _train_and_save_mlp(tmp_path)
        bot = LoadedPolicyBot(
            model_path=ckpt,
            checkpoint_id="mlp-default",
        )
        assert bot.policy_type == "mlp_v1"


class TestCrossArchLoadRefused:
    """ADR 0016 §4: cross-arch load is NOT supported — an MLP
    checkpoint opened with policy_type='lstm_v1' (or vice versa) must
    fail loudly, not silently produce nonsense actions. SB3 raises on
    shape mismatch; we pin that it propagates cleanly up through the
    bot's ``_load`` rather than being swallowed."""

    def test_mlp_checkpoint_opened_as_lstm_raises(
        self, tmp_path: Path
    ) -> None:
        ckpt = _train_and_save_mlp(tmp_path)
        bot = LoadedPolicyBot(
            model_path=ckpt,
            checkpoint_id="cross-arch",
            policy_type="lstm_v1",
        )
        # SB3 raises during unpickle / state-dict apply. We don't pin
        # the exact exception class (sb3-contrib versions vary) — only
        # that an error escapes instead of returning a live policy.
        with pytest.raises(Exception):
            bot._load()
