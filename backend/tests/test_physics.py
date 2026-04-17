"""Physics regression tests — faithful port of gorisanson/pikachu-volleyball.

These tests pin down the exact numerical behavior of the engine against the
original JS source (src/resources/js/physics.js). If any of these tests break,
the engine has drifted from the reference implementation.

Reference constants (from physics.js):
  GROUND_WIDTH = 432, GROUND_HEIGHT = 304
  GROUND_HALF_WIDTH = 216  (== NET_PILLAR_X)
  NET_PILLAR_HALF_WIDTH = 25
  NET_PILLAR_TOP_TOP_Y_COORD = 176
  NET_PILLAR_TOP_BOTTOM_Y_COORD = 192
  PLAYER_LENGTH = 64  (half = 32)
  PLAYER_TOUCHING_GROUND_Y_COORD = 244
  BALL_RADIUS = 20
  BALL_TOUCHING_GROUND_Y_COORD = 252
"""

from __future__ import annotations

import random

import pytest

from backend.game.constants import (
    BALL_GROUND_Y,
    BALL_INIT_Y_VELOCITY,
    BALL_MIN_REFLECT_VY_ABS,
    BALL_PLAYER_COLLISION_DIST,
    BALL_RADIUS,
    BALL_SERVE_X_P1,
    BALL_SERVE_X_P2,
    BALL_SERVE_Y,
    GRAVITY,
    GROUND_HEIGHT,
    GROUND_WIDTH,
    LYING_DOWN_DURATION,
    MAX_SCORE,
    NET_PILLAR_HALF_WIDTH,
    NET_PILLAR_TOP_BOTTOM_Y,
    NET_PILLAR_TOP_Y,
    NET_PILLAR_X,
    PLAYER_DIVE_SPEED,
    PLAYER_DIVE_VELOCITY,
    PLAYER_GROUND_Y,
    PLAYER_HALF_LENGTH,
    PLAYER_INIT_X_P1,
    PLAYER_INIT_X_P2,
    PLAYER_JUMP_VELOCITY,
    PLAYER_SPEED,
)
from backend.game.engine import PikachuVolleyball, PlayerInput

NOOP = PlayerInput(x_dir=0, y_dir=0, power_hit=False)


# ─── Constants parity ───────────────────────────────────────────────────────


class TestConstantsParity:
    """All constants must match original physics.js exactly."""

    def test_court_dimensions(self) -> None:
        assert GROUND_WIDTH == 432
        assert GROUND_HEIGHT == 304

    def test_net_geometry(self) -> None:
        assert NET_PILLAR_X == 216  # == GROUND_WIDTH // 2
        assert NET_PILLAR_HALF_WIDTH == 25
        assert NET_PILLAR_TOP_Y == 176
        assert NET_PILLAR_TOP_BOTTOM_Y == 192

    def test_player_geometry(self) -> None:
        assert PLAYER_HALF_LENGTH == 32  # half of PLAYER_LENGTH=64
        assert PLAYER_GROUND_Y == 244

    def test_player_speeds(self) -> None:
        assert PLAYER_SPEED == 6
        assert PLAYER_DIVE_SPEED == 8
        assert PLAYER_JUMP_VELOCITY == -16
        assert PLAYER_DIVE_VELOCITY == -5

    def test_player_spawn_positions(self) -> None:
        assert PLAYER_INIT_X_P1 == 36
        assert PLAYER_INIT_X_P2 == 396  # GROUND_WIDTH - 36

    def test_ball_geometry(self) -> None:
        assert BALL_RADIUS == 20
        assert BALL_GROUND_Y == 252
        assert BALL_INIT_Y_VELOCITY == 1

    def test_ball_serve_positions(self) -> None:
        assert BALL_SERVE_X_P1 == 56
        assert BALL_SERVE_X_P2 == 376  # GROUND_WIDTH - 56
        assert BALL_SERVE_Y == 0

    def test_gravity(self) -> None:
        assert GRAVITY == 1

    def test_lying_down_duration(self) -> None:
        assert LYING_DOWN_DURATION == 3

    def test_collision_distance_is_half_length(self) -> None:
        # Original uses PLAYER_HALF_LENGTH, NOT PLAYER_HALF_LENGTH + BALL_RADIUS
        assert BALL_PLAYER_COLLISION_DIST == PLAYER_HALF_LENGTH == 32

    def test_min_reflect_vy_magnitude(self) -> None:
        assert BALL_MIN_REFLECT_VY_ABS == 15

    def test_max_score(self) -> None:
        assert MAX_SCORE == 15


