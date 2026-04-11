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
