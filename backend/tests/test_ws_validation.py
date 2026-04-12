"""Tests for the Pydantic WebSocket message validation layer."""

from __future__ import annotations

import pytest

from backend.app.models.schemas import (
    WsReplayRequestPayload,
    WsSetLevelPayload,
    WsTrainingStartPayload,
)
from backend.app.ws.validation import (
    ParsedMessage,
    ValidationFailure,
    parse_ws_message,
)


# --- unit-level: parse_ws_message -------------------------------------------


def test_parse_rejects_non_dict_input():
    result = parse_ws_message("not-a-dict")
    assert isinstance(result, ValidationFailure)
    assert result.code == "envelope_invalid"


def test_parse_rejects_missing_type():
    result = parse_ws_message({"payload": {}})
    assert isinstance(result, ValidationFailure)
    assert result.code == "envelope_invalid"


def test_parse_rejects_empty_type():
    """Empty string type is refused by WsEnvelope's min_length=1 constraint."""
    result = parse_ws_message({"type": "", "payload": {}})
    assert isinstance(result, ValidationFailure)
    assert result.code == "envelope_invalid"


def test_parse_rejects_unknown_type():
    result = parse_ws_message({"type": "nope:unknown", "payload": {}})
    assert isinstance(result, ValidationFailure)
    assert result.code == "unknown_type"
    assert "nope:unknown" in result.message


def test_parse_rejects_invalid_payload():
    result = parse_ws_message(
        {"type": "training:start", "payload": {"bot_level": 99}}
    )
    assert isinstance(result, ValidationFailure)
    assert result.code == "payload_invalid"


def test_parse_accepts_training_start_defaults():
    result = parse_ws_message({"type": "training:start", "payload": {}})
    assert isinstance(result, ParsedMessage)
    assert result.type == "training:start"
    assert isinstance(result.payload, WsTrainingStartPayload)
    assert result.payload.bot_level == 1  # default
    assert result.payload.total_timesteps == 1_000_000


def test_parse_accepts_training_start_with_values():
    result = parse_ws_message(
        {
            "type": "training:start",
            "payload": {"bot_level": 3, "total_timesteps": 5000},
        }
    )
    assert isinstance(result, ParsedMessage)
    assert result.payload.bot_level == 3
    assert result.payload.total_timesteps == 5000


def test_parse_accepts_set_level():
    result = parse_ws_message({"type": "training:set_level", "payload": {"level": 4}})
    assert isinstance(result, ParsedMessage)
    assert isinstance(result.payload, WsSetLevelPayload)
    assert result.payload.level == 4


def test_parse_accepts_replay_request():
    result = parse_ws_message(
        {"type": "replay:request", "payload": {"game_id": "abc-123"}}
    )
    assert isinstance(result, ParsedMessage)
    assert isinstance(result.payload, WsReplayRequestPayload)
    assert result.payload.game_id == "abc-123"


def test_parse_rejects_oversized_game_id():
    """Game IDs >128 chars are suspicious — reject."""
    result = parse_ws_message(
        {"type": "replay:request", "payload": {"game_id": "x" * 200}}
    )
    assert isinstance(result, ValidationFailure)
    assert result.code == "payload_invalid"


def test_parse_accepts_empty_payload_for_stop():
    result = parse_ws_message({"type": "training:stop"})
    assert isinstance(result, ParsedMessage)
    assert result.type == "training:stop"


def test_parse_accepts_pong():
    result = parse_ws_message({"type": "pong"})
    assert isinstance(result, ParsedMessage)
    assert result.type == "pong"


def test_parse_ignores_extra_envelope_fields():
    """Unknown envelope fields are silently dropped (extra='ignore')."""
    result = parse_ws_message(
        {"type": "training:stop", "payload": {}, "extra_field": "foo"}
    )
    assert isinstance(result, ParsedMessage)


# --- integration-level: handlers go through the new validator --------------


def test_ws_rejects_non_object_message(client):
    """Server rejects raw arrays/strings as invalid envelopes."""
    with client.websocket_connect("/ws") as ws:
        # send raw JSON array
        ws.send_json(["not", "an", "object"])
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "envelope_invalid"


def test_ws_rejects_missing_type(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"payload": {}})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "envelope_invalid"


def test_ws_invalid_payload_returns_payload_invalid_code(client):
    """Payload-level validation error is distinguishable from envelope errors."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            {"type": "training:start", "payload": {"bot_level": -1}}
        )
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["payload"]["code"] == "payload_invalid"


def test_ws_ping_gets_pong_reply(client):
    """Client-initiated ping receives a pong reply."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "ping"})
        resp = ws.receive_json()
        assert resp["type"] == "pong"
