"""Boundary-contract enforcement for ``reward_model`` enum.

ADR 0015 fixes the enum at ``shaped_v1 | sparse_v1 |
learned_shaped_v1``. The BE validator and FE selector both clamp to
this set; the env constructor is the third guardrail so a client
that bypasses the API (tests, notebooks, direct instantiation) still
crashes immediately on an unknown value rather than silently
degrading to a default.

These tests also pin the learned_shaped_v1 scaffold's behaviour:
with the default zero-weights ``BuiltinLinearPotential`` the shaping
delta is identically zero, so ``learned_shaped_v1`` must return the
same reward stream as ``sparse_v1`` on an otherwise-identical
trajectory.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.game.engine import GameState, PlayerInput
from backend.rl.env import PikachuVolleyballEnv, VALID_REWARD_MODELS
from backend.rl.opponent import OpponentProvider
from backend.rl.reward_potential import BuiltinLinearPotential


class _NoopOpponent:
    """Zero-action opponent for deterministic cross-env comparisons."""

    id = "noop"

    def get_action(self, state: GameState, *, is_player2: bool) -> PlayerInput:
        return PlayerInput(x_dir=0, y_dir=0, power_hit=False)


class _NoopProvider(OpponentProvider):
    def get_opponent(self, env_index: int = 0) -> Any:
        return _NoopOpponent()


def _make_env(reward_model: str, **kwargs: Any) -> PikachuVolleyballEnv:
    return PikachuVolleyballEnv(
        bot_level=1,
        reward_model=reward_model,
        opponent_provider=_NoopProvider(),
        **kwargs,
    )


class TestEnumRejection:
    """Unknown values must raise ValueError at construction time."""

    @pytest.mark.parametrize("bad_value", [
        "",
        "shaped",
        "v1",
        "SPARSE_V1",          # case-sensitive
        "shaped_v2",          # plausible-but-not-shipped
        "learned_shaped_v2",  # plausible-but-not-shipped
        "none",
        "sparse_v1 ",         # trailing whitespace
    ])
    def test_unknown_value_rejected(self, bad_value: str) -> None:
        with pytest.raises(ValueError, match="reward_model"):
            PikachuVolleyballEnv(bot_level=1, reward_model=bad_value)

    def test_non_string_rejected(self) -> None:
        # The enum is a string contract — numeric types must not
        # silently coerce through the ``not in`` check.
        with pytest.raises(ValueError, match="reward_model"):
            PikachuVolleyballEnv(bot_level=1, reward_model=0)  # type: ignore[arg-type]

    def test_none_rejected(self) -> None:
        with pytest.raises(ValueError, match="reward_model"):
            PikachuVolleyballEnv(bot_level=1, reward_model=None)  # type: ignore[arg-type]


class TestValidEnumConstructs:
    """All three enum values must construct successfully and surface
    the value on the instance."""

    @pytest.mark.parametrize("model", list(VALID_REWARD_MODELS))
    def test_valid_value_accepted(self, model: str) -> None:
        env = PikachuVolleyballEnv(bot_level=1, reward_model=model)
        assert env.reward_model == model

    def test_enum_contains_expected_three(self) -> None:
        # Locks the boundary contract — if a new reward model lands
        # without simultaneously updating BE / FE validators, this
        # test anchors the moment of divergence.
        assert set(VALID_REWARD_MODELS) == {
            "shaped_v1", "sparse_v1", "learned_shaped_v1",
        }


class TestLearnedShapedV1PlaceholderBehaviour:
    """With the default zero-weights potential, learned_shaped_v1
    collapses to sparse_v1 on every transition. This test pins that
    invariant — when an IRL-trained Φ ships, this test should be
    updated or replaced; until then it's a regression guard on the
    scaffold itself."""

    def test_zero_potential_yields_zero_shaping(self) -> None:
        phi = BuiltinLinearPotential.zeros()
        # Any 18-float obs must produce Φ = 0.
        import numpy as np  # local — avoid top-level for test-only dep
        obs = np.linspace(-1.0, 1.0, 18, dtype=np.float32)
        assert phi.phi(obs) == 0.0

    def test_learned_matches_sparse_under_placeholder(self) -> None:
        env_s = _make_env("sparse_v1")
        env_l = _make_env("learned_shaped_v1")
        env_s.reset(seed=31)
        env_l.reset(seed=31)

        for step in range(200):
            action = [0, 3, 2, 8][step % 4]
            _, r_s, t_s, tr_s, _ = env_s.step(action)
            _, r_l, t_l, tr_l, _ = env_l.step(action)
            assert r_s == r_l, (
                f"learned_shaped_v1 drifted from sparse_v1 "
                f"under zero Φ at step {step}: "
                f"sparse={r_s!r} learned={r_l!r}"
            )
            assert t_s == t_l and tr_s == tr_l
            if t_s or tr_s:
                env_s.reset(seed=31)
                env_l.reset(seed=31)


class TestLearnedShapedV1WithCustomPotential:
    """A caller-supplied trained PotentialFn must be accepted and
    consulted on every step. Verifies the injection hook without
    shipping a real IRL fitter."""

    def test_custom_potential_injected(self) -> None:
        import numpy as np  # local — test-only

        # A non-zero weight vector so the potential actually fires.
        phi = BuiltinLinearPotential(
            weights=np.ones(18, dtype=np.float32) * 0.1,
            bias=0.0,
        )
        env = PikachuVolleyballEnv(
            bot_level=1,
            reward_model="learned_shaped_v1",
            potential_fn=phi,
        )
        assert env._potential_fn is phi

    def test_potential_kwarg_ignored_for_shaped_v1(self) -> None:
        # Caller passing a potential with the shaped_v1 model is
        # accepted but unused — the dispatcher never routes to the
        # shaping path. Guard that it doesn't accidentally affect
        # the reward.
        import numpy as np  # local — test-only

        phi = BuiltinLinearPotential(
            weights=np.ones(18, dtype=np.float32) * 10.0,  # huge
            bias=100.0,
        )
        env_plain = _make_env("shaped_v1")
        env_loaded = _make_env("shaped_v1", potential_fn=phi)
        env_plain.reset(seed=5)
        env_loaded.reset(seed=5)

        for i in range(100):
            _, r1, t1, tr1, _ = env_plain.step(i % 4)
            _, r2, t2, tr2, _ = env_loaded.step(i % 4)
            assert r1 == r2
            if t1 or tr1:
                env_plain.reset(seed=5)
                env_loaded.reset(seed=5)


class TestBuiltinLinearPotentialShapeValidation:
    """Shape-mismatch in the potential weights must fail loudly."""

    def test_wrong_shape_rejected(self) -> None:
        import numpy as np  # local — test-only
        with pytest.raises(ValueError, match="shape"):
            BuiltinLinearPotential(
                weights=np.zeros(17, dtype=np.float32),  # wrong
            )
