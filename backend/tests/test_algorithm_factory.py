"""Factory dispatch matrix for the ADR 0017 ``algorithm`` axis.

S3 already pins ``policy_type`` dispatch; this suite pins the second
axis — ``algorithm`` — and every implemented × reserved combination
so a typo in ``policy_factory.py`` can't silently downgrade an
``sac`` run to PPO (or vice versa).
"""

from __future__ import annotations

import pytest

from backend.rl.policy_factory import (
    IMPLEMENTED_ALGORITHMS,
    SAC_DEFAULT_KWARGS,
    VALID_ALGORITHMS,
    make_policy_spec,
)

NET_ARCH = [256, 256]


class TestAlgorithmEnumShape:
    """The ``algorithm`` enum pins the same way ``policy_type`` /
    ``reward_model`` do: one place changes them, the FE/BE contract
    follows."""

    def test_valid_enum_contains_all_implemented(self) -> None:
        # Enum grew from {ppo, sac} (S4) to {ppo, sac, dreamer_v3}
        # (S5, ADR 0018). Any future enum addition without a matching
        # factory cell is what this test catches.
        assert set(VALID_ALGORITHMS) == {"ppo", "sac", "dreamer_v3"}

    def test_implemented_algorithms(self) -> None:
        assert set(IMPLEMENTED_ALGORITHMS) == {"ppo", "sac", "dreamer_v3"}

    def test_sac_default_kwargs_pinned(self) -> None:
        # ADR 0017 §5: fixed knobs. Surfacing any of these on the WS
        # payload without updating the ADR is the drift this catches.
        assert SAC_DEFAULT_KWARGS["buffer_size"] == 1_000_000
        assert SAC_DEFAULT_KWARGS["learning_starts"] == 10_000
        assert SAC_DEFAULT_KWARGS["batch_size"] == 256
        assert SAC_DEFAULT_KWARGS["ent_coef"] == "auto"
        assert SAC_DEFAULT_KWARGS["target_entropy"] == "auto"


class TestPpoDispatchUnchanged:
    """ADR 0017: the ppo axis must be bit-identical to pre-S4. These
    tests duplicate S3's spec-level assertions against the new
    two-axis signature to prove the default path didn't drift."""

    def test_ppo_mlp_v1(self) -> None:
        from stable_baselines3 import PPO

        spec = make_policy_spec("mlp_v1", NET_ARCH, algorithm="ppo")
        assert spec.algo_class is PPO
        assert spec.policy_class_id == "MlpPolicy"
        assert spec.policy_kwargs == {"net_arch": [256, 256]}

    def test_ppo_lstm_v1(self) -> None:
        from sb3_contrib import RecurrentPPO

        spec = make_policy_spec("lstm_v1", NET_ARCH, algorithm="ppo")
        assert spec.algo_class is RecurrentPPO
        assert spec.policy_class_id == "MlpLstmPolicy"
        # LSTM kwargs still pinned (ADR 0016 §3).
        assert spec.policy_kwargs["lstm_hidden_size"] == 128

    def test_algorithm_defaults_to_ppo(self) -> None:
        # No ``algorithm=`` → defaults to "ppo". The entire pre-S4
        # callsite universe relies on this: trainer, LoadedPolicyBot,
        # S3 parity tests, mlp_v1 factory call. One silent default
        # flip and every pre-S4 test collapses.
        from stable_baselines3 import PPO

        spec_implicit = make_policy_spec("mlp_v1", NET_ARCH)
        spec_explicit = make_policy_spec("mlp_v1", NET_ARCH, algorithm="ppo")
        assert spec_implicit.algo_class is PPO
        assert spec_implicit.algo_class is spec_explicit.algo_class
        assert spec_implicit.policy_class_id == spec_explicit.policy_class_id
        assert spec_implicit.policy_kwargs == spec_explicit.policy_kwargs


class TestSacDispatch:
    """sac × mlp_v1 routes to the vendored SACDiscrete + MlpPolicy
    registry key. net_arch is forwarded; SAC hyperparams are NOT
    baked into policy_kwargs (they go on the algorithm constructor
    directly, sourced from SAC_DEFAULT_KWARGS in the trainer)."""

    def test_sac_mlp_v1(self) -> None:
        from backend.rl.sac_discrete import SACDiscrete

        spec = make_policy_spec("mlp_v1", NET_ARCH, algorithm="sac")
        assert spec.algo_class is SACDiscrete
        assert spec.policy_class_id == "MlpPolicy"
        # net_arch is the only policy_kwarg — SAC hyperparams live
        # in SAC_DEFAULT_KWARGS, not here.
        assert spec.policy_kwargs == {"net_arch": [256, 256]}


class TestReservedCells:
    """Unimplemented cells must raise NotImplementedError with a
    message that names both axes — so the FE error surfaces *why*
    the cell isn't available (algorithm vs policy_type vs both)."""

    def test_sac_lstm_v1_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError) as exc_info:
            make_policy_spec("lstm_v1", NET_ARCH, algorithm="sac")
        # Error message must reference both axes — the ADR §4 reader
        # should know immediately which cell isn't wired.
        msg = str(exc_info.value)
        assert "sac" in msg and "lstm_v1" in msg

    @pytest.mark.parametrize("reserved_pt", ["gru_v1", "transformer_v1"])
    def test_sac_reserved_policy_type(self, reserved_pt: str) -> None:
        # ADR 0016 reserved policy_types raise before the algorithm
        # axis is consulted — same behaviour under ppo and sac.
        with pytest.raises(NotImplementedError, match="reserved"):
            make_policy_spec(reserved_pt, NET_ARCH, algorithm="sac")

    @pytest.mark.parametrize("reserved_pt", ["gru_v1", "transformer_v1"])
    def test_ppo_reserved_policy_type_unchanged(self, reserved_pt: str) -> None:
        # S3 behaviour preserved.
        with pytest.raises(NotImplementedError, match="reserved"):
            make_policy_spec(reserved_pt, NET_ARCH, algorithm="ppo")


class TestUnknownAlgorithm:
    """Anything outside the algorithm enum is a boundary-contract
    violation. WS validator + trainer.start() are the primary
    guardrails; the factory assertion is the last-resort trap."""

    @pytest.mark.parametrize("bad", [
        "",
        "PPO",            # case-sensitive
        "ppo ",           # trailing whitespace
        "dqn",            # plausible future additions — not yet enum
        "a2c",
        "sac_discrete",   # vendored class name, not the enum key
    ])
    def test_unknown_algorithm_raises_assertion(self, bad: str) -> None:
        with pytest.raises(AssertionError, match="algorithm"):
            make_policy_spec("mlp_v1", NET_ARCH, algorithm=bad)
