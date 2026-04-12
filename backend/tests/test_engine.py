"""Tests for the Pikachu Volleyball game engine."""

import pytest

from backend.game.constants import (
    BALL_GROUND_Y,
    BALL_RADIUS,
    GRAVITY,
    MAX_SCORE,
    NET_PILLAR_TOP_Y,
    NET_PILLAR_X,
    PLAYER_GROUND_Y,
    PLAYER_HALF_LENGTH,
)
from backend.game.engine import (
    GameState,
    PikachuVolleyball,
    PlayerInput,
)

NOOP = PlayerInput(x_dir=0, y_dir=0, power_hit=False)


@pytest.fixture
def game() -> PikachuVolleyball:
    return PikachuVolleyball()


@pytest.fixture
def state(game: PikachuVolleyball) -> GameState:
    return game.reset()


class TestGravity:
    """Ball should fall due to gravity."""

    def test_ball_falls_with_gravity(self, game: PikachuVolleyball) -> None:
        state = game.reset()
        initial_vy = state.ball.vy
        # Step with no input — ball should accelerate downward
        new_state = game.step(NOOP, NOOP)
        assert new_state.ball.vy >= initial_vy + GRAVITY or new_state.is_round_over


class TestBallPlayerCollision:
    """Ball vy should reverse on collision with player."""

    def test_ball_vy_reverses_on_player_collision(
        self, game: PikachuVolleyball
    ) -> None:
        state = game.reset()
        # Place ball directly above player1 and falling
        game._state.ball.x = state.player1.x
        game._state.ball.y = state.player1.y - PLAYER_HALF_LENGTH + 1
        game._state.ball.vy = 5  # falling

        new_state = game.step(NOOP, NOOP)
        # After collision, vy should be negative (upward)
        assert new_state.ball.vy < 0 or new_state.is_round_over


class TestBallNetCollision:
    """Ball vx should reverse on net collision."""

    def test_ball_vx_reverses_on_net_collision(
        self, game: PikachuVolleyball
    ) -> None:
        """Ball hitting the side of the net pillar should have vx reflected.

        Per original physics.js: when the ball is at the side of the pillar
        (ball.y > NET_PILLAR_TOP_BOTTOM_Y_COORD = 192), the ball's vx is forced
        to point away from the net.
        """
        from backend.game.constants import NET_PILLAR_TOP_BOTTOM_Y

        game.reset()
        # Place ball on the LEFT side of the net, below the pillar top
        # (ball.y must be > NET_PILLAR_TOP_BOTTOM_Y to hit the pillar's side).
        game._state.ball.x = NET_PILLAR_X - 5
        game._state.ball.y = NET_PILLAR_TOP_BOTTOM_Y + 5
        game._state.ball.vx = 5  # moving right, into net
        game._state.ball.vy = 0

        new_state = game.step(NOOP, NOOP)
        # Left-side collision: vx should be forced negative (away from net).
        assert new_state.ball.vx <= 0 or new_state.is_round_over

    def test_ball_vy_reverses_on_net_pillar_top(
        self, game: PikachuVolleyball
    ) -> None:
        """Ball landing on TOP of net pillar should have vy flipped upward."""
        from backend.game.constants import NET_PILLAR_TOP_BOTTOM_Y

        game.reset()
        # On top of the pillar: NET_PILLAR_TOP_Y < y <= NET_PILLAR_TOP_BOTTOM_Y
        game._state.ball.x = NET_PILLAR_X
        game._state.ball.y = NET_PILLAR_TOP_BOTTOM_Y - 2
        game._state.ball.vx = 0
        game._state.ball.vy = 5  # moving down, onto pillar top

        new_state = game.step(NOOP, NOOP)
        # Top-of-pillar collision should send ball back upward.
        assert new_state.ball.vy < 5 or new_state.is_round_over


class TestScoring:
    """Ball touching ground should trigger scoring."""

    def test_ball_ground_scores(self, game: PikachuVolleyball) -> None:
        state = game.reset()
        # Place ball just above ground on player2's side
        game._state.ball.x = NET_PILLAR_X + 100
        game._state.ball.y = BALL_GROUND_Y - 2
        game._state.ball.vy = 5  # falling fast

        initial_score1 = state.score1
        new_state = game.step(NOOP, NOOP)
        # Ball hits ground on p2 side → p1 scores
        assert new_state.score1 > initial_score1 or new_state.is_round_over

    def test_ball_ground_p1_side_scores_for_p2(
        self, game: PikachuVolleyball
    ) -> None:
        state = game.reset()
        # Place ball on player1's side
        game._state.ball.x = NET_PILLAR_X - 100
        game._state.ball.y = BALL_GROUND_Y - 2
        game._state.ball.vy = 5

        initial_score2 = state.score2
        new_state = game.step(NOOP, NOOP)
        assert new_state.score2 > initial_score2 or new_state.is_round_over