# ─── Ball-player collision distance boundary ──────────────────────────────────


class TestCollisionBoundary:
    """Collision triggers iff |dx| <= 32 AND |dy| <= 32."""

    def test_collide_at_exact_distance(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Place ball exactly 32px away on both axes — should collide.
        game._state.ball.x = game._state.player1.x + PLAYER_HALF_LENGTH
        game._state.ball.y = game._state.player1.y - PLAYER_HALF_LENGTH
        game._state.ball.vx = 0
        game._state.ball.vy = 5  # falling

        prev_vy = game._state.ball.vy
        new_state = game.step(NOOP, NOOP)
        # Collision reflects vy negative (with min magnitude 15).
        assert new_state.ball.vy < 0 or new_state.is_round_over
        assert abs(new_state.ball.vy) >= BALL_MIN_REFLECT_VY_ABS or new_state.is_round_over
        assert prev_vy > 0  # sanity

    def test_no_collide_just_beyond(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Ball at dx = 33 (one past boundary) — should NOT collide.
        game._state.ball.x = game._state.player1.x + PLAYER_HALF_LENGTH + 1
        game._state.ball.y = game._state.player1.y
        game._state.ball.vx = 0
        game._state.ball.vy = 5  # falling

        new_state = game.step(NOOP, NOOP)
        # No collision — vy keeps increasing from gravity, not flipped negative.
        assert new_state.ball.vy > 0 or new_state.is_round_over

    def test_no_collide_when_only_x_within(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # dx within 32, dy way outside.
        game._state.ball.x = game._state.player1.x
        game._state.ball.y = game._state.player1.y - 100
        game._state.ball.vx = 0
        game._state.ball.vy = 1

        new_state = game.step(NOOP, NOOP)
        # No collision — ball keeps falling.
        assert new_state.ball.vy > 0 or new_state.is_round_over


# ─── Minimum reflect vy magnitude ─────────────────────────────────────────────


class TestMinReflectVyMagnitude:
    """After collision, |vy| must be at least 15 (unless power hit overrides).

    Note: step() applies gravity in world update BEFORE ball-player collision,
    so the vy that collision sees is (input_vy + GRAVITY) unless the ball hit
    a wall/net/ground first.
    """

    @pytest.mark.parametrize("incoming_vy", [1, 3, 5, 10, 13])
    def test_small_incoming_vy_clamps_to_15(self, incoming_vy: int) -> None:
        game = PikachuVolleyball()
        game.reset()
        game._state.ball.x = game._state.player1.x
        game._state.ball.y = game._state.player1.y - 10
        game._state.ball.vx = 0
        game._state.ball.vy = incoming_vy
        # After world update: vy' = incoming_vy + 1 (gravity). If vy' < 15,
        # collision reflection clamps to -15.

        new_state = game.step(NOOP, NOOP)
        if not new_state.is_round_over:
            assert new_state.ball.vy == -BALL_MIN_REFLECT_VY_ABS

    @pytest.mark.parametrize("incoming_vy", [14, 15, 20, 30])
    def test_large_incoming_vy_preserved(self, incoming_vy: int) -> None:
        game = PikachuVolleyball()
        game.reset()
        game._state.ball.x = game._state.player1.x
        game._state.ball.y = game._state.player1.y - 10
        game._state.ball.vx = 0
        game._state.ball.vy = incoming_vy
        # After world update: vy' = incoming_vy + 1 (gravity). If vy' >= 15,
        # collision reflection is exactly -vy'.

        new_state = game.step(NOOP, NOOP)
        if not new_state.is_round_over:
            assert new_state.ball.vy == -(incoming_vy + GRAVITY)


# ─── Gravity application order ────────────────────────────────────────────────


class TestGravityOrdering:
    """Gravity applied AT END of ball update — next frame's vy = this vy + 1."""

    def test_gravity_accumulates_by_one_per_frame(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Position ball in mid-air away from players/net/ground/ceiling.
        game._state.ball.x = 100
        game._state.ball.y = 100
        game._state.ball.vx = 0
        game._state.ball.vy = 0

        prev_vy = game._state.ball.vy
        for _ in range(5):
            game.step(NOOP, NOOP)
            # Each frame vy should increase by exactly GRAVITY=1.
            assert game._state.ball.vy == prev_vy + GRAVITY
            prev_vy = game._state.ball.vy


# ─── Net collision split: top vs side ─────────────────────────────────────────


class TestNetCollisionSplit:
    """y <= 192 is top-of-pillar (vy flip); y > 192 is side (vx reflect)."""

    def test_top_of_pillar_flips_vy(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # y in [NET_PILLAR_TOP_Y, NET_PILLAR_TOP_BOTTOM_Y] == [176, 192]
        game._state.ball.x = NET_PILLAR_X
        game._state.ball.y = NET_PILLAR_TOP_BOTTOM_Y - 1  # 191
        game._state.ball.vx = 0
        game._state.ball.vy = 5  # falling onto pillar top

        new_state = game.step(NOOP, NOOP)
        # Top-of-pillar: vy flipped upward.
        assert new_state.ball.vy < 5 or new_state.is_round_over

    def test_side_of_pillar_reflects_vx_left(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        game._state.ball.x = NET_PILLAR_X - 5  # left of net
        game._state.ball.y = NET_PILLAR_TOP_BOTTOM_Y + 10  # below top
        game._state.ball.vx = 5  # moving INTO net (right)
        game._state.ball.vy = 0

        new_state = game.step(NOOP, NOOP)
        # Ball on left side of net — vx should be forced negative (away).
        assert new_state.ball.vx <= 0 or new_state.is_round_over

    def test_side_of_pillar_reflects_vx_right(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        game._state.ball.x = NET_PILLAR_X + 5  # right of net
        game._state.ball.y = NET_PILLAR_TOP_BOTTOM_Y + 10
        game._state.ball.vx = -5  # moving INTO net (left)
        game._state.ball.vy = 0

        new_state = game.step(NOOP, NOOP)
        # Ball on right side of net — vx should be forced positive (away).
        assert new_state.ball.vx >= 0 or new_state.is_round_over


class TestNetVxReversalHardened:
    """QA-hotfix regression guard — pin exact sign-flip semantics.

    Pins the behavior where a ball moving INTO the net from either side
    gets its vx reversed. Uses explicit sign-flip assertions (not just
    ``<= 0``) and multi-frame scenarios so that any future edit which
    preserves "ball loses vx" but drops "ball bounces away" still fails.
    """

    def test_left_side_moving_right_into_net_gets_vx_flipped(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        game._state.ball.x = NET_PILLAR_X - 10  # inside 25px net zone
        game._state.ball.y = NET_PILLAR_TOP_BOTTOM_Y + 20  # side-of-pillar
        game._state.ball.vx = 8  # moving INTO net
        game._state.ball.vy = 0

        new_state = game.step(NOOP, NOOP)
        # Original JS: ball.xVelocity = -Math.abs(ball.xVelocity) on left side.
        # So 8 must flip to -8 (magnitude preserved, direction reversed).
        assert new_state.ball.vx == -8

    def test_right_side_moving_left_into_net_gets_vx_flipped(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        game._state.ball.x = NET_PILLAR_X + 10
        game._state.ball.y = NET_PILLAR_TOP_BOTTOM_Y + 20
        game._state.ball.vx = -8  # moving INTO net
        game._state.ball.vy = 0

        new_state = game.step(NOOP, NOOP)
        # Original: ball.xVelocity = Math.abs(ball.xVelocity) on right side.
        assert new_state.ball.vx == 8

    def test_ball_actually_moves_away_after_net_contact(self) -> None:
        """Multi-frame guard: after hitting net, the ball's x position must
        travel AWAY from the net center on the next frame.

        This catches a regression where vx is reset to 0 (no reversal) but the
        ball simply stops — tests asserting `vx <= 0` would pass while play
        physics still felt broken.
        """
        game = PikachuVolleyball()
        game.reset()
        game._state.ball.x = NET_PILLAR_X - 10
        game._state.ball.y = NET_PILLAR_TOP_BOTTOM_Y + 20
        game._state.ball.vx = 6
        game._state.ball.vy = 0

        game.step(NOOP, NOOP)  # net contact — vx flipped to -6 this frame
        x_after_contact = game._state.ball.x

        game.step(NOOP, NOOP)  # next frame — ball should have moved LEFT
        x_next = game._state.ball.x

        assert x_next < x_after_contact, (
            f"Ball must travel away from net after collision "
            f"(x_after_contact={x_after_contact}, x_next={x_next})"
        )

    def test_net_collision_preserves_vx_magnitude(self) -> None:
        """Original JS uses -Math.abs / +Math.abs, NOT a damped reflection.
        So |vx| after collision must equal |vx| before (no energy loss).
        """
        for start_vx in (3, 7, 12, 15):
            game = PikachuVolleyball()
            game.reset()
            game._state.ball.x = NET_PILLAR_X - 10
            game._state.ball.y = NET_PILLAR_TOP_BOTTOM_Y + 20
            game._state.ball.vx = start_vx
            game._state.ball.vy = 0

            game.step(NOOP, NOOP)
            assert abs(game._state.ball.vx) == start_vx, (
                f"|vx| changed on net collision: {start_vx} → {game._state.ball.vx}"
            )


# ─── Ceiling handling ─────────────────────────────────────────────────────────


class TestCeilingReflection:
    """Original: if future_y < 0 then vy = 1 (NOT flip)."""

    def test_ceiling_forces_vy_to_one(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Ball trying to go above screen.
        game._state.ball.x = 100
        game._state.ball.y = 5
        game._state.ball.vx = 0
        game._state.ball.vy = -20  # moving up fast → future_y = -15 < 0

        game.step(NOOP, NOOP)
        # After the frame: vy was set to 1, ball moved down by 1, then gravity added 1.
        # Ball vy at end of step = 1 (forced) + 1 (gravity) = 2
        assert game._state.ball.vy == 2


# ─── Ball never leaves screen bounds (stress test) ────────────────────────────


class TestBallStaysOnScreen:
    """Stress test: random play, ball position must stay within screen."""

    def test_ball_x_stays_in_bounds_random_play(self) -> None:
        random.seed(42)
        game = PikachuVolleyball()
        game.reset()

        for _ in range(3000):
            p1 = PlayerInput(
                x_dir=random.choice([-1, 0, 1]),
                y_dir=random.choice([-1, 0]),
                power_hit=random.random() < 0.3,
            )
            p2 = PlayerInput(
                x_dir=random.choice([-1, 0, 1]),
                y_dir=random.choice([-1, 0]),
                power_hit=random.random() < 0.3,
            )
            state = game.step(p1, p2)
            # Ball should stay within screen horizontally.
            # Left bound uses BALL_RADIUS, right bound uses GROUND_WIDTH
            # (original asymmetric quirk).
            assert -BALL_RADIUS <= state.ball.x <= GROUND_WIDTH + BALL_RADIUS, (
                f"Ball escaped: x={state.ball.x}"
            )
            # Ball y: at/above 0 (modulo one-frame overshoot) and at/above ground.
            assert state.ball.y <= BALL_GROUND_Y + BALL_RADIUS, (
                f"Ball below ground: y={state.ball.y}"
            )
            if state.is_round_over:
                state = game.reset()


# ─── Serve configuration ─────────────────────────────────────────────────────


class TestServePositions:
    """Serves must spawn at the correct x,y with the correct vy."""

    def test_player1_serve_position(self) -> None:
        game = PikachuVolleyball()
        state = game.reset()
        assert state.serving_player == 1
        assert state.ball.x == BALL_SERVE_X_P1
        assert state.ball.y == BALL_SERVE_Y
        assert state.ball.vy == BALL_INIT_Y_VELOCITY

    def test_player2_serve_position(self) -> None:
        game = PikachuVolleyball()
        # Force score so next reset spawns a p2 serve.
        game._state.score2 = 5
        game._state = game._create_initial_state(serving_player=2)
        state = game._state
        assert state.ball.x == BALL_SERVE_X_P2
        assert state.ball.y == BALL_SERVE_Y
        assert state.ball.vy == BALL_INIT_Y_VELOCITY


# ─── Player half-court clamping ──────────────────────────────────────────────


class TestPlayerCourtBounds:
    """Players clamped to [PLAYER_HALF_LENGTH, NET_PILLAR_X - PLAYER_HALF_LENGTH]
    for P1 and [NET_PILLAR_X + PLAYER_HALF_LENGTH, GROUND_WIDTH - PLAYER_HALF_LENGTH]
    for P2.

    We freeze the ball far above the ground to prevent round-resets that
    would reset player positions.
    """

    @staticmethod
    def _freeze_ball(game: PikachuVolleyball) -> None:
        """Keep ball floating high above the ground so no round ends."""
        game._state.ball.x = NET_PILLAR_X
        game._state.ball.y = 20
        game._state.ball.vx = 0
        game._state.ball.vy = 0

    def test_p1_cannot_cross_net(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        move_right = PlayerInput(x_dir=1, y_dir=0, power_hit=False)
        for _ in range(100):
            self._freeze_ball(game)
            game.step(move_right, NOOP)
        # Max p1.x = NET_PILLAR_X - PLAYER_HALF_LENGTH = 216 - 32 = 184
        assert game._state.player1.x == NET_PILLAR_X - PLAYER_HALF_LENGTH

    def test_p2_cannot_cross_net(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        move_left = PlayerInput(x_dir=-1, y_dir=0, power_hit=False)
        for _ in range(100):
            self._freeze_ball(game)
            game.step(NOOP, move_left)
        # Min p2.x = NET_PILLAR_X + PLAYER_HALF_LENGTH = 216 + 32 = 248
        assert game._state.player2.x == NET_PILLAR_X + PLAYER_HALF_LENGTH

    def test_p1_cannot_exit_left_wall(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        move_left = PlayerInput(x_dir=-1, y_dir=0, power_hit=False)
        for _ in range(100):
            self._freeze_ball(game)
            game.step(move_left, NOOP)
        # Min p1.x = PLAYER_HALF_LENGTH = 32
        assert game._state.player1.x == PLAYER_HALF_LENGTH

    def test_p2_cannot_exit_right_wall(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        move_right = PlayerInput(x_dir=1, y_dir=0, power_hit=False)
        for _ in range(100):
            self._freeze_ball(game)
            game.step(NOOP, move_right)
        # Max p2.x = GROUND_WIDTH - PLAYER_HALF_LENGTH = 432 - 32 = 400
        assert game._state.player2.x == GROUND_WIDTH - PLAYER_HALF_LENGTH


# ─── Jump and dive mechanics ─────────────────────────────────────────────────


class TestJumpAndDive:
    """Jump velocity is -16; dive triggers from grounded + power_hit + x_dir."""

    def test_jump_sets_correct_initial_velocity(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        jump = PlayerInput(x_dir=0, y_dir=-1, power_hit=False)
        game.step(jump, NOOP)
        # After stepping, player1 is now airborne.
        # The jump set vy = -16, then the update loop runs:
        #   y += vy (-16), gravity adds 1 → vy becomes -15 at end of frame
        assert game._state.player1.is_jumping
        assert game._state.player1.vy == PLAYER_JUMP_VELOCITY + GRAVITY  # -15

    def test_dive_triggers_with_power_hit_and_x_direction(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Grounded + power_hit + x_dir != 0 → dive
        dive = PlayerInput(x_dir=1, y_dir=0, power_hit=True)
        game.step(dive, NOOP)
        assert game._state.player1.is_diving
        assert game._state.player1.diving_direction == 1

    def test_dive_direction_tracks_left_input(self) -> None:
        # physics.js:597 — player.divingDirection = userInput.xDirection.
        # Left input (x_dir=-1) must record -1, not default 0 or the
        # absolute value. FE dive sprite orientation depends on the sign.
        game = PikachuVolleyball()
        game.reset()
        dive_left = PlayerInput(x_dir=-1, y_dir=0, power_hit=True)
        game.step(dive_left, NOOP)
        assert game._state.player1.is_diving
        assert game._state.player1.diving_direction == -1

    def test_dive_direction_resets_on_landing(self) -> None:
        # physics.js:564-578 — on landing, state=3 → state=4 and
        # diving flags clear. diving_direction must reset to 0 so the
        # next idle/jump frame doesn't carry a stale sign.
        game = PikachuVolleyball()
        game.reset()
        game._state.player1.is_diving = True
        game._state.player1.diving_direction = 1
        game._state.player1.y = PLAYER_GROUND_Y - 3
        game._state.player1.vy = 10  # will hit ground
        game.step(NOOP, NOOP)
        assert not game._state.player1.is_diving
        assert game._state.player1.diving_direction == 0

    def test_dive_landing_starts_lying_down(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # state=3 is "diving" per the port (physics.js Player.state).
        game._state.player1.state = 3
        game._state.player1.diving_direction = 1
        game._state.player1.y = PLAYER_GROUND_Y - 3
        game._state.player1.vy = 10  # will hit ground
        game.step(NOOP, NOOP)
        assert game._state.player1.lying_down_duration == LYING_DOWN_DURATION
        assert not game._state.player1.is_diving

    def test_lying_down_blocks_movement(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # state=4 is "lying down after diving"; lying_down_duration_left
        # drives the internal counter that the port decrements each frame.
        game._state.player1.state = 4
        game._state.player1.lying_down_duration_left = 3
        game._state.player1.sync_derived_flags()
        initial_x = game._state.player1.x
        move_right = PlayerInput(x_dir=1, y_dir=0, power_hit=False)
        game.step(move_right, NOOP)
        # Position frozen during lying down.
        assert game._state.player1.x == initial_x


# ─── Scoring side ──────────────────────────────────────────────────────────────


class TestScoringSide:
    """Ball grounding on p1 side → p2 scores; on p2 side → p1 scores."""

    def test_ball_on_p1_side_scores_for_p2(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        game._state.ball.x = NET_PILLAR_X - 50
        game._state.ball.y = BALL_GROUND_Y - 1
        game._state.ball.vy = 5
        prev_score2 = game._state.score2
        new_state = game.step(NOOP, NOOP)
        assert new_state.score2 == prev_score2 + 1
        assert new_state.serving_player == 2

    def test_ball_on_p2_side_scores_for_p1(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        game._state.ball.x = NET_PILLAR_X + 50
        game._state.ball.y = BALL_GROUND_Y - 1
        game._state.ball.vy = 5
        prev_score1 = game._state.score1
        new_state = game.step(NOOP, NOOP)
        assert new_state.score1 == prev_score1 + 1
        assert new_state.serving_player == 1


# ─── Punch effect markers don't alter position ───────────────────────────────


class TestCollisionDoesNotRefireWithinBox:
    """Per original physics.js: once a ball enters the 32px collision box,
    collision fires ONCE. Subsequent frames while ball is still in the box
    do not re-reflect velocity. Flag resets when ball leaves the box."""

    def test_second_frame_in_box_does_not_reflect_vy_again(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Make player jump up to 100 so ball can meet them in mid-air without
        # dropping the ball to the ground.
        state = game._state
        state.player1.y = 100
        state.player1.is_jumping = True
        state.ball.x = state.player1.x
        state.ball.y = 120  # 20px below player head, inside 32px box
        state.ball.vx = 0
        state.ball.vy = 5  # falling slowly

        # Frame 1: collision fires. Expect vy reflected to negative (≤ -15).
        game.step(NOOP, NOOP)
        assert game._state.player1.is_collision_with_ball_happened is True
        vy_after_first_hit = game._state.ball.vy
        assert vy_after_first_hit < 0, "Collision should reflect vy negative"

        # Keep player in mid-air and force the ball back inside the box
        # with the same falling velocity (as if physics were re-applying).
        state.player1.y = 100
        state.player1.is_jumping = True
        state.ball.x = state.player1.x
        state.ball.y = 120
        state.ball.vx = 0
        state.ball.vy = 5

        # Frame 2: ball still in box, flag still True → NO reflection.
        game.step(NOOP, NOOP)
        # vy at end = input vy (5) + gravity (1) = 6. No reflection fired.
        assert game._state.ball.vy == 6, (
            f"Expected vy=6 (no reflection); got vy={game._state.ball.vy}"
        )

    def test_flag_resets_when_ball_leaves_box(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Enter box (mid-air).
        state = game._state
        state.player1.y = 100
        state.player1.is_jumping = True
        state.ball.x = state.player1.x
        state.ball.y = 120
        state.ball.vx = 0
        state.ball.vy = 5
        game.step(NOOP, NOOP)
        assert game._state.player1.is_collision_with_ball_happened is True

        # Move ball far away (out of box) but still in air.
        state.ball.x = state.player1.x + 200
        state.ball.y = 50
        state.ball.vx = 0
        state.ball.vy = 0
        game.step(NOOP, NOOP)
        # Flag should reset because ball is no longer in the box.
        assert game._state.player1.is_collision_with_ball_happened is False


class TestPunchEffectMarkersDoNotMovePosition:
    """punch_effect_x/y are graphic markers only."""

    def test_power_hit_does_not_teleport_ball(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Put p1 in a jumping state near ball so power hit applies.
        game._state.player1.is_jumping = True
        game._state.player1.y = PLAYER_GROUND_Y - 40
        game._state.ball.x = game._state.player1.x + 5
        game._state.ball.y = game._state.player1.y + 5
        game._state.ball.vx = 0
        game._state.ball.vy = 3

        ball_x_before = game._state.ball.x
        ball_y_before = game._state.ball.y
        power = PlayerInput(x_dir=1, y_dir=-1, power_hit=True)
        game.step(power, NOOP)
        # Position can change due to new vx/vy in NEXT frame update, but the
        # per-frame movement should be bounded by the post-collision velocity,
        # NOT by an additive punch_effect jump.
        dx = game._state.ball.x - ball_x_before
        dy = game._state.ball.y - ball_y_before
        assert abs(dx) < 50  # bounded by power-hit vx magnitude
        assert abs(dy) < 50


class TestBallIsPowerHitFlag:
    """Ball carries an is_power_hit flag for FE hyper/trail rendering.

    Matches original physics.js: ball.isPowerHit is set true inside the
    power-hit branch of processCollisionBetweenBallAndPlayer, false in
    the non-power-hit branch. Persists between collisions until the next
    collision flips it.
    """

    def test_flag_starts_false_on_fresh_ball(self) -> None:
        game = PikachuVolleyball()
        state = game.reset()
        assert state.ball.is_power_hit is False

    def test_power_hit_collision_sets_flag_true(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # state=1 is "jumping" per the port. The power_hit input below
        # then transitions state 1 → 2 inside _update_player, and the
        # ball-player collision check keys off state==2 for the power
        # branch (matches physics.js:709).
        game._state.player1.state = 1
        game._state.player1.sync_derived_flags()
        game._state.player1.y = PLAYER_GROUND_Y - 40
        game._state.ball.x = game._state.player1.x
        game._state.ball.y = game._state.player1.y
        game._state.ball.vx = 0
        game._state.ball.vy = 3
        power = PlayerInput(x_dir=1, y_dir=-1, power_hit=True)
        state = game.step(power, NOOP)
        assert state.ball.is_power_hit is True

    def test_non_power_collision_sets_flag_false(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Not jumping — collision cannot be a power hit.
        game._state.player1.is_jumping = False
        game._state.ball.x = game._state.player1.x
        game._state.ball.y = game._state.player1.y - PLAYER_HALF_LENGTH + 1
        game._state.ball.vx = 0
        game._state.ball.vy = 5
        # Pre-seed True so we can observe the flip to False.
        game._state.ball.is_power_hit = True
        state = game.step(NOOP, NOOP)
        assert state.ball.is_power_hit is False

    def test_flag_persists_between_collisions(self) -> None:
        """Flag keeps its last-collision value when no new collision occurs."""
        game = PikachuVolleyball()
        game.reset()
        # Park the ball far from both players so no collision fires.
        game._state.ball.x = NET_PILLAR_X
        game._state.ball.y = 50
        game._state.ball.vx = 0
        game._state.ball.vy = 0
        game._state.ball.is_power_hit = True  # prior power hit
        state = game.step(NOOP, NOOP)
        # No collision happened this frame → flag unchanged.
        assert state.ball.is_power_hit is True
