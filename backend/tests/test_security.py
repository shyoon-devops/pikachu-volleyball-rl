"""Security tests for SEC-1, SEC-2, SEC-3."""

import pytest


class TestPathTraversal:
    """SEC-1: Path traversal prevention."""

    def test_replay_path_traversal_dot_dot(self, client):
        resp = client.get("/api/replays/../../etc/passwd")
        assert resp.status_code == 404

    def test_replay_path_traversal_slash(self, client):
        resp = client.get("/api/replays/foo/bar")
        assert resp.status_code == 404

    def test_game_invalid_id(self, client):
        resp = client.get("/api/games/not-a-valid-objectid")
        assert resp.status_code == 404

    def test_eval_path_traversal(self, client):
        resp = client.post(
            "/api/evaluation/run",
            json={"model_path": "../../etc/passwd", "bot_level": 1},
        )
        assert resp.status_code == 404
        assert "Invalid model path" in resp.json()["detail"]


class TestCorsConfig:
    """SEC-2: CORS is not wildcard by default."""

    def test_cors_rejects_unknown_origin(self, client):
        resp = client.options(
            "/api/health",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Should NOT include Access-Control-Allow-Origin for unknown origin
        assert resp.headers.get("access-control-allow-origin") != "*"

    def test_cors_allows_configured_origin(self, client):
        resp = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


class TestRateLimit:
    """SEC-3: Rate limiting on API endpoints."""

    def test_health_exempt_from_rate_limit(self, client):
        """Health check should not be rate limited."""
        for _ in range(30):
            resp = client.get("/api/health")
            assert resp.status_code == 200

    def test_rate_limit_triggers(self, client):
        """Exceeding burst limit returns 429."""
        statuses = []
        for _ in range(25):
            resp = client.get("/api/games")
            statuses.append(resp.status_code)
        assert 429 in statuses, f"Expected 429 in statuses but got: {set(statuses)}"

    def test_rate_limit_response_format(self, client):
        """429 response includes Retry-After header."""
        for _ in range(25):
            resp = client.get("/api/games")
            if resp.status_code == 429:
                assert "Retry-After" in resp.headers
                assert resp.json()["detail"] == "Too many requests"
                return
        pytest.skip("Rate limit not triggered within 25 requests")