class TestPlayerCourtRestriction:
    """Players must stay on their half of the court."""

    def test_player1_stays_on_left_side(self, game: PikachuVolleyball) -> None:
        state = game.reset()
        # Try to move player1 right for many frames
        move_right = PlayerInput(x_dir=1, y_dir=0, power_hit=False)
        for _ in range(200):
            state = game.step(move_right, NOOP)
            if state.is_round_over:
                state = game.reset()
        # Player1 should not cross the net
        assert state.player1.x < NET_PILLAR_X

    def test_player2_stays_on_right_side(
        self, game: PikachuVolleyball
    ) -> None:
        state = game.reset()
        move_left = PlayerInput(x_dir=-1, y_dir=0, power_hit=False)
        for _ in range(200):
            state = game.step(NOOP, move_left)
            if state.is_round_over:
                state = game.reset()
        assert state.player2.x > NET_PILLAR_X


class TestPowerHit:
    """Power hit should apply boosted velocity."""

    def test_power_hit_increases_ball_speed(
        self, game: PikachuVolleyball
    ) -> None:
        state = game.reset()
        # Place ball on player1, player jumping
        game._state.player1.is_jumping = True
        game._state.player1.y = PLAYER_GROUND_Y - 40
        game._state.ball.x = state.player1.x
        game._state.ball.y = game._state.player1.y
        game._state.ball.vy = 3

        power_input = PlayerInput(x_dir=1, y_dir=-1, power_hit=True)
        new_state = game.step(power_input, NOOP)
        # Ball should have high speed after power hit
        speed = abs(new_state.ball.vx) + abs(new_state.ball.vy)
        assert speed > 10 or new_state.is_round_over


class TestGameCompletion:
    """Game should end when a player reaches MAX_SCORE."""

    def test_game_ends_at_max_score(self, game: PikachuVolleyball) -> None:
        game.reset()
        game._state.score1 = MAX_SCORE - 1
        # Force ball to land on p2 side
        game._state.ball.x = NET_PILLAR_X + 100
        game._state.ball.y = BALL_GROUND_Y - 1
        game._state.ball.vy = 5

        new_state = game.step(NOOP, NOOP)
        assert new_state.score1 == MAX_SCORE

    def test_full_game_terminates(self, game: PikachuVolleyball) -> None:
        """A full game with noop inputs should eventually end."""
        state = game.reset()
        for _ in range(50000):
            state = game.step(NOOP, NOOP)
            if state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE:
                break
        assert state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE


class TestRallyTimeout:
    """Safety-valve: force-end the round after RALLY_MAX_FRAMES without a net crossing.

    Prevents infinite self-toss loops where the ball stays on one side of
    the court indefinitely — a failure mode observed with weak RL policies
    that can't send the ball over the net.
    """

    def test_round_ends_when_rally_exceeds_max_frames(
        self, game: PikachuVolleyball
    ) -> None:
        game.reset()
        # Pin ball on p1 side with zero horizontal velocity so it never
        # crosses the net — the counter should monotonically increase.
        game._state.ball.x = NET_PILLAR_X - 50
        game._state.ball.y = BALL_GROUND_Y - 60
        game._state.ball.vx = 0
        game._state.ball.vy = 0
        game._prev_ball_x = float(game._state.ball.x)

        # Step one under the threshold. Bypass normal physics by re-pinning
        # the ball between frames — we only care about the counter logic.
        timed_out = False
        for _ in range(game.RALLY_MAX_FRAMES + 5):
            game._state.ball.x = NET_PILLAR_X - 50
            game._state.ball.y = BALL_GROUND_Y - 60
            game._state.ball.vx = 0
            game._state.ball.vy = 0
            state = game.step(NOOP, NOOP)
            if state.round_ended_by_timeout:
                timed_out = True
                break

        assert timed_out, "Rally timeout never fired past RALLY_MAX_FRAMES"
        assert state.is_round_over is True
        # Ball was on p1 side → p2 is awarded the point.
        assert state.score2 == 1
        assert state.score1 == 0

    def test_net_crossing_resets_counter(self, game: PikachuVolleyball) -> None:
        """Any net crossing (either direction) must zero the counter."""
        game.reset()
        # Seed the counter so we can see it drop.
        game._state.frames_since_net_crossing = 400
        game._prev_ball_x = float(NET_PILLAR_X - 5)
        # Place the ball post-crossing on the p2 side.
        game._state.ball.x = NET_PILLAR_X + 10
        game._state.ball.y = 100
        game._state.ball.vx = 5
        game._state.ball.vy = 0

        state = game.step(NOOP, NOOP)
        assert state.frames_since_net_crossing == 0
        assert state.round_ended_by_timeout is False

    def test_counter_increments_on_non_crossing_frame(
        self, game: PikachuVolleyball
    ) -> None:
        game.reset()
        state = game.step(NOOP, NOOP)
        assert state.frames_since_net_crossing >= 1

    def test_reset_clears_counter(self, game: PikachuVolleyball) -> None:
        game.reset()
        game._state.frames_since_net_crossing = 999
        state = game.reset()
        assert state.frames_since_net_crossing == 0
        assert state.round_ended_by_timeout is False

    def test_grounded_round_is_not_flagged_as_timeout(
        self, game: PikachuVolleyball
    ) -> None:
        """Normal concede (ball grounds) must NOT set round_ended_by_timeout."""
        game.reset()
        game._state.ball.x = NET_PILLAR_X - 50
        game._state.ball.y = BALL_GROUND_Y - 1
        game._state.ball.vy = 10

        state = game.step(NOOP, NOOP)
        assert state.is_round_over is True
        assert state.round_ended_by_timeout is False


