"""Factory dispatch for the ADR 0018 ``dreamer_v3`` algorithm cell.

S4's ``test_algorithm_factory.py`` already pins the matrix surface
(enum, ppo + sac cells, reserved cells); this file adds the S5
dreamer cell — construction, policy_type orthogonality, and the
invariant that adding ``dreamer_v3`` didn't disturb the pre-S5
factory behaviour.
"""

from __future__ import annotations

import pytest

from backend.rl.policy_factory import (
    IMPLEMENTED_ALGORITHMS,
    VALID_ALGORITHMS,
    make_policy_spec,
)

NET_ARCH = [256, 256]


class TestDreamerInEnum:
    """The enum grew by one value (ADR 0018 §4); implemented set
    stayed equal to valid set (no reserved values at S5)."""

    def test_dreamer_v3_in_valid_enum(self) -> None:
        assert "dreamer_v3" in VALID_ALGORITHMS
        assert set(VALID_ALGORITHMS) == {"ppo", "sac", "dreamer_v3"}

    def test_dreamer_v3_implemented(self) -> None:
        assert "dreamer_v3" in IMPLEMENTED_ALGORITHMS
        assert set(IMPLEMENTED_ALGORITHMS) == {"ppo", "sac", "dreamer_v3"}


class TestDreamerDispatch:
    """sac routes to SACDiscrete, ppo to PPO/RecurrentPPO; dreamer
    must route to the vendored DreamerAgent regardless of
    policy_type — ADR 0018 §4 makes policy_type orthogonal on the
    dreamer path."""

    def test_dreamer_v3_returns_dreamer_agent(self) -> None:
        from backend.rl.dreamer_runner import DreamerAgent

        spec = make_policy_spec("mlp_v1", NET_ARCH, algorithm="dreamer_v3")
        assert spec.algo_class is DreamerAgent
        # policy_class_id is a sentinel (not consumed by the
        # DreamerAgent constructor) but must be a string so
        # downstream audit/logging code doesn't choke on None.
        assert isinstance(spec.policy_class_id, str)

    @pytest.mark.parametrize("pt", ["mlp_v1", "lstm_v1"])
    def test_dreamer_ignores_policy_type(self, pt: str) -> None:
        """Both implemented policy_types dispatch to DreamerAgent —
        policy_type is intentionally orthogonal on this path (ADR
        0018 §4). Reserved policy_types still raise from the ADR
        0016 gate (separate test below)."""
        from backend.rl.dreamer_runner import DreamerAgent

        spec = make_policy_spec(pt, NET_ARCH, algorithm="dreamer_v3")
        assert spec.algo_class is DreamerAgent

    @pytest.mark.parametrize("reserved_pt", ["gru_v1", "transformer_v1"])
    def test_dreamer_reserved_policy_type_still_gated(
        self, reserved_pt: str
    ) -> None:
        # ADR 0016's reserved-policy_type gate fires before the
        # algorithm is consulted — identical behaviour under ppo,
        # sac, and dreamer_v3. Pins the gate precedence.
        with pytest.raises(NotImplementedError, match="reserved"):
            make_policy_spec(reserved_pt, NET_ARCH, algorithm="dreamer_v3")


class TestS4PathsUnchanged:
    """Adding dreamer_v3 to the enum must not have disturbed the
    ppo / sac cells — duplicates S4's assertions to make drift
    from the S5 addition immediately visible."""

    def test_ppo_mlp_v1_unchanged(self) -> None:
        from stable_baselines3 import PPO

        spec = make_policy_spec("mlp_v1", NET_ARCH, algorithm="ppo")
        assert spec.algo_class is PPO
        assert spec.policy_class_id == "MlpPolicy"

    def test_sac_mlp_v1_unchanged(self) -> None:
        from backend.rl.sac_discrete import SACDiscrete

        spec = make_policy_spec("mlp_v1", NET_ARCH, algorithm="sac")
        assert spec.algo_class is SACDiscrete
        assert spec.policy_class_id == "MlpPolicy"

    def test_default_still_ppo(self) -> None:
        # Missing algorithm kwarg → ppo. Pre-S2 + S3 + S4 callsites
        # (and a few tests) rely on this.
        from stable_baselines3 import PPO

        spec = make_policy_spec("mlp_v1", NET_ARCH)
        assert spec.algo_class is PPO
