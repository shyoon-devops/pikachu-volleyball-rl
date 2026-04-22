"""Tests for the LoadedPolicyBot wrapper.

SB3 is never actually imported here — a stub policy loader lets us
exercise the mirroring + action-mapping + obs-shape paths without a
real checkpoint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from backend.game.constants import GROUND_WIDTH, NET_PILLAR_X
from backend.game.engine import (
    BallState,
    GameState,
    PikachuVolleyball,
    PlayerInput,
    PlayerState,
)
from backend.rl.env import ACTION_MAP
from backend.rl.loaded_policy_bot import (
    LoadedPolicyBot,
    _action_mirror_x_dir,
)


# ─── Test doubles ─────────────────────────────────────────────────────


class _StubPolicy:
    """Captures the last-observed obs + returns a scripted action."""

    def __init__(self, action: int) -> None:
        self.action = int(action)
        self.last_obs: np.ndarray | None = None
        self.last_deterministic: bool | None = None

    def predict(
        self,
        observation: np.ndarray,
        *,
        deterministic: bool = True,
    ) -> tuple[np.ndarray, Any]:
        self.last_obs = np.asarray(observation, dtype=np.float32).copy()
        self.last_deterministic = bool(deterministic)
        return np.array(self.action), None


def _make_state() -> GameState:
    """Reset state via the engine so all derived fields are in sync."""
    return PikachuVolleyball().reset()


# ─── Action-mirror helper ─────────────────────────────────────────────


class TestActionMirror:
    def test_noop_and_vertical_actions_unchanged(self) -> None:
        for a in (0, 3, 6, 9):
            assert _action_mirror_x_dir(a) == a

    def test_left_right_swapped(self) -> None:
        assert _action_mirror_x_dir(1) == 2
        assert _action_mirror_x_dir(2) == 1

    def test_jump_with_direction_swapped(self) -> None:
        assert _action_mirror_x_dir(4) == 5
        assert _action_mirror_x_dir(5) == 4

    def test_power_with_direction_swapped(self) -> None:
        assert _action_mirror_x_dir(7) == 8
        assert _action_mirror_x_dir(8) == 7

    def test_jump_power_with_direction_swapped(self) -> None:
        assert _action_mirror_x_dir(10) == 11
        assert _action_mirror_x_dir(11) == 10


# ─── Basic action flow ────────────────────────────────────────────────


class TestGetActionAsPlayer1:
    def test_returns_action_from_map_for_p1(self) -> None:
        stub = _StubPolicy(action=2)  # "right"
        bot = LoadedPolicyBot(
            model_path="/tmp/not-real.zip",
            checkpoint_id="ck_test",
            policy_loader=lambda path: stub,
        )
        state = _make_state()
        inp = bot.get_action(state, is_player2=False)
        # No mirror for p1: action 2 → right.
        assert inp == ACTION_MAP[2]

    def test_deterministic_flag_forwarded(self) -> None:
        stub = _StubPolicy(action=0)
        bot = LoadedPolicyBot(
            model_path="/tmp/_.zip",
            checkpoint_id="ck_d",
            deterministic=False,
            policy_loader=lambda path: stub,
        )
        bot.get_action(_make_state(), is_player2=False)
        assert stub.last_deterministic is False

    def test_model_is_loaded_lazily(self) -> None:
        calls = [0]

        def loader(path: Path) -> _StubPolicy:
            calls[0] += 1
            return _StubPolicy(action=0)

        bot = LoadedPolicyBot(
            model_path="/tmp/_.zip",
            checkpoint_id="ck_lazy",
            policy_loader=loader,
        )
        assert calls[0] == 0  # no load during __init__
        bot.get_action(_make_state(), is_player2=False)
        assert calls[0] == 1
        bot.get_action(_make_state(), is_player2=False)
        # Second call must reuse the cached policy.
        assert calls[0] == 1


# ─── Side-mirror behavior for player 2 ────────────────────────────────


class TestGetActionAsPlayer2:
    def test_action_x_dir_flipped_for_p2(self) -> None:
        # Policy says "right" (action 2); as p2 the bot should MOVE LEFT
        # (toward the net) — the policy trained as p1 assumes its own
        # side is the left half.
        stub = _StubPolicy(action=2)
        bot = LoadedPolicyBot(
            model_path="/tmp/_.zip",
            checkpoint_id="ck_p2",
            policy_loader=lambda path: stub,
        )
        inp = bot.get_action(_make_state(), is_player2=True)
        assert inp == ACTION_MAP[1]  # flipped to "left"

    def test_obs_mirror_swaps_player_positions(self) -> None:
        stub = _StubPolicy(action=0)
        bot = LoadedPolicyBot(
            model_path="/tmp/_.zip",
            checkpoint_id="ck_mirror",
            policy_loader=lambda path: stub,
        )
        # Custom state: p1 at left, p2 at right, ball on right half.
        state = GameState(
            player1=PlayerState(x=80, y=244),
            player2=PlayerState(x=360, y=244),
            ball=BallState(x=300, y=100, vx=5, vy=-3),
            score1=4,
            score2=2,
            serving_player=1,
        )
        # As p1 — raw obs.
        bot.get_action(state, is_player2=False)
        raw = stub.last_obs.copy()

        # As p2 — mirrored obs. Reset history so delta is comparable.
        bot.reset_history()
        bot.get_action(state, is_player2=True)
        mirrored = stub.last_obs.copy()

        w = float(GROUND_WIDTH)
        # Index 0 is "me_x": for p1 it's player1.x=80 → normalized.
        # For p2 mirrored, "me_x" must be GROUND_WIDTH - player2.x = 72.
        assert raw[0] == pytest.approx(80 / w * 2 - 1)
        assert mirrored[0] == pytest.approx(72 / w * 2 - 1)
        # Index 5 is "opp_x": swapped accordingly.
        assert raw[5] == pytest.approx(360 / w * 2 - 1)
        assert mirrored[5] == pytest.approx((w - 80) / w * 2 - 1)

    def test_obs_mirror_flips_ball_vx_sign(self) -> None:
        # Use fresh bot instances for each path so the ball-history is
        # identical on both sides — keeps trajectory-delta indices
        # (12, 13) comparable if a future assertion wants to use them.
        state = GameState(
            player1=PlayerState(x=80, y=244),
            player2=PlayerState(x=360, y=244),
            ball=BallState(x=200, y=100, vx=8, vy=0),
        )
        stub_p1 = _StubPolicy(action=0)
        bot_p1 = LoadedPolicyBot(
            model_path="/tmp/_.zip",
            checkpoint_id="ck_vx_p1",
            policy_loader=lambda path: stub_p1,
        )
        bot_p1.get_action(state, is_player2=False)
        raw_ball_vx = stub_p1.last_obs[10]

        stub_p2 = _StubPolicy(action=0)
        bot_p2 = LoadedPolicyBot(
            model_path="/tmp/_.zip",
            checkpoint_id="ck_vx_p2",
            policy_loader=lambda path: stub_p2,
        )
        bot_p2.get_action(state, is_player2=True)
        mirrored_ball_vx = stub_p2.last_obs[10]

        # ball.vx=8 → raw positive; mirrored should be negative.
        assert raw_ball_vx > 0
        assert mirrored_ball_vx < 0
        assert raw_ball_vx == pytest.approx(-mirrored_ball_vx, abs=1e-6)

    def test_obs_mirror_flips_score_diff_sign(self) -> None:
        stub = _StubPolicy(action=0)
        bot = LoadedPolicyBot(
            model_path="/tmp/_.zip",
            checkpoint_id="ck_score",
            policy_loader=lambda path: stub,
        )
        state = GameState(
            player1=PlayerState(x=80, y=244),
            player2=PlayerState(x=360, y=244),
            ball=BallState(x=200, y=100),
            score1=7,
            score2=2,
            serving_player=1,
        )
        bot.get_action(state, is_player2=False)
        raw_diff = stub.last_obs[16]  # score_diff index
        bot.reset_history()
        bot.get_action(state, is_player2=True)
        mirrored_diff = stub.last_obs[16]
        # score1 - score2 = 5 for p1; mirrored sees score2 - score1 = -5.
        assert raw_diff > 0
        assert mirrored_diff < 0

    def test_obs_mirror_ball_side_reflects_my_half(self) -> None:
        stub = _StubPolicy(action=0)
        bot = LoadedPolicyBot(
            model_path="/tmp/_.zip",
            checkpoint_id="ck_side",
            policy_loader=lambda path: stub,
        )
        # Ball on p2's side (x > NET_PILLAR_X).
        state = GameState(
            player1=PlayerState(x=80, y=244),
            player2=PlayerState(x=360, y=244),
            ball=BallState(x=NET_PILLAR_X + 100, y=100),
        )
        bot.get_action(state, is_player2=False)
        raw_side = stub.last_obs[15]
        bot.reset_history()
        bot.get_action(state, is_player2=True)
        mirrored_side = stub.last_obs[15]
        # Ball on p2 side: from p1's POV "ball_side" is -1 (opponent's).
        # From p2's mirrored POV, the ball is on p2's (mirrored-left)
        # side → +1.
        assert raw_side == -1.0
        assert mirrored_side == 1.0


# ─── Obs shape contract ───────────────────────────────────────────────


class TestObsShape:
    def test_emits_18_float32(self) -> None:
        stub = _StubPolicy(action=0)
        bot = LoadedPolicyBot(
            model_path="/tmp/_.zip",
            checkpoint_id="ck_shape",
            policy_loader=lambda path: stub,
        )
        bot.get_action(_make_state(), is_player2=False)
        assert stub.last_obs.shape == (18,)
        assert stub.last_obs.dtype == np.float32

    def test_all_values_in_unit_range(self) -> None:
        stub = _StubPolicy(action=0)
        bot = LoadedPolicyBot(
            model_path="/tmp/_.zip",
            checkpoint_id="ck_range",
            policy_loader=lambda path: stub,
        )
        bot.get_action(_make_state(), is_player2=False)
        assert stub.last_obs.min() >= -1.0
        assert stub.last_obs.max() <= 1.0
