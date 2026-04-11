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
    body = resp.json()
    assert body["replays"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["limit"] == 20


def test_replays_list_pagination(client):
    """Replay list supports page/limit query params."""
    resp = client.get("/api/replays?page=2&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 2
    assert body["limit"] == 5


def test_game_record_has_game_id(client):
    """GameRecord schema includes uuid4 game_id field."""
    from backend.app.models.schemas import GameRecord

    record = GameRecord(
        experiment_id="exp-1",
        bot_level=1,
        score1=15,
        score2=10,
        winner=1,
        duration_frames=300,
        rally_count=5,
    )
    assert record.game_id  # auto-generated uuid4
    assert len(record.game_id) == 36  # uuid4 format: 8-4-4-4-12


def test_game_record_preserves_game_id(client):
    """GameRecord preserves explicitly provided game_id."""
    from backend.app.models.schemas import GameRecord

    record = GameRecord(
        game_id="custom-id-123",
        experiment_id="exp-1",
        bot_level=1,
        score1=15,
        score2=10,
        winner=1,
        duration_frames=300,
        rally_count=5,
    )
    assert record.game_id == "custom-id-123"
