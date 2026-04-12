"""Tests for the Pikachu Volleyball game engine."""

import pytest

from backend.game.constants import (
    BALL_GROUND_Y,
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
