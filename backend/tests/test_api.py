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
