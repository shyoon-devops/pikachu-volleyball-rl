"""Boundary-contract enforcement for ``policy_type`` enum (ADR 0016).

The SB3 class + policy-registry key triple is the single source of
truth for how the trainer and ``LoadedPolicyBot`` route calls. These
tests pin that routing so a typo in ``trainer.py`` can't silently
downgrade an ``lstm_v1`` run to MLP (or vice versa).

Kept intentionally close to ``test_reward_model_enum_reject.py`` —
both follow the same boundary-validator pattern.
"""

from __future__ import annotations

import pytest

from backend.rl.policy_factory import (
    IMPLEMENTED_POLICY_TYPES,
    LSTM_POLICY_KWARGS,
    VALID_POLICY_TYPES,
    PolicySpec,
    make_policy_spec,
)

NET_ARCH = [256, 256]


class TestEnumShape:
    """The enum and its implemented subset are the FE/BE contract —
    divergence anywhere means the selector shows options the trainer
    can't fulfil. These tests anchor the moment of divergence."""

    def test_valid_enum_contains_expected_four(self) -> None:
        assert set(VALID_POLICY_TYPES) == {
            "mlp_v1", "lstm_v1", "gru_v1", "transformer_v1",
        }

    def test_implemented_subset(self) -> None:
        # Exactly the two that the trainer can construct today. GRU
        # and Transformer are reserved by the enum; bumping this set
        # requires a follow-up sprint ADR.
        assert set(IMPLEMENTED_POLICY_TYPES) == {"mlp_v1", "lstm_v1"}

    def test_lstm_kwargs_pinned(self) -> None:
        # ADR 0016 §3 fixes these values for the first release.
        # Override surface (hidden_size / n_lstm_layers) is
        # intentionally not exposed on the WS payload.
        assert LSTM_POLICY_KWARGS == {
            "lstm_hidden_size": 128,
            "n_lstm_layers": 1,
            "shared_lstm": False,
            "enable_critic_lstm": True,
        }


class TestMlpV1Dispatch:
    """mlp_v1 must route to SB3 PPO + "MlpPolicy" — identical to the
    pre-Sprint-3 hardcoded constructor. Any change here breaks the
    parity test (test_policy_mlp_v1_parity.py)."""

    def test_mlp_v1_spec(self) -> None:
        from stable_baselines3 import PPO
        spec = make_policy_spec("mlp_v1", NET_ARCH)
        assert isinstance(spec, PolicySpec)
        assert spec.algo_class is PPO
        assert spec.policy_class_id == "MlpPolicy"
        # policy_kwargs must carry net_arch only — no LSTM knobs leaking
        # into the MLP path would change PPO's construction signature
        # and silently break pre-Sprint-3 checkpoint compatibility.
        assert spec.policy_kwargs == {"net_arch": [256, 256]}

    def test_net_arch_is_copied(self) -> None:
        # The factory must not alias its caller's net_arch list — an
        # inadvertent append elsewhere would silently reshape the
        # policy network.
        arch: list[int] = [64, 64]
        spec = make_policy_spec("mlp_v1", arch)
        arch.append(128)
        assert spec.policy_kwargs["net_arch"] == [64, 64]


class TestLstmV1Dispatch:
    """lstm_v1 must route to sb3-contrib RecurrentPPO + "MlpLstmPolicy"
    with the ADR-pinned LSTM kwargs merged into policy_kwargs."""

    def test_lstm_v1_spec(self) -> None:
        from sb3_contrib import RecurrentPPO
        spec = make_policy_spec("lstm_v1", NET_ARCH)
        assert spec.algo_class is RecurrentPPO
        assert spec.policy_class_id == "MlpLstmPolicy"
        # policy_kwargs must carry net_arch PLUS the pinned LSTM
        # kwargs — both SB3 and the ADR treat these as a single bag
        # the policy class consumes at construction.
        assert spec.policy_kwargs == {
            "net_arch": [256, 256],
            "lstm_hidden_size": 128,
            "n_lstm_layers": 1,
            "shared_lstm": False,
            "enable_critic_lstm": True,
        }


class TestReservedPolicyTypes:
    """gru_v1 / transformer_v1 are reserved by the enum but not yet
    implemented — they must raise NotImplementedError so a caller
    that bypassed the WS layer and reached the factory gets a loud,
    attributable failure rather than a silent MLP fallback."""

    @pytest.mark.parametrize("reserved", ["gru_v1", "transformer_v1"])
    def test_reserved_raises(self, reserved: str) -> None:
        with pytest.raises(NotImplementedError, match="reserved"):
            make_policy_spec(reserved, NET_ARCH)


class TestUnknownPolicyType:
    """Anything outside the enum is a boundary-contract violation.
    Since the WS validator + manager start() already reject unknowns,
    the factory assertion is a last-resort guardrail — but the
    failure mode must be *immediate*, not a silent default."""

    @pytest.mark.parametrize("bad", [
        "",
        "mlp",            # missing version
        "MLP_V1",         # case-sensitive
        "mlp_v2",         # plausible but not shipped
        "lstm",           # missing version
        "mlp_v1 ",        # trailing whitespace
    ])
    def test_unknown_raises_assertion(self, bad: str) -> None:
        with pytest.raises(AssertionError, match="policy_type"):
            make_policy_spec(bad, NET_ARCH)
