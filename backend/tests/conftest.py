"""Shared test fixtures for RL training tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def rl_env():
    from backend.rl.env import PikachuVolleyballEnv

    env = PikachuVolleyballEnv(bot_level=1, max_steps=3000)
    yield env
    env.close()
