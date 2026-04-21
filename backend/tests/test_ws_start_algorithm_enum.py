"""WsTrainingStartPayload.algorithm validation (ADR 0017 S4).

Net-new field; follows the S2 reward_model / S3 policy_type pattern.
The Literal narrows accepted values to ``"ppo"`` / ``"sac"`` — future
additions (ADR §3: ``dqn`` / ``ppo_mask`` / ``sac_crossq``) extend
this membership rather than introducing a parallel field.
"""

from __future__ import annotations

import pytest

from backend.app.models.schemas import WsTrainingStartPayload
from backend.app.ws.validation import (
    ParsedMessage,
    ValidationFailure,
    parse_ws_message,
)


class TestAlgorithmDefault:
    def test_missing_field_defaults_to_ppo(self):
        """Pre-S4 callers stay on on-policy PPO."""
        payload = WsTrainingStartPayload()
        assert payload.algorithm == "ppo"

    def test_empty_payload_parse_yields_ppo(self):
        result = parse_ws_message({"type": "training:start", "payload": {}})
        assert isinstance(result, ParsedMessage)
        assert result.payload.algorithm == "ppo"


class TestAlgorithmValidValues:
    @pytest.mark.parametrize("value", ["ppo", "sac"])
    def test_both_enum_members_accepted(self, value):
        payload = WsTrainingStartPayload(algorithm=value)
        assert payload.algorithm == value

    @pytest.mark.parametrize("value", ["ppo", "sac"])
    def test_parse_accepts_both_via_ws(self, value):
        result = parse_ws_message(
            {"type": "training:start", "payload": {"algorithm": value}}
        )
        assert isinstance(result, ParsedMessage)
        assert result.payload.algorithm == value


class TestAlgorithmRejectsUnknown:
    def test_unknown_string_rejected_at_parse(self):
        """Pydantic Literal → ``payload_invalid`` → 400-equivalent."""
        result = parse_ws_message(
            {"type": "training:start", "payload": {"algorithm": "invalid"}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_empty_string_rejected(self):
        result = parse_ws_message(
            {"type": "training:start", "payload": {"algorithm": ""}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_wrong_type_rejected(self):
        result = parse_ws_message(
            {"type": "training:start", "payload": {"algorithm": 1}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_case_sensitive_match(self):
        """``"PPO"`` must not validate — Literal is case-sensitive."""
        result = parse_ws_message(
            {"type": "training:start", "payload": {"algorithm": "PPO"}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_reserved_future_values_still_reject(self):
        """ADR §3 reserves ``dqn`` / ``ppo_mask`` / ``sac_crossq`` —
        they're not accepted until the schema adds them. Guards against
        a future drift where docs list a value that the enum doesn't."""
        for reserved in ("dqn", "ppo_mask", "sac_crossq", "sac_continuous"):
            result = parse_ws_message({
                "type": "training:start",
                "payload": {"algorithm": reserved},
            })
            assert isinstance(result, ValidationFailure), (
                f"{reserved!r} unexpectedly parsed; schema drifted from ADR 0017"
            )


class TestAlgorithmCoexistsWithSelectors:
    """algorithm is orthogonal to reward_model + policy_type — none of
    them should influence another's validation path."""

    def test_all_three_selectors_accepted_together(self):
        payload = WsTrainingStartPayload(
            algorithm="sac",
            policy_type="mlp_v1",
            reward_model="sparse_v1",
        )
        assert payload.algorithm == "sac"
        assert payload.policy_type == "mlp_v1"
        assert payload.reward_model == "sparse_v1"

    def test_invalid_algorithm_does_not_mask_others(self):
        """Even with valid policy_type + reward_model, invalid
        algorithm still trips the validator."""
        result = parse_ws_message({
            "type": "training:start",
            "payload": {
                "algorithm": "nope",
                "policy_type": "lstm_v1",
                "reward_model": "sparse_v1",
            },
        })
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"
