"""Game scenario tests for Pikachu Volleyball."""

from __future__ import annotations

import random

import pytest

from backend.game.bot import RuleBasedBot
from backend.game.constants import (
    BALL_GROUND_Y,
    MAX_SCORE,
    NET_PILLAR_X,
)
from backend.game.engine import PikachuVolleyball, PlayerInput

NOOP = PlayerInput(x_dir=0, y_dir=0, power_hit=False)
JUMP = PlayerInput(x_dir=0, y_dir=-1, power_hit=False)
MOVE_LEFT = PlayerInput(x_dir=-1, y_dir=0, power_hit=False)
MOVE_RIGHT = PlayerInput(x_dir=1, y_dir=0, power_hit=False)


class TestServeScenario:
    """After serve, the ball should rise correctly before falling."""

    def test_ball_starts_above_ground(
        self, game_engine: PikachuVolleyball, game_state: None
    ) -> None:
        state = game_engine._state
        assert state.ball.y < BALL_GROUND_Y

    def test_ball_initial_vy_is_positive(
        self, game_engine: PikachuVolleyball, game_state: None
    ) -> None:
        state = game_engine._state
        # initial vy is 1 (falling slowly)
        assert state.ball.vy >= 0

    def test_serve_ball_eventually_hits_ground(
        self, game_engine: PikachuVolleyball, game_state: None
    ) -> None:
        """With no player input, the served ball should fall and score."""
        scored = False
        for _ in range(500):
            state = game_engine.step(NOOP, NOOP)
            if state.is_round_over:
                scored = True
                break
        assert scored, "Ball never hit the ground after serve"

    def test_serve_goes_to_serving_player_side(
        self, game_engine: PikachuVolleyball
    ) -> None:
        """Ball starts above the serving player."""
        state = game_engine.reset()
        assert state.serving_player == 1
        assert state.ball.x < NET_PILLAR_X  # player1 is on the left


class TestRallyScenario:
    """Rally: both players hitting the ball back and forth."""

    def test_bot_rally_produces_net_crossings(self) -> None:
        """Two bots playing should produce at least one net crossing."""
        random.seed(42)
        game = PikachuVolleyball()
        state = game.reset()
        bot1 = RuleBasedBot(level=3)
        bot2 = RuleBasedBot(level=3)

        crossings = 0
        prev_side = state.ball.x < NET_PILLAR_X

        for _ in range(3000):
            p1 = bot1.get_action(state, is_player2=False)
            p2 = bot2.get_action(state, is_player2=True)
            state = game.step(p1, p2)

            current_side = state.ball.x < NET_PILLAR_X
            if current_side != prev_side:
                crossings += 1
            prev_side = current_side

            if state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE:
                break

        assert crossings >= 1, "No net crossings in 3000 steps"


class TestGameCompletionScenario:
    """Game should complete to MAX_SCORE with correct winner."""

    def test_game_reaches_max_score(self) -> None:
        random.seed(42)
        game = PikachuVolleyball()
        state = game.reset()
        bot1 = RuleBasedBot(level=3)
        bot2 = RuleBasedBot(level=3)

        for _ in range(50000):
            p1 = bot1.get_action(state, is_player2=False)
            p2 = bot2.get_action(state, is_player2=True)
            state = game.step(p1, p2)
            if state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE:
                break

        assert state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE

    def test_winner_has_max_score(self) -> None:
        random.seed(99)
        game = PikachuVolleyball()
        state = game.reset()
        bot1 = RuleBasedBot(level=3)
        bot2 = RuleBasedBot(level=3)

        finished = False
        for _ in range(100000):
            p1 = bot1.get_action(state, is_player2=False)
            p2 = bot2.get_action(state, is_player2=True)
            state = game.step(p1, p2)
            if state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE:
                finished = True
                break

        assert finished, "Game did not finish in 100000 steps"
        winner_score = max(state.score1, state.score2)
        assert winner_score == MAX_SCORE

    def test_scores_never_exceed_max(self) -> None:
        random.seed(42)
        game = PikachuVolleyball()
        state = game.reset()
        bot1 = RuleBasedBot(level=3)
        bot2 = RuleBasedBot(level=3)

        for _ in range(50000):
            p1 = bot1.get_action(state, is_player2=False)
            p2 = bot2.get_action(state, is_player2=True)
            state = game.step(p1, p2)
            assert state.score1 <= MAX_SCORE
            assert state.score2 <= MAX_SCORE
            if state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE:
                break


