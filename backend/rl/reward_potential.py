"""Potential functions for Ng-Harada-Russell shaping (ADR 0015).

The shaped reward family ``learned_shaped_v1`` composes a sparse
terminal reward (win/lose + per-point) with a potential-based shaping
term ``F(s, a, s') = γ·Φ(s') − Φ(s)``. Ng et al. (1999) proved this
keeps the optimal policy identical to the sparse-only baseline — the
shaping only changes the *gradient* the learner sees, never the
optimization target.

This module exposes the ``PotentialFn`` protocol plus one concrete
placeholder (``BuiltinLinearPotential`` with zero-initialised weights)
so the env-side integration can be landed and tested independently
of the IRL / demonstrator-fitting work scheduled in a later ADR.

When the placeholder's weights are all zeros the shaping term
collapses to zero on every transition, so ``learned_shaped_v1``
behaves bit-identically to ``sparse_v1`` until an IRL-trained
replacement drops in. That's intentional: it gives the trainer + WS
path + tests a working end-to-end surface while the learned Φ is
still in the oven.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

# Observation dimension matches PikachuVolleyballEnv.observation_space
# (Box shape=(18,)) so any concrete PotentialFn can assume the obs
# vector length is fixed.
OBS_DIM: int = 18


@runtime_checkable
class PotentialFn(Protocol):
    """Callable from the 18-feature env obs to a scalar potential Φ(s).

    Implementations must be pure: ``phi(obs)`` given the same input
    always returns the same output. The env caches the previous
    frame's Φ(s) across step() calls, so drift in the function under
    the hood would silently corrupt the Ng-Harada-Russell invariance.
    """

    def phi(self, obs: np.ndarray) -> float: ...


@dataclass
class BuiltinLinearPotential:
    """Placeholder linear potential Φ(s) = w · s + b.

    Used as the default for ``learned_shaped_v1`` while the IRL
    training path matures. Weights and bias default to zero, making
    the potential identically zero — and therefore the shaping term
    identically zero — across every transition. An IRL fitter will
    later overwrite ``weights`` / ``bias`` in-place (or construct a
    fresh instance) without changing the env-side contract.

    ``weights`` is an (18,) float32 array; the constructor accepts
    any array-like and normalises to float32 for numerical parity
    with the observation's dtype.
    """

    weights: np.ndarray
    bias: float = 0.0

    @classmethod
    def zeros(cls) -> "BuiltinLinearPotential":
        """Default zero-weights instance — the ``learned_shaped_v1``
        scaffold ships with this so shaping contributes 0.0 until an
        IRL-trained instance is loaded."""
        return cls(weights=np.zeros(OBS_DIM, dtype=np.float32), bias=0.0)

    def __post_init__(self) -> None:
        arr = np.asarray(self.weights, dtype=np.float32)
        if arr.shape != (OBS_DIM,):
            raise ValueError(
                f"BuiltinLinearPotential weights must have shape "
                f"({OBS_DIM},), got {arr.shape}"
            )
        # Overwrite with the normalised array so subsequent phi() calls
        # don't pay the cast cost every step.
        object.__setattr__(self, "weights", arr)

    def phi(self, obs: np.ndarray) -> float:
        # Explicit float cast — ``obs`` may be float32; float() keeps
        # the host Python accumulator deterministic for test-parity
        # across platforms. NOTE: for the zeros placeholder this always
        # returns exactly 0.0, which is the scaffold's contract.
        return float(np.dot(self.weights, obs) + self.bias)
