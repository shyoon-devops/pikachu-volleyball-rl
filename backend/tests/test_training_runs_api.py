"""GET /api/training/runs aggregation + /api/games?title= filter (BE-T4/T5)."""

from __future__ import annotations

from datetime import datetime, timezone


def _seed_games(client, games: list[dict]) -> None:
    """Drop pre-built GameRecord dicts straight into FakeGameService."""
    svc = client.app.state.game_service
    for g in games:
        svc._games.append({"_id": str(len(svc._games)), **g})


def _iso(d):
    return d.isoformat() if isinstance(d, datetime) else d


class TestTrainingRunsEndpoint:
    def test_empty_when_no_games(self, client):
        resp = client.get("/api/training/runs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["data"] == []

    def test_groups_by_title_with_win_rate(self, client):
        _seed_games(client, [
            {
                "game_id": "g1", "experiment_id": "exp-a",
                "timestamp": datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc),
                "bot_level": 1, "score1": 15, "score2": 10, "winner": 1,
                "duration_frames": 1000, "rally_count": 20,
                "title": "run-alpha",
            },
            {
                "game_id": "g2", "experiment_id": "exp-a",
                "timestamp": datetime(2026, 4, 17, 10, 5, tzinfo=timezone.utc),
                "bot_level": 1, "score1": 10, "score2": 15, "winner": 2,
                "duration_frames": 1100, "rally_count": 30,
                "title": "run-alpha",
            },
            {
                "game_id": "g3", "experiment_id": "exp-b",
                "timestamp": datetime(2026, 4, 17, 11, 0, tzinfo=timezone.utc),
                "bot_level": 3, "score1": 15, "score2": 0, "winner": 1,
                "duration_frames": 1500, "rally_count": 50,
                "title": "run-beta",
            },
        ])
        resp = client.get("/api/training/runs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2

        # Sorted by started_at desc → run-beta first.
        titles = [row["title"] for row in body["data"]]
        assert titles == ["run-beta", "run-alpha"]

        beta = body["data"][0]
        assert beta["total_games"] == 1
        assert beta["win_rate"] == 1.0
        assert beta["avg_rally_length"] == 50.0
        assert beta["experiment_id"] == "exp-b"

        alpha = body["data"][1]
        assert alpha["total_games"] == 2
        # 1 win of 2 games.
        assert alpha["win_rate"] == 0.5
        assert alpha["avg_rally_length"] == 25.0  # (20+30)/2

    def test_legacy_games_bucket_as_untitled(self, client):
        _seed_games(client, [
            {
                "game_id": "g1", "experiment_id": "exp-legacy",
                "timestamp": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
                "bot_level": 1, "score1": 15, "score2": 10, "winner": 1,
                "duration_frames": 1000, "rally_count": 10,
                # no title
            },
        ])
        resp = client.get("/api/training/runs")
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["title"] == "untitled"
        assert body["data"][0]["status"] == "done"

    def test_pagination_caps_limit(self, client):
        # Seed 25 distinct titles.
        # Stagger timestamps by minute so the sort is deterministic
        # without running off the hour end.
        _seed_games(client, [
            {
                "game_id": f"g{i}", "experiment_id": f"exp-{i}",
                "timestamp": datetime(2026, 4, 17, 10, i, tzinfo=timezone.utc),
                "bot_level": 1, "score1": 15, "score2": 0, "winner": 1,
                "duration_frames": 1000, "rally_count": 10,
                "title": f"run-{i:02d}",
            }
            for i in range(25)
        ])
        resp = client.get("/api/training/runs?page=1&limit=10")
        body = resp.json()
        assert body["total"] == 25
        assert len(body["data"]) == 10
        # Most recent (i=24) first.
        assert body["data"][0]["title"] == "run-24"

    def test_running_status_overlay(self, client):
        # Seed one finished run.
        _seed_games(client, [
            {
                "game_id": "g1", "experiment_id": "exp-live",
                "timestamp": datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc),
                "bot_level": 1, "score1": 15, "score2": 10, "winner": 1,
                "duration_frames": 1000, "rally_count": 20,
                "title": "run-live-title",
            },
        ])
        # Mutate the training_service mock to report running with matching title.
        client.app.state.training_service.status = lambda: {
            "state": "running",
            "current_step": 100,
            "current_episode": 2,
            "experiment_id": "exp-live",
            "bot_level": 1,
            "started_at": None,
            "title": "run-live-title",
        }
        resp = client.get("/api/training/runs")
        body = resp.json()
        assert body["data"][0]["status"] == "running"


class TestGamesTitleFilter:
    def test_no_filter_returns_all(self, client):
        _seed_games(client, [
            {
                "game_id": "g1", "experiment_id": "e1",
                "timestamp": datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc),
                "bot_level": 1, "score1": 15, "score2": 0, "winner": 1,
                "duration_frames": 1, "rally_count": 1,
                "title": "run-a",
            },
            {
                "game_id": "g2", "experiment_id": "e2",
                "timestamp": datetime(2026, 4, 17, 10, 1, tzinfo=timezone.utc),
                "bot_level": 1, "score1": 15, "score2": 0, "winner": 1,
                "duration_frames": 1, "rally_count": 1,
                "title": "run-b",
            },
        ])
        resp = client.get("/api/games")
        body = resp.json()
        assert body["total"] == 2

    def test_title_filters_exact_match(self, client):
        _seed_games(client, [
            {
                "game_id": "g1", "experiment_id": "e1",
                "timestamp": datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc),
                "bot_level": 1, "score1": 15, "score2": 0, "winner": 1,
                "duration_frames": 1, "rally_count": 1,
                "title": "run-a",
            },
            {
                "game_id": "g2", "experiment_id": "e2",
                "timestamp": datetime(2026, 4, 17, 10, 1, tzinfo=timezone.utc),
                "bot_level": 1, "score1": 15, "score2": 0, "winner": 1,
                "duration_frames": 1, "rally_count": 1,
                "title": "run-b",
            },
        ])
        resp = client.get("/api/games?title=run-a")
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["game_id"] == "g1"

    def test_untitled_filter_matches_nulls(self, client):
        _seed_games(client, [
            {
                "game_id": "g1", "experiment_id": "e1",
                "timestamp": datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc),
                "bot_level": 1, "score1": 15, "score2": 0, "winner": 1,
                "duration_frames": 1, "rally_count": 1,
                # no title
            },
            {
                "game_id": "g2", "experiment_id": "e2",
                "timestamp": datetime(2026, 4, 17, 10, 1, tzinfo=timezone.utc),
                "bot_level": 1, "score1": 15, "score2": 0, "winner": 1,
                "duration_frames": 1, "rally_count": 1,
                "title": "run-b",
            },
        ])
        resp = client.get("/api/games?title=untitled")
        body = resp.json()
        assert body["total"] == 1
        assert body["data"][0]["game_id"] == "g1"
