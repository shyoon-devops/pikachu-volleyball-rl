"""Shared fixtures for Pikachu Volleyball tests."""

from __future__ import annotations

import pytest

from backend.game.bot import RuleBasedBot
from backend.game.engine import GameState, PikachuVolleyball
from backend.rl.env import PikachuVolleyballEnv


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--base-url",
        default="http://localhost:8001",
        help="Base URL for regression tests (default: dev)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "load: marks tests that exert heavy concurrency/load "
        "(deselect with -m 'not load')",
    )


@pytest.fixture
def game_engine() -> PikachuVolleyball:
    """Return an initialized game engine."""
    return PikachuVolleyball()


@pytest.fixture
def game_state(game_engine: PikachuVolleyball) -> GameState:
    """Return a reset initial game state."""
    return game_engine.reset()


@pytest.fixture
def bot_l1() -> RuleBasedBot:
    """Return a Level 1 bot."""
    return RuleBasedBot(level=1)


@pytest.fixture
def bot_l3() -> RuleBasedBot:
    """Return a Level 3 bot."""
    return RuleBasedBot(level=3)


@pytest.fixture
def bot_l5() -> RuleBasedBot:
    """Return a Level 5 bot."""
    return RuleBasedBot(level=5)


@pytest.fixture
def rl_env() -> PikachuVolleyballEnv:
    """Return a Gymnasium environment with L1 bot opponent."""
    env = PikachuVolleyballEnv(bot_level=1, max_steps=3000)
    yield env  # type: ignore[misc]
    env.close()
