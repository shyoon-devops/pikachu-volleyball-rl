"""WsTrainingStartPayload.reward_model validation (ADR 0015 S2).

Boundary contract tests: the three enum members pass, the field
defaults to ``shaped_v1`` when omitted, and any unknown value is
rejected at parse time (Pydantic ``Literal``) so the WS handler never
sees it and the caller gets a 400-equivalent validation error.
"""

from __future__ import annotations

import pytest

from backend.app.models.schemas import WsTrainingStartPayload
from backend.app.ws.validation import (
    ParsedMessage,
    ValidationFailure,
    parse_ws_message,
)


class TestRewardModelDefault:
    def test_missing_field_defaults_to_shaped_v1(self):
        """Legacy callers that omit the field stay on v1.0.0 behavior."""
        payload = WsTrainingStartPayload()
        assert payload.reward_model == "shaped_v1"

    def test_empty_payload_parse_yields_shaped_v1(self):
        result = parse_ws_message({"type": "training:start", "payload": {}})
        assert isinstance(result, ParsedMessage)
        assert result.payload.reward_model == "shaped_v1"


class TestRewardModelValidValues:
    @pytest.mark.parametrize(
        "value", ["shaped_v1", "sparse_v1", "learned_shaped_v1"]
    )
    def test_all_three_enum_members_accepted(self, value):
        payload = WsTrainingStartPayload(reward_model=value)
        assert payload.reward_model == value

    @pytest.mark.parametrize(
        "value", ["shaped_v1", "sparse_v1", "learned_shaped_v1"]
    )
    def test_parse_accepts_all_three_via_ws(self, value):
        """End-to-end through the WS parser — exercises the same path the
        FE hits."""
        result = parse_ws_message(
            {"type": "training:start", "payload": {"reward_model": value}}
        )
        assert isinstance(result, ParsedMessage)
        assert result.payload.reward_model == value


class TestRewardModelRejectsUnknown:
    def test_unknown_string_rejected_at_parse(self):
        """Pydantic Literal raises → the validation layer returns a
        ``payload_invalid`` failure, which the WS handler maps to a
        client-visible reject event (equivalent of HTTP 400)."""
        result = parse_ws_message(
            {"type": "training:start", "payload": {"reward_model": "invalid"}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_empty_string_rejected(self):
        result = parse_ws_message(
            {"type": "training:start", "payload": {"reward_model": ""}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_wrong_type_rejected(self):
        """Non-string (e.g. int) — same path, same failure code."""
        result = parse_ws_message(
            {"type": "training:start", "payload": {"reward_model": 42}}
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"

    def test_case_sensitive_match(self):
        """Literal is case-sensitive — ``"Shaped_v1"`` must NOT validate."""
        result = parse_ws_message(
            {
                "type": "training:start",
                "payload": {"reward_model": "Shaped_v1"},
            }
        )
        assert isinstance(result, ValidationFailure)
        assert result.code == "payload_invalid"
