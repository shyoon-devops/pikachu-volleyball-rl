"""Integration tests for Pikachu Volleyball — cross-module interactions."""

from __future__ import annotations

import random
import tempfile
from pathlib import Path

import msgpack
import pytest

from backend.game.bot import RuleBasedBot
from backend.game.engine import PikachuVolleyball, PlayerInput
from backend.rl.env import PikachuVolleyballEnv

NOOP = PlayerInput(x_dir=0, y_dir=0, power_hit=False)


class TestEngineToEnvIntegration:
    """Game engine runs correctly inside the Gym environment."""

    def test_env_wraps_engine_state(self, rl_env: PikachuVolleyballEnv) -> None:
        obs, _ = rl_env.reset()
        # Observation should reflect the engine's initial state
        assert obs.shape == (18,)
        # Player1 is on the left half → normalized x < 0
        assert obs[0] < 0  # player1.x / w * 2 - 1

    def test_env_action_maps_to_engine_input(
        self, rl_env: PikachuVolleyballEnv
    ) -> None:
        rl_env.reset()
        # All 12 actions should produce valid steps
        for action in range(12):
            obs, reward, terminated, truncated, info = rl_env.step(action)
            assert obs.shape == (18,)
            if terminated or truncated:
                rl_env.reset()

    def test_env_scores_match_engine(self, rl_env: PikachuVolleyballEnv) -> None:
        rl_env.reset()
        for _ in range(500):
            obs, _, terminated, truncated, info = rl_env.step(0)
            if terminated or truncated:
                break
        # Info should carry engine's score
        assert "score1" in info
        assert "score2" in info
        assert info["score1"] >= 0
        assert info["score2"] >= 0

    def test_env_reward_positive_on_scoring(self) -> None:
        """When agent scores, reward should include +10."""
        env = PikachuVolleyballEnv(bot_level=1, max_steps=10000)
        env.reset()

        scored = False
        for _ in range(5000):
            obs, reward, terminated, truncated, info = env.step(
                env.action_space.sample()
            )
            if info["score1"] > 0 and not scored:
                assert reward >= 9.0  # +10 base minus small penalties
                scored = True
                break
            if terminated or truncated:
                env.reset()

        env.close()

    def test_multiple_episodes_no_state_leak(self) -> None:
        """Multiple reset/run cycles should not leak state."""
        env = PikachuVolleyballEnv(bot_level=1, max_steps=500)

        for _ in range(5):
            obs, _ = env.reset()
            assert obs.shape == (18,)
            for _ in range(100):
                obs, _, terminated, truncated, _ = env.step(
                    env.action_space.sample()
                )
                if terminated or truncated:
                    break

        env.close()


class TestEnvToTrainerIntegration:
    """Short training should run without error (if SB3 is available)."""

    def test_short_ppo_training_no_error(self) -> None:
        """Run a minimal PPO training for 128 steps — no crash."""
        try:
            from stable_baselines3 import PPO
        except ImportError:
            pytest.skip("stable-baselines3 not installed")

        env = PikachuVolleyballEnv(bot_level=1, max_steps=500)
        model = PPO(
            "MlpPolicy",
            env,
            n_steps=64,
            batch_size=32,
            n_epochs=2,
            verbose=0,
        )
        model.learn(total_timesteps=128)
        env.close()

    def test_model_predict_after_training(self) -> None:
        """Trained model should predict valid actions."""
        try:
            from stable_baselines3 import PPO
        except ImportError:
            pytest.skip("stable-baselines3 not installed")

        env = PikachuVolleyballEnv(bot_level=1, max_steps=500)
        model = PPO(
            "MlpPolicy",
            env,
            n_steps=64,
            batch_size=32,
            n_epochs=2,
            verbose=0,
        )
        model.learn(total_timesteps=128)

        obs, _ = env.reset()
        action, _ = model.predict(obs, deterministic=True)
        assert 0 <= int(action) <= 11
        env.close()


class TestModelSaveLoad:
    """Model checkpoint save/load roundtrip."""

    def test_save_and_load_produces_same_prediction(self) -> None:
        try:
            from stable_baselines3 import PPO
        except ImportError:
            pytest.skip("stable-baselines3 not installed")

        env = PikachuVolleyballEnv(bot_level=1, max_steps=500)
        model = PPO(
            "MlpPolicy",
            env,
            n_steps=64,
            batch_size=32,
            n_epochs=2,
            verbose=0,
        )
        model.learn(total_timesteps=128)

        obs, _ = env.reset()
        action_before, _ = model.predict(obs, deterministic=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_model")
            model.save(path)

            loaded = PPO.load(path, env=env)
            action_after, _ = loaded.predict(obs, deterministic=True)

        assert int(action_before) == int(action_after)
        env.close()


class TestReplayRoundtrip:
    """Game frame data serialization/deserialization via msgpack."""

    def test_msgpack_roundtrip(self) -> None:
        """Run a short game, serialize frames, deserialize, verify integrity."""
        random.seed(42)
        game = PikachuVolleyball()
        state = game.reset()
        bot1 = RuleBasedBot(level=3)
        bot2 = RuleBasedBot(level=3)

        frames: list[dict] = []
        for _ in range(200):
            frame = {
                "player1": {"x": state.player1.x, "y": state.player1.y},
                "player2": {"x": state.player2.x, "y": state.player2.y},
                "ball": {"x": state.ball.x, "y": state.ball.y},
                "score1": state.score1,
                "score2": state.score2,
                "frame": state.frame,
            }
            frames.append(frame)

            a1 = bot1.get_action(state, is_player2=False)
            a2 = bot2.get_action(state, is_player2=True)
            state = game.step(a1, a2)

        # Serialize → deserialize
        packed = msgpack.packb(frames, use_bin_type=True)
        unpacked = msgpack.unpackb(packed, raw=False)

        assert len(unpacked) == len(frames)
        assert unpacked[0]["player1"]["x"] == frames[0]["player1"]["x"]
        assert unpacked[-1]["score1"] == frames[-1]["score1"]

    def test_msgpack_file_roundtrip(self) -> None:
        """Write to file and read back."""
        frames = [
            {"player1": {"x": 100}, "ball": {"x": 200}, "score1": 3, "frame": 10},
            {"player1": {"x": 110}, "ball": {"x": 190}, "score1": 3, "frame": 11},
        ]

        with tempfile.NamedTemporaryFile(suffix=".msgpack", delete=False) as f:
            packed = msgpack.packb(frames, use_bin_type=True)
            f.write(packed)
            tmppath = f.name

        data = msgpack.unpackb(Path(tmppath).read_bytes(), raw=False)
        Path(tmppath).unlink()

        assert len(data) == 2
        assert data[0]["player1"]["x"] == 100
        assert data[1]["frame"] == 11


class TestEnvBotLevelIntegration:
    """Verify different bot levels work within the env."""

    @pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
    def test_env_with_each_bot_level(self, level: int) -> None:
        env = PikachuVolleyballEnv(bot_level=level, max_steps=500)
        obs, _ = env.reset()
        assert obs.shape == (18,)

        for _ in range(100):
            obs, _, terminated, truncated, _ = env.step(env.action_space.sample())
            if terminated or truncated:
                break

        env.close()
