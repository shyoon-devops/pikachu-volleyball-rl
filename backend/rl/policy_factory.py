"""Policy-architecture dispatch for the RL trainer (ADR 0016).

The trainer and ``LoadedPolicyBot`` both need to pick an SB3 algorithm
class + policy-registry key + kwargs given only the boundary-contract
``policy_type`` string. Centralising that lookup here keeps the SB3
class names from leaking through the trainer and gives us one place to
evolve the matrix when ``gru_v1`` / ``transformer_v1`` land in a later
sprint.

Contract:
  * ``mlp_v1``  → PPO + ``"MlpPolicy"`` (v1.0.0-compatible default).
  * ``lstm_v1`` → ``RecurrentPPO`` + ``"MlpLstmPolicy"`` with the
    LSTM hyperparams pinned by ADR 0016 §3.
  * ``gru_v1`` / ``transformer_v1`` — **reserved**: accepted by the
    boundary validator so the WS enum doesn't need to change when we
    ship them, but raise ``NotImplementedError`` here so a caller that
    actually tries to train with one fails loudly at start-up rather
    than silently dropping back to MLP.

LSTM hyperparameters are pinned — the ADR explicitly keeps
``lstm_hidden_size`` / ``n_lstm_layers`` off the WS payload for v2.x.
Exposing them would create a compatibility matrix between checkpoints
and would leak "advanced hyperparam" surface area that the PM asked to
defer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VALID_POLICY_TYPES: tuple[str, ...] = (
    "mlp_v1",
    "lstm_v1",
    "gru_v1",
    "transformer_v1",
)

# Subset of VALID_POLICY_TYPES that actually construct a model. The
# rest are reserved for future sprints; see module docstring.
IMPLEMENTED_POLICY_TYPES: tuple[str, ...] = ("mlp_v1", "lstm_v1")

# ADR 0016 §3: fixed for first release. Do not surface on WS.
LSTM_POLICY_KWARGS: dict[str, Any] = {
    "lstm_hidden_size": 128,
    "n_lstm_layers": 1,
    "shared_lstm": False,
    "enable_critic_lstm": True,
}


@dataclass(frozen=True)
class PolicySpec:
    """Triple ``(algo_class, policy_class_id, policy_kwargs)`` that the
    trainer feeds straight into the SB3 constructor.

    ``policy_class_id`` is SB3's string registry key ("MlpPolicy",
    "MlpLstmPolicy") rather than the concrete class object — the
    registry resolves it at model-construction time, which matches how
    the SB3 examples are written and avoids a hard import of the
    Recurrent policy class (which moved between sb3-contrib versions)
    at the top of this file.

    ``policy_kwargs`` is the dict forwarded as the SB3 ``policy_kwargs``
    argument. The trainer's global ``net_arch`` is merged in at
    dispatch time (by ``make_policy_spec``) so the factory is the sole
    source of truth for per-policy architecture bits.
    """

    algo_class: type
    policy_class_id: str
    policy_kwargs: dict[str, Any]


def make_policy_spec(policy_type: str, net_arch: list[int]) -> PolicySpec:
    """Return the SB3 construction triple for a given ``policy_type``.

    Parameters
    ----------
    policy_type:
        One of :data:`VALID_POLICY_TYPES`. Unknown values raise
        ``AssertionError`` because the WS validator and env constructor
        are the boundary guardrails — reaching this function with an
        unknown value means a caller bypassed them and we want the
        loudest possible failure.
    net_arch:
        Shared actor/critic hidden-layer sizes. Forwarded as
        ``policy_kwargs={"net_arch": net_arch, ...}``.

    Raises
    ------
    AssertionError
        ``policy_type`` is not in :data:`VALID_POLICY_TYPES`.
    NotImplementedError
        ``policy_type`` is a reserved value (``gru_v1`` /
        ``transformer_v1``) — these ship in a later sprint.
    """
    assert policy_type in VALID_POLICY_TYPES, (
        f"policy_type must be one of {VALID_POLICY_TYPES}, got {policy_type!r}"
    )
    if policy_type not in IMPLEMENTED_POLICY_TYPES:
        raise NotImplementedError(
            f"policy_type={policy_type!r} is reserved by ADR 0016 but not "
            f"implemented in v2.x. Implemented: {IMPLEMENTED_POLICY_TYPES}"
        )

    # Import lazily so modules that only need the enum constants
    # (schema validators, run-record writers) don't pay the SB3 /
    # sb3-contrib import cost at module-load time.
    if policy_type == "mlp_v1":
        from stable_baselines3 import PPO  # noqa: PLC0415

        return PolicySpec(
            algo_class=PPO,
            policy_class_id="MlpPolicy",
            policy_kwargs={"net_arch": list(net_arch)},
        )

    # lstm_v1: sb3-contrib RecurrentPPO. The registry key
    # "MlpLstmPolicy" resolves to RecurrentActorCriticPolicy at
    # construction time — we do NOT import the concrete class here
    # because its import path varies across sb3-contrib releases and
    # the string form is the stable public contract.
    from sb3_contrib import RecurrentPPO  # noqa: PLC0415

    return PolicySpec(
        algo_class=RecurrentPPO,
        policy_class_id="MlpLstmPolicy",
        policy_kwargs={"net_arch": list(net_arch), **LSTM_POLICY_KWARGS},
    )