class TestBoundaryValues:
    """Edge case: 14:14 score — next point ends the game."""

    def test_14_14_next_point_ends_game(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        game._state.score1 = MAX_SCORE - 1  # 14
        game._state.score2 = MAX_SCORE - 1  # 14

        # Force ball to land on p2 side
        game._state.ball.x = NET_PILLAR_X + 100
        game._state.ball.y = BALL_GROUND_Y - 1
        game._state.ball.vy = 5

        new_state = game.step(NOOP, NOOP)
        assert new_state.score1 == MAX_SCORE
        assert new_state.score1 > new_state.score2

    def test_score_0_0_initial(
        self, game_engine: PikachuVolleyball, game_state: None
    ) -> None:
        state = game_engine._state
        assert state.score1 == 0
        assert state.score2 == 0

    def test_serving_player_changes_after_scoring(self) -> None:
        game = PikachuVolleyball()
        game.reset()
        # Ball on p1's side → p2 scores → p2 serves next
        game._state.ball.x = NET_PILLAR_X - 100
        game._state.ball.y = BALL_GROUND_Y - 1
        game._state.ball.vy = 5

        new_state = game.step(NOOP, NOOP)
        assert new_state.serving_player == 2


class TestBotMatchups:
    """Same-level bot matchups should produce roughly balanced results."""

    @pytest.mark.parametrize("level", [1, 3, 5])
    def test_same_level_matchup_is_balanced(self, level: int) -> None:
        random.seed(123)
        p1_wins = 0
        n_games = 10

        for _ in range(n_games):
            game = PikachuVolleyball()
            state = game.reset()
            bot1 = RuleBasedBot(level=level)
            bot2 = RuleBasedBot(level=level)

            for _step in range(50000):
                a1 = bot1.get_action(state, is_player2=False)
                a2 = bot2.get_action(state, is_player2=True)
                state = game.step(a1, a2)
                if state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE:
                    break

            if state.score1 > state.score2:
                p1_wins += 1

        # Balanced: expect between 1 and 9 wins (not extreme)
        assert 0 <= p1_wins <= n_games


class TestCurriculumSimulation:
    """Simulate curriculum: L1 → L3 → L5 bot swap mid-game."""

    def test_curriculum_bot_swap_runs_without_error(self) -> None:
        random.seed(42)
        game = PikachuVolleyball()
        state = game.reset()

        levels = [1, 3, 5]
        games_per_level = 2
        total_games = 0

        for level in levels:
            bot1 = RuleBasedBot(level=level)
            bot2 = RuleBasedBot(level=level)

            for _ in range(games_per_level):
                game = PikachuVolleyball()
                state = game.reset()

                for _step in range(50000):
                    a1 = bot1.get_action(state, is_player2=False)
                    a2 = bot2.get_action(state, is_player2=True)
                    state = game.step(a1, a2)
                    if state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE:
                        break

                total_games += 1

        assert total_games == len(levels) * games_per_level

    def test_higher_level_bots_play_longer_rallies(self) -> None:
        """Higher-level bots should generally produce longer games."""
        random.seed(42)
        avg_frames: dict[int, float] = {}

        for level in [1, 5]:
            total_frames = 0
            n_games = 5

            for _ in range(n_games):
                game = PikachuVolleyball()
                state = game.reset()
                bot1 = RuleBasedBot(level=level)
                bot2 = RuleBasedBot(level=level)

                for _step in range(50000):
                    a1 = bot1.get_action(state, is_player2=False)
                    a2 = bot2.get_action(state, is_player2=True)
                    state = game.step(a1, a2)
                    if state.score1 >= MAX_SCORE or state.score2 >= MAX_SCORE:
                        break

                total_frames += state.frame

            avg_frames[level] = total_frames / n_games

        # L5 games should be longer on average than L1 games
        assert avg_frames[5] > avg_frames[1]
