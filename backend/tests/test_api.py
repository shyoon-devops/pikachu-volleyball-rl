"""REST API tests."""


def test_health_check(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_games_empty(client):
    resp = client.get("/api/games")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["total"] == 0


def test_training_status_initial(client):
    resp = client.get("/api/training/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "stopped"


def test_models_empty(client):
    resp = client.get("/api/models")
    assert resp.status_code == 200
    assert resp.json()["models"] == []


def test_game_not_found(client):
    resp = client.get("/api/games/nonexistent")
    assert resp.status_code == 404


def test_evaluation_results_empty(client):
    resp = client.get("/api/evaluation/results")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_evaluation_run_validation(client):
    """bot_level and n_games are validated."""
    resp = client.post(
        "/api/evaluation/run",
        json={"model_path": "test.zip", "bot_level": 99},
    )
    assert resp.status_code == 422

    resp2 = client.post(
        "/api/evaluation/run",
        json={"model_path": "test.zip", "n_games": 0},
    )
    assert resp2.status_code == 422


def test_replays_list_empty(client):
    """Replay list returns empty when no replays exist."""
    resp = client.get("/api/replays")
    assert resp.status_code == 200
    assert resp.json()["replays"] == []
