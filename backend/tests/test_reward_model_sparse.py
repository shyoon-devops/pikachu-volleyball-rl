"""Verify sparse_v1 strips all farming shaping signals.

ADR 0015 §2 option A: ``sparse_v1`` = terminal win/lose + per-point
only. The three farming paths flagged in §1 — #6 (approach), #7
(offensive pressure), #8 (ready position) — must contribute exactly
zero on every frame. The touch (+3/+1/-2) and net-crossing (+2)
shaping also drops; the stall penalty (-0.05/frame) drops too.

Strategy: instrument the env with a counting wrapper around each
shaping helper and assert the helpers' contributions never appear in
the reward stream. The mutation-carrying helpers
(``_score_reward`` / ``_net_crossing_reward`` / ``_stall_penalty``)
are still called for their side-effects — the step() rally-timeout
truncation reads ``_frames_since_crossing`` — but their shaping
deltas must be discarded.
"""

from __future__ import annotations

import pytest

from backend.rl.env import PikachuVolleyballEnv
from backend.game.constants import BALL_GROUND_Y, MAX_SCORE, NET_PILLAR_X


def _run_and_sum(env: PikachuVolleyballEnv, n_steps: int) -> float:
    """Step the env n_steps times under NOOP and return cumulative reward."""
    env.reset(seed=123)
    total = 0.0
    for _ in range(n_steps):
        _, r, term, trunc, _ = env.step(0)
        total += r
        if term or trunc:
            env.reset(seed=123)
    return total


class TestFarmingPathsDropped:
    """The three per-frame shaping helpers (#6/#7/#8) must NOT be
    called under sparse_v1. Patch each to raise; any invocation
    surfaces as a test failure."""

    def test_approach_reward_never_called(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = PikachuVolleyballEnv(bot_level=1, reward_model="sparse_v1")

        def _boom(*_args, **_kwargs) -> float:
            raise AssertionError(
                "_approach_reward was called under sparse_v1"
            )

        monkeypatch.setattr(env, "_approach_reward", _boom)
        _run_and_sum(env, n_steps=200)

    def test_offensive_pressure_never_called(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = PikachuVolleyballEnv(bot_level=1, reward_model="sparse_v1")

        def _boom(*_args, **_kwargs) -> float:
            raise AssertionError(
                "_offensive_pressure_reward was called under sparse_v1"
            )

        monkeypatch.setattr(env, "_offensive_pressure_reward", _boom)
        _run_and_sum(env, n_steps=200)

    def test_ready_position_never_called(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = PikachuVolleyballEnv(bot_level=1, reward_model="sparse_v1")

        def _boom(*_args, **_kwargs) -> float:
            raise AssertionError(
                "_ready_position_reward was called under sparse_v1"
            )

        monkeypatch.setattr(env, "_ready_position_reward", _boom)
        _run_and_sum(env, n_steps=200)

    def test_touch_reward_never_called(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Touch shaping (+3/+1/-2) is also dropped from sparse_v1.
        env = PikachuVolleyballEnv(bot_level=1, reward_model="sparse_v1")

        def _boom(*_args, **_kwargs) -> float:
            raise AssertionError(
                "_touch_reward was called under sparse_v1"
            )

        monkeypatch.setattr(env, "_touch_reward", _boom)
        _run_and_sum(env, n_steps=200)


class TestTerminalSignalsKept:
    """Terminal signals — game win/lose and per-point score/concede —
    MUST still land as reward. Drive the env into a scoring frame
    via direct state poke, assert the reward lines up with the
    declared constants."""

    def _force_ground_on_p2_side(self, env: PikachuVolleyballEnv) -> None:
        env._game._state.ball.x = NET_PILLAR_X + 100
        env._game._state.ball.y = BALL_GROUND_Y - 1
        env._game._state.ball.vy = 10

    def test_per_point_score_delta_matches_constant(self) -> None:
        env = PikachuVolleyballEnv(bot_level=1, reward_model="sparse_v1")
        env.reset(seed=7)
        self._force_ground_on_p2_side(env)

        _, r, _term, _trunc, _ = env.step(0)
        # A ground on p2 side is a +1 score for p1 → +_SCORE_REWARD
        # (no game end, so only the score term fires).
        assert r == pytest.approx(env._SCORE_REWARD)

    def test_game_win_reward_on_match_point(self) -> None:
        env = PikachuVolleyballEnv(bot_level=1, reward_model="sparse_v1")
        env.reset(seed=9)
        # Pre-score to the winning point so this ground touch ends
        # the match.
        env._game._state.score1 = MAX_SCORE - 1
        env._prev_score1 = MAX_SCORE - 1
        self._force_ground_on_p2_side(env)

        _, r, term, _trunc, _ = env.step(0)
        assert term is True
        assert r == pytest.approx(env._SCORE_REWARD + env._GAME_WIN_REWARD)


class TestRallyTimeoutTickStillRuns:
    """``_frames_since_crossing`` must keep ticking under sparse_v1
    so step()'s rally-timeout truncation still fires. We assert the
    counter advances across a handful of NOOP steps — if the sparse
    path had skipped ``_stall_penalty`` entirely, it would stay at 0."""

    def test_counter_advances_under_sparse_noop(self) -> None:
        env = PikachuVolleyballEnv(bot_level=1, reward_model="sparse_v1")
        env.reset(seed=0)
        assert env._frames_since_crossing == 0
        for _ in range(30):
            env.step(0)
            if env._frames_since_crossing == 0:
                # Got reset by a score/crossing — not a stall test frame.
                continue
        # At least one tick must have occurred without a reset.
        assert env._frames_since_crossing > 0


class TestSparseRewardIsBounded:
    """NOOP for a few hundred steps with no scoring should net
    exactly zero reward under sparse_v1 — no drift from an
    accidentally-restored shaping helper."""

    def test_noop_without_scoring_yields_zero_reward(self) -> None:
        # Pin the ball mid-court so the env keeps stepping without a
        # score or a crossing for the window we're measuring.
        env = PikachuVolleyballEnv(bot_level=1, reward_model="sparse_v1")
        env.reset(seed=1)
        # Force the ball into a stable mid-air position each step so
        # no scoring or net crossing can fire. This is the pure
        # "shaping helpers were skipped" check.
        total = 0.0
        for _ in range(100):
            env._game._state.ball.x = NET_PILLAR_X - 40
            env._game._state.ball.y = 80
            env._game._state.ball.vx = 0
            env._game._state.ball.vy = 0
            _, r, term, trunc, _ = env.step(0)
            total += r
            if term or trunc:
                break
        # No score, no crossing, no terminal → every shaping path is
        # gated to 0. The only non-zero possibilities under sparse_v1
        # are scoring and game_outcome, neither of which triggered.
        assert total == 0.0
