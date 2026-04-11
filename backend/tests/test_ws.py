"""WebSocket tests."""

import pytest


def test_ws_connect_disconnect(client):
    """WebSocket connects and disconnects cleanly."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "training:stop", "payload": {}})
        resp = ws.receive_json()
        assert resp["type"] == "training:status"
        assert resp["payload"]["state"] == "stopped"


def test_ws_unknown_message(client):
    """Unknown message type does not crash the connection."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "unknown:type", "payload": {}})
        # Connection stays alive — send a valid message after
        ws.send_json({"type": "training:stop", "payload": {}})
        resp = ws.receive_json()
        assert resp["type"] == "training:status"


def test_ws_double_training_start(client, app_instance):
    """Sending training:start twice returns error instead of crashing."""
    svc = app_instance.state.training_service

    with client.websocket_connect("/ws") as ws:
        # First start — should succeed
        ws.send_json({"type": "training:start", "payload": {}})
        resp1 = ws.receive_json()
        assert resp1["type"] == "training:status"
        assert resp1["payload"]["state"] == "running"

        # Patch status to return "running" for the second call
        svc.status = lambda: {"state": "running", "current_step": 0, "current_episode": 0}

        # Second start — should get error, not crash
        ws.send_json({"type": "training:start", "payload": {}})
        resp2 = ws.receive_json()
        assert resp2["type"] == "training:error"
        assert "already running" in resp2["payload"]["message"]

        # Connection still alive
        ws.send_json({"type": "training:stop", "payload": {}})
        resp3 = ws.receive_json()
        assert resp3["type"] == "training:status"


def test_ws_invalid_bot_level(client):
    """Invalid bot_level in training:start returns validation error."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "training:start", "payload": {"bot_level": 99}})
        resp = ws.receive_json()
        assert resp["type"] == "error"
        assert "errors" in resp["payload"]["message"]

        # Connection still alive
        ws.send_json({"type": "training:stop", "payload": {}})
        resp2 = ws.receive_json()
        assert resp2["type"] == "training:status"


def test_ws_invalid_set_level(client):
    """Invalid level in training:set_level returns validation error."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "training:set_level", "payload": {"level": 0}})
        resp = ws.receive_json()
        assert resp["type"] == "error"

        ws.send_json({"type": "training:set_level", "payload": {"level": 10}})
        resp2 = ws.receive_json()
        assert resp2["type"] == "error"


def test_ws_empty_replay_request(client):
    """Empty game_id in replay:request returns validation error."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "replay:request", "payload": {"game_id": ""}})
        resp = ws.receive_json()
        assert resp["type"] == "error"


def test_ws_valid_set_level(client):
    """Valid set_level updates and returns status."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "training:set_level", "payload": {"level": 3}})
        resp = ws.receive_json()
        assert resp["type"] == "training:status"
        assert resp["payload"]["bot_level"] == 3
