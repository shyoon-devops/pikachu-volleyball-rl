"""WebSocket tests."""


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
