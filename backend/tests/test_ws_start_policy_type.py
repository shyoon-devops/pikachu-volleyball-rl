"""WsTrainingStartPayload.policy_type validation (ADR 0016 S3).

Boundary contract tests mirroring the reward_model suite: the four
enum members pass, the field defaults to ``mlp_v1`` when omitted, and
any unknown value is rejected at parse time (Pydantic ``Literal``) so
the WS handler never sees it and the caller gets a 400-equivalent
validation error.
"""

from __future__ import annotations

import pytest

from backend.app.models.schemas import WsTrainingStartPayload
from backend.app.ws.validation import (
    ParsedMessage,
    ValidationFailure,
    parse_ws_message,
)


class TestPolicyTypeDefault:
    def test_missing_field_defaults_to_mlp_v1(self):
        """Pre-Sprint-3 callers stay on SB3's MlpPolicy branch."""
        payload = WsTrainingStartPayload()
        assert payload.policy_type == "mlp_v1"

    def test_empty_payload_parse_yields_mlp_v1(self):
        result = parse_ws_message({"type": "training:start", "payload": {}})
        assert isinstance(result, ParsedMessage)
        assert result.payload.policy_type == "mlp_v1"


class TestPolicyTypeValidValues:
    @pytest.mark.parametrize(
        "value", ["mlp_v1", "lstm_v1", "gru_v1", "transformer_v1"]
    )
    def test_all_four_enum_members_accepted(self, value):
        """All four enum members parse — reserved values are runtime-
        gated by the trainer, NOT by schema rejection (ADR §8)."""
        payload = WsTrainingStartPayload(policy_type=value)
        assert payload.policy_type == value

    @pytest.mark.parametrize(
        "value", ["mlp_v1", "lstm_v1", "gru_v1", "transformer_v1"]
    )
    def test_parse_accepts_all_four_via_ws(self, value):
        result = parse_ws_message(
            {"type": "training:start", "payload": {"policy_type": value}}
        )
        assert isinstance(result, ParsedMessage)
        assert result.payload.policy_type == value


class TestPolicyTypeRejectsUnknown:
    def test_unknown_string_rejected_at_parse(self):
        result = parse_ws_message(
            {"type": "training:start", "payload": {"policy_type": "invalid"}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_empty_string_rejected(self):
        result = parse_ws_message(
            {"type": "training:start", "payload": {"policy_type": ""}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_wrong_type_rejected(self):
        result = parse_ws_message(
            {"type": "training:start", "payload": {"policy_type": 42}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_case_sensitive_match(self):
        """``"MLP_v1"`` must not validate — Literal is case-sensitive."""
        result = parse_ws_message(
            {
                "type": "training:start",
                "payload": {"policy_type": "MLP_v1"},
            }
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_adjacent_value_rejected(self):
        """Plausible-looking typo (``"mlp_v2"``) must be rejected."""
        result = parse_ws_message(
            {"type": "training:start", "payload": {"policy_type": "mlp_v2"}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"


class TestPolicyTypeCoexistsWithRewardModel:
    """The two S2/S3 selectors are independent — setting one must not
    influence the other's validation path."""

    def test_both_fields_accepted_together(self):
        payload = WsTrainingStartPayload(
            reward_model="sparse_v1", policy_type="lstm_v1"
        )
        assert payload.reward_model == "sparse_v1"
        assert payload.policy_type == "lstm_v1"

    def test_invalid_policy_does_not_mask_reward(self):
        """Even with a valid reward_model, invalid policy_type rejects."""
        result = parse_ws_message({
            "type": "training:start",
            "payload": {
                "reward_model": "sparse_v1",
                "policy_type": "nope",
            },
        })
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"
