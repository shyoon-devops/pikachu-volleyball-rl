"""Tests for the Rule-based Bot."""

import pytest

from backend.game.engine import PikachuVolleyball, PlayerInput
from backend.game.bot import RuleBasedBot


class TestBotValidInput:
    """Each level should return a valid PlayerInput."""

    @pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
    def test_returns_valid_player_input(self, level: int) -> None:
        game = PikachuVolleyball()
        state = game.reset()
        bot = RuleBasedBot(level=level)

        action = bot.get_action(state, is_player2=True)

        assert isinstance(action, PlayerInput)
        assert action.x_dir in (-1, 0, 1)
        assert action.y_dir in (-1, 0, 1)
        assert isinstance(action.power_hit, bool)

    @pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
    def test_returns_valid_input_as_player1(self, level: int) -> None:
        game = PikachuVolleyball()
        state = game.reset()
        bot = RuleBasedBot(level=level)

        action = bot.get_action(state, is_player2=False)

        assert isinstance(action, PlayerInput)
        assert action.x_dir in (-1, 0, 1)
        assert action.y_dir in (-1, 0, 1)


class TestL5BeatsL1:
    """L5 bot should consistently beat L1 bot over 10 games."""

    def test_l5_wins_majority_against_l1(self) -> None:
        """L5 should clearly outperform L1 over a 20-game sample.

        With the faithful 32px collision box (matching original physics.js),
        both bots miss more often than with the older 52px box, so the level
        gap narrows slightly. We still expect L5 to win a clear majority
        (>= 60% = 12/20) to confirm the skill ordering.
        """
        import random as rng

        rng.seed(42)
        l5_wins = 0
        n_games = 20

        for _ in range(n_games):
            game = PikachuVolleyball()
            state = game.reset()
            bot_l1 = RuleBasedBot(level=1)
            bot_l5 = RuleBasedBot(level=5)

            for _step in range(50000):
                p1_action = bot_l1.get_action(state, is_player2=False)
                p2_action = bot_l5.get_action(state, is_player2=True)
                state = game.step(p1_action, p2_action)
                if state.score1 >= 15 or state.score2 >= 15:
                    break

            if state.score2 > state.score1:
                l5_wins += 1

        assert l5_wins >= 12, f"L5 won only {l5_wins}/{n_games} games"
