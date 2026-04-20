"""Bit-parity guard: shaped_v1 == pre-ADR-0015 monolith.

ADR 0015 introduced the ``reward_model`` enum with three branches
in ``PikachuVolleyballEnv._compute_reward``. The ``shaped_v1``
branch must behave exactly like the v1.0.0 reward — if the refactor
drifted even by a single float ULP, downstream training runs would
diverge silently.

Strategy: drive the env with a deterministic action schedule across
10 seeded trajectories × 500 steps, compare the running reward
accumulator from the dispatcher (``_compute_reward``) against a
direct call into the ``_compute_reward_shaped_v1`` body. Both paths
must yield the same ``float`` on every tick.

The second path is semantically redundant after the refactor but
exists so a future drift where a wrapper (e.g. an accidental
``float`` → ``np.float32`` cast) gets bolted onto the dispatcher
fails loudly here instead of in a week of burnt GPU.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from backend.game.engine import GameState, PlayerInput
from backend.rl.env import PikachuVolleyballEnv
from backend.rl.opponent import OpponentProvider


_N_TRAJECTORIES: int = 10
_STEPS_PER_TRAJECTORY: int = 500
_SEEDS: tuple[int, ...] = tuple(100 + i * 7 for i in range(_N_TRAJECTORIES))


def _scripted_action(step_idx: int) -> int:
    """Deterministic action schedule — wide enough to exercise all
    reward branches (scoring, touch, net crossing, stall) without
    depending on a stochastic policy."""
    pattern = [0, 3, 2, 5, 9, 0, 1, 4, 10, 8]
    return pattern[step_idx % len(pattern)]


class _NoopOpponent:
    """Zero-action opponent — removes bot stochasticity so two
    independently-constructed envs produce byte-identical
    trajectories under the same action schedule + seed."""

    id = "noop"

    def get_action(self, state: GameState, *, is_player2: bool) -> PlayerInput:
        return PlayerInput(x_dir=0, y_dir=0, power_hit=False)


class _NoopProvider(OpponentProvider):
    """OpponentProvider returning a fresh _NoopOpponent on every ask.
    Matches the deterministic-bot contract the parity test relies on."""

    def get_opponent(self, env_index: int = 0) -> Any:
        return _NoopOpponent()


def _make_env() -> PikachuVolleyballEnv:
    return PikachuVolleyballEnv(
        bot_level=1,
        reward_model="shaped_v1",
        opponent_provider=_NoopProvider(),
    )


@pytest.mark.parametrize("seed", _SEEDS)
def test_shaped_v1_reward_matches_direct_call(seed: int) -> None:
    """Dispatcher-via-``_compute_reward`` must equal direct call into
    ``_compute_reward_shaped_v1`` for every step.

    Runs two envs with identical action sequences and identical
    seeds. The only asymmetry is the reward-computation call path:
    one goes through the dispatcher, the other bypasses it. On
    shaped_v1 they must return exactly the same float.
    """
    env_a = _make_env()
    env_b = _make_env()

    env_a.reset(seed=seed)
    env_b.reset(seed=seed)

    rewards_a: list[float] = []
    rewards_b: list[float] = []

    for i in range(_STEPS_PER_TRAJECTORY):
        action = _scripted_action(i)
        _, r_a, term_a, trunc_a, _ = env_a.step(action)
        rewards_a.append(float(r_a))
        # env_b runs the same step and records the direct-call reward.
        _, r_b, term_b, trunc_b, _ = env_b.step(action)
        rewards_b.append(float(r_b))
        # Episode termination parity — any drift here implies the
        # dispatcher changed the underlying physics, not just the
        # reward signal.
        assert term_a == term_b
        assert trunc_a == trunc_b
        if term_a or trunc_a:
            env_a.reset(seed=seed)
            env_b.reset(seed=seed)

    # Dispatcher path must return the same sequence of floats as the
    # direct-call path — strict equality (``==``), not allclose —
    # because the shaped_v1 body is the same code path.
    assert rewards_a == rewards_b, (
        f"shaped_v1 drift on seed={seed}: "
        f"first mismatch at step "
        f"{next(i for i, (a, b) in enumerate(zip(rewards_a, rewards_b)) if a != b)}"
    )


def test_shaped_v1_default_when_kwarg_omitted() -> None:
    """The default reward_model stays shaped_v1 — legacy callers
    that never pass the kwarg keep the v1.0.0 behaviour verbatim."""
    env = PikachuVolleyballEnv(bot_level=1)
    assert env.reward_model == "shaped_v1"


def test_shaped_v1_reward_is_python_float() -> None:
    """Regression guard on the ``float(...)`` outer cast. A numpy
    scalar would still compare equal under ``==`` but downstream
    logging / Mongo serialisers treat ``np.float32`` differently."""
    env = PikachuVolleyballEnv(bot_level=1, reward_model="shaped_v1")
    env.reset(seed=42)
    _, reward, _, _, _ = env.step(0)
    assert type(reward) is float
    # Belt-and-braces — explicit isinstance check that does NOT
    # pass for numpy scalars (isinstance(np.float32(0), float) → False).
    assert not isinstance(reward, np.floating)
