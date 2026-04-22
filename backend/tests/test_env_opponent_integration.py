"""Env-side tests for the OpponentProvider integration.

Covers: legacy bot_level path untouched, explicit provider injection,
provider re-sampled on reset(), on_match_end forwarded at terminated
matches.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.game.bot import RuleBasedBot
from backend.game.engine import PlayerInput
from backend.rl.env import PikachuVolleyballEnv
from backend.rl.opponent import (
    FixedBotProvider,
    Opponent,
    OpponentProvider,
)


class _RecordingProvider(OpponentProvider):
    """Tracks get_opponent / on_match_end calls for assertions."""

    def __init__(self, opponent: Opponent) -> None:
        self._opponent = opponent
        self.get_calls: list[int] = []
        self.match_end_calls: list[dict[str, Any]] = []

    def get_opponent(self, env_index: int = 0) -> Opponent:
        self.get_calls.append(int(env_index))
        return self._opponent

    def on_match_end(
        self,
        env_index: int,
        opponent: Opponent,
        winner: int,
        score1: int,
        score2: int,
    ) -> None:
        self.match_end_calls.append(
            dict(
                env_index=env_index,
                opponent_id=getattr(opponent, "id", None),
                winner=winner,
                score1=score1,
                score2=score2,
            )
        )


class _StaticOpponent:
    id = "ck_static"

    def get_action(self, state: Any, *, is_player2: bool) -> PlayerInput:
        return PlayerInput(x_dir=0, y_dir=0, power_hit=False)


class TestLegacyBotLevelPath:
    """No provider passed → FixedBotProvider built from bot_level."""

    def test_default_provider_is_fixed_bot(self) -> None:
        env = PikachuVolleyballEnv(bot_level=3)
        # Exposed as _opponent_provider for tests and trainer hand-off.
        assert isinstance(env._opponent_provider, FixedBotProvider)
        assert env._opponent_provider.level == 3

    def test_bot_is_rulebased_after_reset(self) -> None:
        env = PikachuVolleyballEnv(bot_level=2)
        env.reset()
        assert isinstance(env._bot, RuleBasedBot)
        assert env._bot.level == 2


class TestExplicitProviderInjection:
    def test_explicit_provider_overrides_bot_level(self) -> None:
        provider = _RecordingProvider(opponent=_StaticOpponent())
        env = PikachuVolleyballEnv(
            bot_level=1, opponent_provider=provider
        )
        # Construction should consult the provider once (env_index=0).
        assert provider.get_calls == [0]
        assert env._bot is provider._opponent

    def test_env_index_forwarded_to_provider(self) -> None:
        provider = _RecordingProvider(opponent=_StaticOpponent())
        env = PikachuVolleyballEnv(
            bot_level=1, opponent_provider=provider, env_index=5
        )
        assert provider.get_calls == [5]
        env.reset()
        # reset re-samples opponent using the same env_index.
        assert provider.get_calls == [5, 5]


class TestResetResamplesOpponent:
    def test_reset_calls_get_opponent(self) -> None:
        provider = _RecordingProvider(opponent=_StaticOpponent())
        env = PikachuVolleyballEnv(
            bot_level=1, opponent_provider=provider
        )
        # Initial __init__ counted once.
        assert len(provider.get_calls) == 1
        env.reset()
        assert len(provider.get_calls) == 2
        env.reset()
        assert len(provider.get_calls) == 3


class TestOnMatchEndForwarded:
    def test_on_match_end_fires_when_score_reaches_max(self) -> None:
        # Drive the env to a terminated state by forcing the engine's
        # score through the boundary — avoids needing a full game
        # rollout inside the test.
        provider = _RecordingProvider(opponent=_StaticOpponent())
        env = PikachuVolleyballEnv(
            bot_level=1, opponent_provider=provider
        )
        env.reset()
        # Manipulate the engine state so the next step() terminates.
        env._game._state.score1 = 14  # 1 point from win
        env._game._state.ball.x = env._game._state.player2.x + 200
        env._game._state.ball.x = min(
            env._game._state.ball.x, 431
        )
        env._game._state.ball.y = 250  # just above ground
        env._game._state.ball.vy = 10  # will ground on next step
        obs, reward, terminated, truncated, info = env.step(0)
        # Winning ground touch → score1 reaches 15 → terminated.
        assert terminated
        assert len(provider.match_end_calls) == 1
        call = provider.match_end_calls[0]
        assert call["winner"] == 1
        assert call["score1"] == 15
        assert call["opponent_id"] == "ck_static"

    def test_on_match_end_not_fired_on_truncation(self) -> None:
        # Truncation (stall / max_steps) must NOT trigger a league
        # rating update — those games didn't finish naturally.
        provider = _RecordingProvider(opponent=_StaticOpponent())
        env = PikachuVolleyballEnv(
            bot_level=1, opponent_provider=provider, max_steps=3
        )
        env.reset()
        for _ in range(5):
            obs, reward, terminated, truncated, info = env.step(0)
            if terminated or truncated:
                break
        # Static opponent + 3-step budget → truncation is practically
        # guaranteed. Assert the premise (no natural termination) first
        # so a future change that accidentally scores inside 3 steps
        # fails loudly, then assert the invariant (no match-end call).
        assert truncated and not terminated, (
            "test precondition broken — episode terminated naturally "
            "within 3 steps; pick a different scenario"
        )
        assert provider.match_end_calls == []


class TestObservationShapeUnchanged:
    """Smoke test — the provider plumbing must not disturb the obs
    shape contract the parity test and the agent policy rely on."""

    def test_reset_obs_is_18_float32(self) -> None:
        env = PikachuVolleyballEnv(bot_level=1)
        obs, _ = env.reset()
        assert obs.shape == (18,)
        assert obs.dtype == np.float32

    def test_step_obs_is_18_float32(self) -> None:
        env = PikachuVolleyballEnv(bot_level=1)
        env.reset()
        obs, _reward, _term, _trunc, _info = env.step(0)
        assert obs.shape == (18,)
        assert obs.dtype == np.float32
