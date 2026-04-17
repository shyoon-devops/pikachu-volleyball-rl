"""Gap-fill tests to boost coverage on game/, rl/ modules."""

from __future__ import annotations

import asyncio
import tempfile
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.game.bot import RuleBasedBot
from backend.game.constants import (
    MAX_SCORE,
    NET_PILLAR_TOP_Y,
    NET_PILLAR_X,
    PLAYER_GROUND_Y,
)
from backend.game.engine import (
    BallState,
    GameState,
    PikachuVolleyball,
    PlayerInput,
    PlayerState,
)
from backend.rl.callbacks import (
    CheckpointCallback,
    MetricsCallback,
    _serialize_state,
)
from backend.rl.env import ACTION_MAP, PikachuVolleyballEnv

NOOP = PlayerInput(x_dir=0, y_dir=0, power_hit=False)


# ─── game/engine.py gaps ───


class TestEngineDiving:
    """Cover the diving/lying_down code paths (lines 113-116, 148-149)."""

    def test_player_lying_down_decrements(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Force player into lying_down state
        game._state.player1.lying_down_duration = 5
        game._state.player1.is_diving = False
        game._state.player1.is_jumping = False

        state = game.step(NOOP, NOOP)
        assert state.player1.lying_down_duration < 5

    def test_lying_down_eventually_clears(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        game._state.player1.lying_down_duration = 2

        for _ in range(5):
            state = game.step(NOOP, NOOP)
            if state.is_round_over:
                break
        assert state.player1.lying_down_duration == 0

    def test_diving_landing_sets_lying_down(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Force player1 into diving state at ground level. state=3 is
        # "diving" per the port; sync_derived_flags propagates to
        # is_diving/is_jumping compat views.
        game._state.player1.state = 3
        game._state.player1.diving_direction = 0
        game._state.player1.sync_derived_flags()
        game._state.player1.y = PLAYER_GROUND_Y - 5
        game._state.player1.vy = 10  # will reach ground

        state = game.step(NOOP, NOOP)
        # After landing from dive, lying_down_duration should be set
        # to LYING_DOWN_DURATION (3 frames per original physics.js).
        from backend.game.constants import LYING_DOWN_DURATION

        assert state.player1.lying_down_duration == LYING_DOWN_DURATION or state.is_round_over


class TestEngineNetCollisionZeroVx:
    """Cover net collision when ball has vx=0 (lines 219-222)."""

    def test_net_collision_vx_zero_ball_left(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Place ball at net with no horizontal velocity, on left side
        game._state.ball.x = NET_PILLAR_X - 5
        game._state.ball.y = NET_PILLAR_TOP_Y + 10
        game._state.ball.vx = 0
        game._state.ball.vy = 0

        state = game.step(NOOP, NOOP)
        # Ball should be pushed to the left of the net
        assert state.ball.x <= NET_PILLAR_X or state.is_round_over

    def test_net_collision_vx_zero_ball_right(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        game._state.ball.x = NET_PILLAR_X + 5
        game._state.ball.y = NET_PILLAR_TOP_Y + 10
        game._state.ball.vx = 0
        game._state.ball.vy = 0

        state = game.step(NOOP, NOOP)
        assert state.ball.x >= NET_PILLAR_X or state.is_round_over


# ─── game/bot.py gaps ───


class TestBotInvalidLevel:
    """Cover ValueError for invalid level (line 44)."""

    def test_invalid_level_raises(self) -> None:
        with pytest.raises(ValueError, match="Level must be 1-5"):
            RuleBasedBot(level=0)

    def test_invalid_level_high_raises(self) -> None:
        with pytest.raises(ValueError, match="Level must be 1-5"):
            RuleBasedBot(level=6)


class TestBotFramesToY:
    """Cover the _frames_to_y fallback returning 200 (line 181)."""

    def test_frames_to_y_unreachable(self) -> None:
        bot = RuleBasedBot(level=1)
        # Ball at y=0 moving upward — will never reach target far below
        result = bot._frames_to_y(y=0.0, vy=-100.0, target_y=100000.0)
        # Should return 200 (max) or some positive value
        assert result > 0


# ─── rl/callbacks.py ───


class TestSerializeState:
    """Cover _serialize_state helper function."""

    def test_serialize_state_returns_dict(self) -> None:
        state = GameState(
            player1=PlayerState(x=100, y=200),
            player2=PlayerState(x=300, y=200),
            ball=BallState(x=200, y=150, vx=3, vy=-5),
            score1=5,
            score2=3,
            frame=42,
        )
        result = _serialize_state(state)

        assert result["player1"]["x"] == 100
        assert result["player2"]["x"] == 300
        assert result["ball"]["x"] == 200
        assert result["ball"]["vy"] == -5
        assert result["score1"] == 5
        assert result["score2"] == 3
        assert result["frame"] == 42

    def test_serialize_state_has_all_keys(self) -> None:
        state = GameState(
            player1=PlayerState(x=0, y=0),
            player2=PlayerState(x=0, y=0),
            ball=BallState(x=0, y=0),
        )
        result = _serialize_state(state)
        # Display-state-machine fields (state_name / slow_motion_frames_left
        # / fade_black_alpha / ready_message_visible) added by
        # ``port(engine-state): add slowMotion + afterEndOfRound +
        # beforeStartOfNextRound`` so the FE replay viewer can render the
        # full pikavolley.js round/afterEndOfRound/beforeStartOfNextRound
        # transitions. ``post_score_freeze_frames`` is back-filled by
        # replay_service for legacy replays only.
        assert set(result.keys()) == {
            "player1",
            "player2",
            "ball",
            "score1",
            "score2",
            "frame",
            "is_round_over",
            "is_game_ended",
            "game_end_frame_counter",
            "sounds",
            "state_name",
            "slow_motion_frames_left",
            "fade_black_alpha",
            "ready_message_visible",
            "tick_rate",
        }

    def test_serialize_state_sounds_has_five_keys(self) -> None:
        # Schema contract: `sounds` holds the 5 physics-layer flags.
        # `pi` / `pikachu` are menu sounds and intentionally NOT emitted.
        state = GameState(
            player1=PlayerState(x=0, y=0),
            player2=PlayerState(x=0, y=0),
            ball=BallState(x=0, y=0),
        )
        result = _serialize_state(state)
        assert set(result["sounds"].keys()) == {
            "pika",
            "chu",
            "pipikachu",
            "power_hit",
            "ball_touches_ground",
        }
        assert all(v is False for v in result["sounds"].values())

    def test_serialize_state_sounds_or_across_players(self) -> None:
        # Player-side flags are OR'd so a single True from either player
        # bubbles up. Ball-side flags come directly from the ball.
        state = GameState(
            player1=PlayerState(x=0, y=0, sound_chu=True),
            player2=PlayerState(x=0, y=0, sound_pika=True, sound_pipikachu=True),
            ball=BallState(
                x=0, y=0, sound_power_hit=True, sound_ball_touches_ground=True
            ),
        )
        result = _serialize_state(state)
        assert result["sounds"] == {
            "pika": True,
            "chu": True,
            "pipikachu": True,
            "power_hit": True,
            "ball_touches_ground": True,
        }

    def test_serialize_state_emits_diving_direction(self) -> None:
        # Port check: physics.js Player.divingDirection (0xB4, init 0) must
        # round-trip through the WS/replay frame. FE uses this to flip the
        # dive sprite left/right instead of guessing from vx sign.
        state = GameState(
            player1=PlayerState(x=100, y=200, is_diving=True, diving_direction=-1),
            player2=PlayerState(x=300, y=200, is_diving=True, diving_direction=1),
            ball=BallState(x=200, y=150),
        )
        result = _serialize_state(state)
        assert result["player1"]["diving_direction"] == -1
        assert result["player2"]["diving_direction"] == 1

    def test_serialize_state_diving_direction_defaults_zero(self) -> None:
        state = GameState(
            player1=PlayerState(x=0, y=0),
            player2=PlayerState(x=0, y=0),
            ball=BallState(x=0, y=0),
        )
        result = _serialize_state(state)
        assert result["player1"]["diving_direction"] == 0
        assert result["player2"]["diving_direction"] == 0


class TestCheckpointCallback:
    """Cover CheckpointCallback save logic."""

    def test_checkpoint_creates_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            CheckpointCallback(
                experiment_id="test-exp",
                model_dir=tmpdir,
                save_interval=100,
            )
            checkpoint_dir = Path(tmpdir) / "test-exp"
            assert checkpoint_dir.exists()

    def test_checkpoint_saves_at_interval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = CheckpointCallback(
                experiment_id="test-exp",
                model_dir=tmpdir,
                save_interval=100,
            )
            # Mock the model
            cb.model = MagicMock()
            cb.num_timesteps = 100

            result = cb._on_step()
            assert result is True
            cb.model.save.assert_called_once()

    def test_checkpoint_skips_non_interval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = CheckpointCallback(
                experiment_id="test-exp",
                model_dir=tmpdir,
                save_interval=100,
            )
            cb.model = MagicMock()
            cb.num_timesteps = 50

            result = cb._on_step()
            assert result is True
            cb.model.save.assert_not_called()


class TestMetricsCallback:
    """Cover MetricsCallback metric publishing."""

    def test_metrics_callback_logs_at_interval(self) -> None:
        loop = asyncio.new_event_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        cb = MetricsCallback(queue=queue, loop=loop, log_interval=10)
        cb.model = MagicMock()
        cb.model.logger = None
        cb.num_timesteps = 10
        cb.locals = {"infos": []}

        result = cb._on_step()
        assert result is True
        loop.close()

    def test_metrics_callback_skips_non_interval(self) -> None:
        loop = asyncio.new_event_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        cb = MetricsCallback(queue=queue, loop=loop, log_interval=10)
        cb.model = MagicMock()
        cb.num_timesteps = 7
        cb.locals = {"infos": []}

        result = cb._on_step()
        assert result is True
        loop.close()

    def test_metrics_tracks_wins(self) -> None:
        loop = asyncio.new_event_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        cb = MetricsCallback(queue=queue, loop=loop, log_interval=10)
        cb.model = MagicMock()
        cb.model.logger = None
        cb.num_timesteps = 10
        cb.locals = {"infos": [{"score1": MAX_SCORE, "score2": 3}]}

        cb._on_step()
        assert len(cb._episode_wins) == 1
        assert cb._episode_wins[0] is True
        loop.close()


class TestStopEventCallback:
    """Cover _StopEventCallback."""

    def test_stop_event_continues_when_not_set(self) -> None:
        from backend.rl.trainer import _StopEventCallback, TrainingManager

        event = threading.Event()
        pause_event = threading.Event()
        manager = TrainingManager()
        cb = _StopEventCallback(event, pause_event, manager)
        assert cb._on_step() is True

    def test_stop_event_stops_when_set(self) -> None:
        from backend.rl.trainer import _StopEventCallback, TrainingManager

        event = threading.Event()
        event.set()
        pause_event = threading.Event()
        manager = TrainingManager()
        cb = _StopEventCallback(event, pause_event, manager)
        assert cb._on_step() is False


# ─── rl/trainer.py ───


class TestTrainingManagerInit:
    """Cover TrainingManager constructor and simple methods."""

    def test_initial_status_is_stopped(self) -> None:
        from backend.rl.trainer import TrainingManager

        tm = TrainingManager()
        assert tm.status == "stopped"

    def test_set_bot_level_valid(self) -> None:
        from backend.rl.trainer import TrainingManager

        tm = TrainingManager()
        tm.set_bot_level(3)
        assert tm._bot_level == 3

    def test_set_bot_level_invalid(self) -> None:
        from backend.rl.trainer import TrainingManager

        tm = TrainingManager()
        with pytest.raises(ValueError, match="Bot level must be 1-5"):
            tm.set_bot_level(0)

    def test_set_bot_level_invalid_high(self) -> None:
        from backend.rl.trainer import TrainingManager

        tm = TrainingManager()
        with pytest.raises(ValueError, match="Bot level must be 1-5"):
            tm.set_bot_level(6)

    def test_default_hyperparams_exist(self) -> None:
        from backend.rl.trainer import DEFAULT_HYPERPARAMS

        assert "learning_rate" in DEFAULT_HYPERPARAMS
        assert "n_steps" in DEFAULT_HYPERPARAMS
        assert "batch_size" in DEFAULT_HYPERPARAMS

    def test_find_latest_checkpoint_no_dir(self) -> None:
        from backend.rl.trainer import TrainingManager

        tm = TrainingManager(model_dir="/nonexistent_dir")
        tm._experiment_id = "test"
        assert tm._find_latest_checkpoint() is None


# ─── rl/evaluator.py ───


class TestModelEvaluator:
    """Cover ModelEvaluator with a quickly trained model."""

    def test_evaluate_returns_eval_result(self) -> None:
        try:
            from stable_baselines3 import PPO
        except ImportError:
            pytest.skip("stable-baselines3 not installed")

        from backend.rl.evaluator import EvalResult, ModelEvaluator

        # Train a minimal model
        env = PikachuVolleyballEnv(bot_level=1, max_steps=500)
        model = PPO("MlpPolicy", env, n_steps=64, batch_size=32, n_epochs=2, verbose=0)
        model.learn(total_timesteps=128)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "eval_model")
            model.save(path)

            evaluator = ModelEvaluator()
            result = evaluator.evaluate(path, bot_level=1, n_games=3)

        assert isinstance(result, EvalResult)
        assert result.n_games == 3
        assert 0.0 <= result.win_rate <= 1.0
        assert result.avg_score >= 0
        assert result.avg_rally_length >= 0
        assert result.bot_level == 1
        env.close()

    def test_compare_checkpoints(self) -> None:
        try:
            from stable_baselines3 import PPO
        except ImportError:
            pytest.skip("stable-baselines3 not installed")

        from backend.rl.evaluator import ModelEvaluator

        env = PikachuVolleyballEnv(bot_level=1, max_steps=500)
        model = PPO("MlpPolicy", env, n_steps=64, batch_size=32, n_epochs=2, verbose=0)
        model.learn(total_timesteps=128)

        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = str(Path(tmpdir) / "ckpt1")
            p2 = str(Path(tmpdir) / "ckpt2")
            model.save(p1)
            model.save(p2)

            evaluator = ModelEvaluator()
            results = evaluator.compare_checkpoints([p1, p2], bot_level=1, n_games=2)

        assert len(results) == 2
        env.close()


# ─── rl/env.py extra coverage ───


class TestEnvAutopower:
    """Cover auto power-hit activation (line ~82-92 in env.py)."""

    def test_auto_power_hit_when_jumping_near_ball(self) -> None:
        env = PikachuVolleyballEnv(bot_level=1, max_steps=3000)
        env.reset()
        # Force player1 to be jumping and near the ball
        env._game._state.player1.is_jumping = True
        env._game._state.player1.y = PLAYER_GROUND_Y - 40
        env._game._state.ball.x = env._game._state.player1.x + 10
        env._game._state.ball.y = env._game._state.player1.y + 10

        # Action 3 = jump (y_dir=-1), but since already jumping, the auto power-hit triggers
        obs, reward, _, _, _ = env.step(3)
        assert obs.shape == (18,)
        env.close()


class TestActionMap:
    """Cover all entries in ACTION_MAP."""

    def test_all_actions_are_valid(self) -> None:
        assert len(ACTION_MAP) == 12
        for action_id, inp in ACTION_MAP.items():
            assert isinstance(inp, PlayerInput)
            assert inp.x_dir in (-1, 0, 1)
            assert inp.y_dir in (-1, 0, 1)
