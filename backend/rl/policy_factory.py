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

# ADR 0017 §3: second boundary axis added in Sprint 4. ``ppo`` is
# the default so every pre-S4 callsite (including the trainer + S3
# parity tests) keeps its bit-identical PPO construction — the S4
# factory change is purely additive.
VALID_ALGORITHMS: tuple[str, ...] = ("ppo", "sac")
IMPLEMENTED_ALGORITHMS: tuple[str, ...] = ("ppo", "sac")

# ADR 0017 §5: SAC-Discrete defaults. Not WS-surfaced. Aligned with
# the Christodoulou 2019 implementation conventions + SB3 SAC
# hyperparam naming so readers recognise them. Buffer size kept at
# the SB3 default (1M) — smaller values trade off sample reuse for
# memory; we'd rather page-swap than silently collapse to a few
# thousand steps.
SAC_DEFAULT_KWARGS: dict[str, Any] = {
    "learning_rate": 3e-4,
    "buffer_size": 1_000_000,
    "learning_starts": 10_000,
    "batch_size": 256,
    "tau": 0.005,
    "gamma": 0.99,
    "train_freq": 1,
    "gradient_steps": 1,
    "ent_coef": "auto",
    "target_update_interval": 1,
    "target_entropy": "auto",
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


def make_policy_spec(
    policy_type: str,
    net_arch: list[int],
    *,
    algorithm: str = "ppo",
) -> PolicySpec:
    """Return the SB3 construction triple for a given
    ``(algorithm, policy_type)`` pair.

    ``algorithm`` is keyword-only with an ``"ppo"`` default so every
    pre-S4 callsite (trainer, S3 tests) keeps its bit-identical PPO
    construction path — ADR 0017's S4 extension is additive.

    Parameters
    ----------
    policy_type:
        One of :data:`VALID_POLICY_TYPES`. Unknown → ``AssertionError``;
        the WS validator + env constructor are the primary guardrails,
        this assertion is the last-resort "caller bypassed us" signal.
    net_arch:
        Shared actor/critic hidden-layer sizes. Forwarded as
        ``policy_kwargs={"net_arch": net_arch, ...}``.
    algorithm:
        One of :data:`VALID_ALGORITHMS` (ADR 0017 §3). Unknown →
        ``AssertionError``. Current implementation matrix:

        * ``ppo × mlp_v1``   — SB3 PPO + ``"MlpPolicy"`` (S1/S2 default).
        * ``ppo × lstm_v1``  — sb3-contrib RecurrentPPO + ``"MlpLstmPolicy"``
          (ADR 0016).
        * ``sac × mlp_v1``   — vendored :class:`SACDiscrete` +
          ``"MlpPolicy"`` (ADR 0017 §7).
        * ``sac × lstm_v1``  — **not implemented**. SB3 has no
          ``RecurrentSAC``; sb3-contrib has no recurrent off-policy
          algorithm. Deferred to S5 per ADR 0017 §4.
        * Any ``algorithm × {gru_v1, transformer_v1}`` — inherits
          ADR 0016's reserved-value gate (``NotImplementedError``).

    Raises
    ------
    AssertionError
        Either axis is outside its enum.
    NotImplementedError
        The ``(algorithm, policy_type)`` cell is reserved / deferred.
    """
    assert policy_type in VALID_POLICY_TYPES, (
        f"policy_type must be one of {VALID_POLICY_TYPES}, got {policy_type!r}"
    )
    assert algorithm in VALID_ALGORITHMS, (
        f"algorithm must be one of {VALID_ALGORITHMS}, got {algorithm!r}"
    )
    if policy_type not in IMPLEMENTED_POLICY_TYPES:
        raise NotImplementedError(
            f"policy_type={policy_type!r} is reserved by ADR 0016 but not "
            f"implemented in v2.x. Implemented: {IMPLEMENTED_POLICY_TYPES}"
        )

    # Import lazily so modules that only need the enum constants
    # (schema validators, run-record writers) don't pay the SB3 /
    # sb3-contrib import cost at module-load time.
    if algorithm == "ppo" and policy_type == "mlp_v1":
        from stable_baselines3 import PPO  # noqa: PLC0415

        return PolicySpec(
            algo_class=PPO,
            policy_class_id="MlpPolicy",
            policy_kwargs={"net_arch": list(net_arch)},
        )

    if algorithm == "ppo" and policy_type == "lstm_v1":
        # sb3-contrib RecurrentPPO. Registry key "MlpLstmPolicy"
        # resolves to RecurrentActorCriticPolicy at construction —
        # we do NOT import the concrete class here because its path
        # varies across sb3-contrib releases; the string form is the
        # stable public contract.
        from sb3_contrib import RecurrentPPO  # noqa: PLC0415

        return PolicySpec(
            algo_class=RecurrentPPO,
            policy_class_id="MlpLstmPolicy",
            policy_kwargs={"net_arch": list(net_arch), **LSTM_POLICY_KWARGS},
        )

    if algorithm == "sac" and policy_type == "mlp_v1":
        # Vendored SAC-Discrete (ADR 0017 §2/§7). sb3-contrib 2.8.0
        # does NOT ship SAC-Discrete — we own ``backend/rl/sac_discrete.py``
        # rather than pull a third-party package, which would lock
        # us to someone else's release cadence.
        from backend.rl.sac_discrete import SACDiscrete  # noqa: PLC0415

        return PolicySpec(
            algo_class=SACDiscrete,
            policy_class_id="MlpPolicy",
            policy_kwargs={"net_arch": list(net_arch)},
        )

    # Remaining cell is sac × lstm_v1 — ADR 0017 §4 explicitly
    # defers it to S5 (no RecurrentSAC in SB3 or sb3-contrib).
    # Raise with the pair so the FE/test surface gets a clear
    # "why this combination" message.
    raise NotImplementedError(
        f"algorithm={algorithm!r} × policy_type={policy_type!r} is "
        f"not implemented in v2.x (ADR 0017 §4). A GRU-head SAC "
        f"variant is deferred to Sprint 5."
    )