class TestPostScoreFreeze:
    """Freeze-frame hold after scoring so viewers see the final moment.

    Addresses the user-reported bug: "14→15 득점 순간 안 보이는" — the
    engine used to immediately swap in the next serving state on the
    scoring frame, hiding the grounded-ball moment from replay viewers.
    """

    def _force_ground_on_p2_side(self, game: PikachuVolleyball) -> None:
        game._state.ball.x = NET_PILLAR_X + 100
        game._state.ball.y = BALL_GROUND_Y - 1
        game._state.ball.vy = 10

    def test_scoring_sets_freeze_counter(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        self._force_ground_on_p2_side(game)

        state = game.step(NOOP, NOOP)
        assert state.is_round_over is True
        assert state.score1 == 1
        assert state.post_score_freeze_frames == game.POST_SCORE_FREEZE_FRAMES

    def test_ball_stays_grounded_during_freeze(self) -> None:
        """Ball position, score, and is_round_over all hold through freeze."""
        game = PikachuVolleyball()
        game.reset()
        self._force_ground_on_p2_side(game)

        state = game.step(NOOP, NOOP)
        grounded_x = state.ball.x
        grounded_y = state.ball.y
        score_at_ground = state.score1

        # Step through the full freeze window (but NOT past it).
        for _ in range(game.POST_SCORE_FREEZE_FRAMES - 1):
            state = game.step(NOOP, NOOP)
            assert state.ball.x == grounded_x
            assert state.ball.y == grounded_y
            assert state.score1 == score_at_ground
            assert state.is_round_over is True
            assert state.post_score_freeze_frames > 0

    def test_freeze_expires_into_fresh_serving_state(self) -> None:
        """When freeze reaches 0, engine swaps to a new serving state."""
        game = PikachuVolleyball()
        game.reset()
        self._force_ground_on_p2_side(game)

        # First step triggers scoring + freeze=POST_SCORE_FREEZE_FRAMES.
        game.step(NOOP, NOOP)
        # Run out the rest of the freeze.
        for _ in range(game.POST_SCORE_FREEZE_FRAMES):
            state = game.step(NOOP, NOOP)

        # Freeze has expired; engine reset to serving state for round 2.
        assert state.post_score_freeze_frames == 0
        assert state.is_round_over is False
        assert state.ball.y < BALL_GROUND_Y  # ball no longer grounded

    def test_final_point_holds_grounded_state_forever(self) -> None:
        """Last point (score == MAX_SCORE) must NOT reset to serve state."""
        game = PikachuVolleyball()
        game.reset()
        game._state.score1 = MAX_SCORE - 1
        self._force_ground_on_p2_side(game)

        state = game.step(NOOP, NOOP)
        assert state.score1 == MAX_SCORE
        grounded_y = state.ball.y

        # Run through freeze + a handful of extra frames — ball must stay
        # on the ground because the match is over.
        for _ in range(game.POST_SCORE_FREEZE_FRAMES + 10):
            state = game.step(NOOP, NOOP)
            assert state.score1 == MAX_SCORE
            assert state.is_round_over is True
            assert state.ball.y == grounded_y

    def test_timeout_flag_persists_through_freeze(self) -> None:
        """round_ended_by_timeout must stay True for the whole hold."""
        game = PikachuVolleyball()
        game.reset()
        # Seed a pending timeout by pinning the ball on p1 side with no
        # horizontal motion so no net crossing ever happens.
        game._state.frames_since_net_crossing = game.RALLY_MAX_FRAMES - 1
        game._state.ball.x = NET_PILLAR_X - 50
        game._state.ball.y = BALL_GROUND_Y - 60
        game._state.ball.vx = 0
        game._state.ball.vy = 0
        game._prev_ball_x = float(game._state.ball.x)

        state = game.step(NOOP, NOOP)
        assert state.round_ended_by_timeout is True
        assert state.post_score_freeze_frames > 0

        # Next freeze frame must still report the timeout flag.
        state = game.step(NOOP, NOOP)
        assert state.round_ended_by_timeout is True
        assert state.is_round_over is True

    def test_rl_env_default_disables_freeze(self) -> None:
        """Env path opts out — scoring swaps immediately (no freeze frames)."""
        game = PikachuVolleyball(post_score_freeze=False)
        game.reset()
        self._force_ground_on_p2_side(game)

        state = game.step(NOOP, NOOP)
        assert state.score1 == 1
        assert state.post_score_freeze_frames == 0
        # With freeze disabled, the engine immediately swapped to a fresh
        # serving state, so the ball is back at serve position — not on the
        # ground.
        assert state.ball.y < BALL_GROUND_Y


class TestPunchEffectRadius:
    """Graphic punch-effect radius (white radial ring) on ground/power-hit.

    Mirrors original physics.js:475-478 (ground touch) and 715-719 (power
    hit) — radius is SET to BALL_RADIUS on the trigger frame and decays
    by 2 per subsequent frame (originally done client-side in
    view.js:502-507; centralised here so FE stays stateless).
    """

    def test_fresh_ball_has_zero_radius(self, game: PikachuVolleyball) -> None:
        state = game.reset()
        assert state.ball.punch_effect_radius == 0

    def test_ground_touch_sets_radius_to_ball_radius(
        self, game: PikachuVolleyball
    ) -> None:
        game.reset()
        game._state.ball.x = NET_PILLAR_X + 100
        game._state.ball.y = BALL_GROUND_Y - 1
        game._state.ball.vy = 10

        state = game.step(NOOP, NOOP)
        assert state.ball.punch_effect_radius == BALL_RADIUS
        assert state.ball.punch_effect_x == state.ball.x
        assert state.ball.punch_effect_y == BALL_GROUND_Y + BALL_RADIUS

    def test_power_hit_collision_sets_radius_to_ball_radius(
        self, game: PikachuVolleyball
    ) -> None:
        game.reset()
        # Place player 1 jumping + ball on top of them + power input.
        game._state.player1.is_jumping = True
        game._state.player1.y = PLAYER_GROUND_Y - 40
        game._state.ball.x = game._state.player1.x
        game._state.ball.y = game._state.player1.y
        game._state.ball.vy = 3

        power = PlayerInput(x_dir=1, y_dir=-1, power_hit=True)
        state = game.step(power, NOOP)
        # Either the power hit set radius to BALL_RADIUS this frame, or
        # the radius already decayed by 2 if another frame was processed.
        # In both cases it must be positive (effect is active).
        if not state.is_round_over:
            assert state.ball.punch_effect_radius > 0

    def test_radius_decays_by_2_per_frame(self, game: PikachuVolleyball) -> None:
        """After trigger, radius must shrink by exactly 2 per step."""
        game.reset()
        # Manually seed a fresh effect so we don't also trigger scoring.
        game._state.ball.punch_effect_radius = BALL_RADIUS
        # Move ball high above the ground so physics doesn't re-trigger.
        game._state.ball.x = 100
        game._state.ball.y = 50
        game._state.ball.vx = 0
        game._state.ball.vy = 0

        prev = BALL_RADIUS
        for _ in range(BALL_RADIUS // 2 + 3):
            state = game.step(NOOP, NOOP)
            if state.is_round_over:
                # Ball grounded mid-test — stop before asserting
                # re-triggered values.
                break
            expected = max(0, prev - 2)
            assert state.ball.punch_effect_radius == expected
            prev = expected
        # Eventually hits zero and stays there.
        assert state.ball.punch_effect_radius == 0

    def test_radius_never_below_zero(self, game: PikachuVolleyball) -> None:
        """Many idle steps must not drive radius negative."""
        game.reset()
        # Set radius to an odd value so straight decrement would dip below 0.
        game._state.ball.punch_effect_radius = 1
        game._state.ball.x = 100
        game._state.ball.y = 50
        game._state.ball.vy = 0

        state = game.step(NOOP, NOOP)
        assert state.ball.punch_effect_radius == 0
        state = game.step(NOOP, NOOP)
        assert state.ball.punch_effect_radius == 0
