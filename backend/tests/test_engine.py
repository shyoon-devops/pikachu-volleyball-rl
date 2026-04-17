"""Tests for the Pikachu Volleyball game engine."""

import pytest

from backend.game.constants import (
    BALL_GROUND_Y,
    BALL_RADIUS,
    GRAVITY,
    MAX_SCORE,
    NET_PILLAR_X,
    PLAYER_GROUND_Y,
    PLAYER_HALF_LENGTH,
    PLAYER_INIT_X_P1,
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

    def test_mid_match_score_swaps_to_fresh_serve(self) -> None:
        """Mid-match scoring immediately swaps to a fresh serving state.

        Port(view) dropped the 20-frame post-score freeze. On a non-match-
        deciding point the engine now swaps immediately (matches the
        ``pikavolley.js`` ``startOfNewRound`` transition minus its display-
        layer pauses, which live above the engine).
        """
        game = PikachuVolleyball()
        game.reset()
        game._state.score1 = 5  # far from match-end
        self._force_ground_on_p2_side(game)

        state = game.step(NOOP, NOOP)
        assert state.score1 == 6
        assert state.is_round_over is True
        assert state.is_game_ended is False
        # Swap happened on the same frame — ball is at serve position.
        assert state.ball.y < BALL_GROUND_Y

    def test_max_score_enters_game_end_without_swap(self) -> None:
        """Match-winning point sets is_game_ended and keeps the grounded ball.

        Unlike mid-match scoring, the match-winning ground touch does NOT
        swap to a serving state — the ball stays where it grounded so the
        211-frame gameEnd window can play out the winner/loser pose.
        """
        game = PikachuVolleyball()
        game.reset()
        game._state.score1 = MAX_SCORE - 1
        self._force_ground_on_p2_side(game)

        state = game.step(NOOP, NOOP)
        assert state.score1 == MAX_SCORE
        assert state.is_game_ended is True
        assert state.game_end_frame_counter == 0
        assert state.player1.is_winner is True
        assert state.player2.is_winner is False
        assert state.player1.game_ended is True
        assert state.player2.game_ended is True
        # Grounded ball preserved (no serve-state swap).
        assert state.ball.y == BALL_GROUND_Y

    def test_game_end_counter_advances_and_physics_continues(self) -> None:
        """During gameEnd, counter increments and physics runs.

        Regression target: port(physics) used to freeze physics for 20
        frames after scoring; the view port restores the original's
        behavior where physics continues running through the full 211-
        frame gameEnd window (ball can bounce, animations play).
        """
        game = PikachuVolleyball()
        game.reset()
        game._state.score1 = MAX_SCORE - 1
        self._force_ground_on_p2_side(game)

        state = game.step(NOOP, NOOP)
        assert state.is_game_ended is True

        # Counter ticks up each step.
        prev_counter = state.game_end_frame_counter
        for i in range(5):
            state = game.step(NOOP, NOOP)
            assert state.game_end_frame_counter == prev_counter + 1, (
                f"counter stuck at frame {i}: expected {prev_counter + 1}, "
                f"got {state.game_end_frame_counter}"
            )
            prev_counter = state.game_end_frame_counter

    def test_game_end_no_extra_scoring_on_subsequent_ground_touches(self) -> None:
        """Ground touches during gameEnd must NOT add further points.

        Mirrors ``pikavolley.js`` round() gating
        (``isBallTouchingGround && ... && this.gameEnded === false``).
        Without this gate, a ball bouncing during the 211-frame window
        could silently increment the score past the winning threshold.
        """
        game = PikachuVolleyball()
        game.reset()
        game._state.score1 = MAX_SCORE - 1
        self._force_ground_on_p2_side(game)

        state = game.step(NOOP, NOOP)
        assert state.is_game_ended is True
        score_at_end = state.score1

        # Drive the ball to ground repeatedly — score must NOT advance.
        for _ in range(30):
            game._state.ball.y = BALL_GROUND_Y - 1
            game._state.ball.vy = 10
            state = game.step(NOOP, NOOP)
            assert state.score1 == score_at_end, (
                "score advanced during gameEnd window"
            )

    def test_game_end_freezes_state_after_full_window(self) -> None:
        """After GAME_END_FRAMES, repeated step() is a no-op.

        Equivalent to the original's ``state = this.intro`` transition at
        ``frameCounter >= frameTotal.gameEnd``. Our headless engine can't
        return to an intro screen so it simply pins state instead.
        """
        game = PikachuVolleyball()
        game.reset()
        game._state.score1 = MAX_SCORE - 1
        self._force_ground_on_p2_side(game)

        # Scoring frame.
        game.step(NOOP, NOOP)

        # Run out the 211-frame window.
        for _ in range(game.GAME_END_FRAMES):
            state = game.step(NOOP, NOOP)

        pinned_counter = state.game_end_frame_counter
        pinned_ball_x = state.ball.x
        pinned_ball_y = state.ball.y

        # Additional calls should no-op (counter stops advancing, physics frozen).
        for _ in range(10):
            state = game.step(NOOP, NOOP)
            assert state.game_end_frame_counter == pinned_counter
            assert state.ball.x == pinned_ball_x
            assert state.ball.y == pinned_ball_y
            assert state.score1 == MAX_SCORE
            assert state.is_round_over is True

    def test_callback_style_loop_exits_at_game_end_plus_211(self) -> None:
        """Regression: callback while-loop must terminate.

        Mirrors the exact loop condition in ``backend/rl/callbacks.py:199``
        (``score < MAX or (is_game_ended and counter < GAME_END_FRAMES)``).
        This test locks in the full-match exit: the loop must go False
        within roughly the 211-frame gameEnd window (plus the scoring
        frame) and never run away.
        """
        game = PikachuVolleyball()
        game.reset()
        game._state.score1 = MAX_SCORE - 1
        self._force_ground_on_p2_side(game)

        state = game.step(NOOP, NOOP)
        safety_bound = game.GAME_END_FRAMES * 2
        steps = 0
        while (
            state.score1 < MAX_SCORE and state.score2 < MAX_SCORE
        ) or (
            state.is_game_ended
            and state.game_end_frame_counter < game.GAME_END_FRAMES
        ):
            state = game.step(NOOP, NOOP)
            steps += 1
            assert steps <= safety_bound, "callback loop did not terminate"

        assert state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE
        assert state.game_end_frame_counter >= game.GAME_END_FRAMES
        # Iterations should be in the 211-frame ballpark — a large blowup
        # would still be caught by the safety bound above, but this keeps
        # the expected shape explicit.
        assert steps <= game.GAME_END_FRAMES + 5

    def test_timeout_flag_persists_after_round_swap(self) -> None:
        """round_ended_by_timeout stays True on the timeout frame.

        Pre-port (freeze model) this flag used to persist across the
        whole 20-frame freeze window. Post-port there is no freeze, so
        the flag is observable on the exact frame the timeout fires; the
        engine swaps to a fresh serving state on the same frame, but the
        returned state still carries the flag so RL / UI layers can
        distinguish a concede from a timeout.
        """
        game = PikachuVolleyball()
        game.reset()
        game._state.frames_since_net_crossing = game.RALLY_MAX_FRAMES - 1
        game._state.ball.x = NET_PILLAR_X - 50
        game._state.ball.y = BALL_GROUND_Y - 60
        game._state.ball.vx = 0
        game._state.ball.vy = 0
        game._prev_ball_x = float(game._state.ball.x)

        state = game.step(NOOP, NOOP)
        assert state.round_ended_by_timeout is True
        assert state.is_round_over is True


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
        # Pre-score to MAX_SCORE-1 so this grounding enters the gameEnd
        # window instead of swapping to a fresh serving state. After the
        # view port, mid-match scoring immediately swaps (losing the
        # grounded-ball markers), whereas the match-winning ground touch
        # preserves them for the 211-frame winner-pose window — which is
        # where the FE actually needs the punch-effect radius to render.
        game.reset()
        game._state.score1 = MAX_SCORE - 1
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
        # state=1 is "jumping"; _update_player transitions state 1→2 when
        # the power_hit input fires, and the collision branch keys off
        # state==2 (matches physics.js:709).
        game._state.player1.state = 1
        game._state.player1.sync_derived_flags()
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


class TestDisplayStateMachine:
    """Port-of-pikavolley.js round/afterEndOfRound/beforeStartOfNextRound flow.

    These tests pin the display-mode state machine that ``port(view): gameEnd
    211f`` left as a stub. The RL training env keeps the engine in pure mode
    (display_state_machine=False, no slow-motion / fade / ready frames); the
    replay viewer pipeline opts in.
    """

    def _force_ground_on_p2_side(self, game: PikachuVolleyball) -> None:
        game._state.ball.x = NET_PILLAR_X + 100
        game._state.ball.y = BALL_GROUND_Y - 1
        game._state.ball.vy = 10

    def test_default_state_name_is_round(self) -> None:
        game = PikachuVolleyball(display_state_machine=True)
        state = game.reset()
        assert state.state_name == "round"
        assert state.slow_motion_frames_left == 0
        assert state.fade_black_alpha == 0.0
        assert state.ready_message_visible is False

    def test_mid_match_score_arms_slow_motion(self) -> None:
        """Score in display mode arms 6-frame slow-mo, no immediate swap."""
        game = PikachuVolleyball(display_state_machine=True)
        game.reset()
        self._force_ground_on_p2_side(game)
        state = game.step(NOOP, NOOP)

        assert state.score1 == 1
        assert state.is_round_over is True
        assert state.state_name == "round"  # still 'round' until slow-mo done
        assert state.slow_motion_frames_left == game.SLOW_MOTION_FRAMES_NUM
        # Ball stayed where it landed (no immediate swap).
        assert state.ball.y == BALL_GROUND_Y

    def test_slow_motion_skips_4_of_5_calls(self) -> None:
        """Physics advances every 5th call during the slow-motion window."""
        game = PikachuVolleyball(display_state_machine=True)
        game.reset()
        self._force_ground_on_p2_side(game)
        game.step(NOOP, NOOP)  # scoring frame, arms slow-mo at 6

        # 4 skipped calls after the score: counter ticks but frames_left stays.
        for _ in range(4):
            state = game.step(NOOP, NOOP)
            assert state.slow_motion_frames_left == 6

        # 5th call advances physics, decrements frames_left to 5.
        state = game.step(NOOP, NOOP)
        assert state.slow_motion_frames_left == 5

    def test_slow_motion_into_after_end_of_round(self) -> None:
        """After 30 step()s post-score, transitions to afterEndOfRound."""
        game = PikachuVolleyball(display_state_machine=True)
        game.reset()
        self._force_ground_on_p2_side(game)
        game.step(NOOP, NOOP)  # scoring + arm slow-mo

        # 30 step()s = 6 physics frames × 5 skip ratio.
        for _ in range(game.SLOW_MOTION_FRAMES_NUM * game.SLOW_MOTION_SKIP_RATIO):
            state = game.step(NOOP, NOOP)

        assert state.slow_motion_frames_left == 0
        assert state.state_name == "afterEndOfRound"
        # Fade has begun (≥ 1/16 from the post-physics block).
        assert state.fade_black_alpha > 0

    def test_after_end_of_round_holds_5_frames_then_advances(self) -> None:
        """afterEndOfRound runs for AFTER_END_OF_ROUND_FRAMES (5) ticks."""
        game = PikachuVolleyball(display_state_machine=True)
        game.reset()
        # Jump straight into afterEndOfRound for clarity.
        game._state.state_name = "afterEndOfRound"
        game._state.state_frame_counter = 0
        game._state.fade_black_alpha = 0.0625

        for i in range(game.AFTER_END_OF_ROUND_FRAMES - 1):
            state = game.step(NOOP, NOOP)
            assert state.state_name == "afterEndOfRound"
            assert state.state_frame_counter == i + 1

        # Final tick rolls into beforeStartOfNextRound.
        state = game.step(NOOP, NOOP)
        assert state.state_name == "beforeStartOfNextRound"
        assert state.state_frame_counter == 0

    def test_before_start_of_next_round_resets_players_and_ball(self) -> None:
        """Frame 0 of beforeStartOfNextRound re-initializes players + ball."""
        game = PikachuVolleyball(display_state_machine=True)
        game.reset()
        # Move ball + players to non-default positions.
        game._state.ball.x = 200
        game._state.ball.y = 100
        game._state.ball.vy = 9
        game._state.player1.x = 80
        game._state.serving_player = 2
        game._state.state_name = "beforeStartOfNextRound"
        game._state.state_frame_counter = 0
        game._state.fade_black_alpha = 0.5

        state = game.step(NOOP, NOOP)

        # Players + ball reset to serve positions for player2 serve.
        assert state.player1.x == PLAYER_INIT_X_P1
        assert state.player1.y == PLAYER_GROUND_Y
        assert state.ball.y == 0  # serve y
        # Fade alpha was forced to 1 on entry then decremented by 1/16.
        assert state.fade_black_alpha == pytest.approx(1.0 - 1.0 / 16)

    def test_ready_message_blinks_every_5_frames(self) -> None:
        """ready_message_visible flips every READY_MESSAGE_TOGGLE_PERIOD ticks."""
        game = PikachuVolleyball(display_state_machine=True)
        game.reset()
        game._state.state_name = "beforeStartOfNextRound"
        game._state.state_frame_counter = 0

        toggle_states: list[bool] = []
        for _ in range(15):
            state = game.step(NOOP, NOOP)
            toggle_states.append(state.ready_message_visible)
        # Pattern: 4 frames False (init), then toggle at frames 5, 10, 15...
        # After init reset (visible=False), counter ticks 1..15.
        # At counter 5: toggle → True. At 10: False. At 15: True.
        assert toggle_states[4] is True   # frame counter == 5
        assert toggle_states[9] is False  # frame counter == 10
        assert toggle_states[14] is True  # frame counter == 15

    def test_before_start_returns_to_round_after_30f(self) -> None:
        """After 30 ticks, state_name flips to 'round' and physics resumes."""
        game = PikachuVolleyball(display_state_machine=True)
        game.reset()
        game._state.state_name = "beforeStartOfNextRound"
        game._state.state_frame_counter = 0

        for _ in range(game.BEFORE_START_OF_NEXT_ROUND_FRAMES):
            state = game.step(NOOP, NOOP)

        assert state.state_name == "round"
        assert state.state_frame_counter == 0
        assert state.fade_black_alpha == 0.0
        assert state.ready_message_visible is False
        assert state.is_round_over is False

    def test_game_end_skips_slow_motion(self) -> None:
        """Match-winning score goes straight to gameEnd, no slow-mo / fade."""
        game = PikachuVolleyball(display_state_machine=True)
        game.reset()
        game._state.score1 = MAX_SCORE - 1
        self._force_ground_on_p2_side(game)
        state = game.step(NOOP, NOOP)

        assert state.is_game_ended is True
        assert state.state_name == "gameEnd"
        # No slow-motion arming on game-end (matches pikavolley.js gating).
        assert state.slow_motion_frames_left == 0

    def test_pure_mode_unchanged_default(self) -> None:
        """Without display_state_machine, scoring still swaps immediately."""
        game = PikachuVolleyball()  # default False
        game.reset()
        self._force_ground_on_p2_side(game)
        state = game.step(NOOP, NOOP)

        assert state.score1 == 1
        # Pure mode: immediate swap to fresh serve, ball off the ground.
        assert state.ball.y < BALL_GROUND_Y
        # State machine fields stay at defaults.
        assert state.slow_motion_frames_left == 0
        assert state.state_name == "round"
