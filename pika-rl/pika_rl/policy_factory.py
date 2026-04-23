"""Shim over ``backend.rl.policy_factory``.

Re-exports the algorithm × policy_type dispatcher + enum constants
so downstream repos (MineRL Diamond) can depend on the stable
``pika_rl.policy_factory.*`` surface instead of reaching into
``backend.rl.*``. A ``policy_factory`` alias for ``make_policy_spec``
is exposed to match the naming used in external planning docs.
"""

from backend.rl.policy_factory import (  # noqa: F401 — re-export
    IMPLEMENTED_ALGORITHMS,
    IMPLEMENTED_POLICY_TYPES,
    LSTM_POLICY_KWARGS,
    SAC_DEFAULT_KWARGS,
    VALID_ALGORITHMS,
    VALID_POLICY_TYPES,
    PolicySpec,
    make_policy_spec,
)

# External docs (Phase 0 research, MineRL repo plan) refer to the
# dispatcher as ``policy_factory``; in-repo it's ``make_policy_spec``.
# Expose both so either name works without a downstream refactor.
policy_factory = make_policy_spec

__all__ = [
    "IMPLEMENTED_ALGORITHMS",
    "IMPLEMENTED_POLICY_TYPES",
    "LSTM_POLICY_KWARGS",
    "SAC_DEFAULT_KWARGS",
    "VALID_ALGORITHMS",
    "VALID_POLICY_TYPES",
    "PolicySpec",
    "make_policy_spec",
    "policy_factory",
]
