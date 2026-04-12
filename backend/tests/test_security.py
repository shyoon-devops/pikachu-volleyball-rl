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


class TestRateLimitExemptions:
    """Infrastructure paths (probes, metrics) must never be throttled.

    These endpoints are hit by k8s probes, Prometheus scrapes, and Promtail —
    429-ing them causes cascading unhealthy states across the cluster. The
    tests first exhaust the per-IP token bucket with regular requests, then
    verify the exempt paths still respond 200.
    """

    @staticmethod
    def _exhaust_bucket(client) -> None:
        """Consume all tokens on the shared bucket until 429 is observed."""
        seen_429 = False
        for _ in range(50):
            if client.get("/api/games").status_code == 429:
                seen_429 = True
                break
        assert seen_429, "precondition failed: bucket never drained — test is inert"

    def test_health_live_exempt_under_throttle(self, client):
        self._exhaust_bucket(client)
        for _ in range(10):
            resp = client.get("/api/health/live")
            assert resp.status_code == 200, f"/api/health/live got {resp.status_code}"

    def test_health_ready_exempt_under_throttle(self, client):
        self._exhaust_bucket(client)
        for _ in range(10):
            resp = client.get("/api/health/ready")
            # 200 (all ok) or 503 (subsystem degraded) both mean "not throttled".
            assert resp.status_code in (200, 503)

    def test_health_root_exempt_under_throttle(self, client):
        self._exhaust_bucket(client)
        for _ in range(10):
            resp = client.get("/api/health")
            assert resp.status_code in (200, 503)

    def test_api_metrics_exempt_under_throttle(self, client):
        """Custom /api/metrics (Prometheus text format) must bypass the limiter."""
        self._exhaust_bucket(client)
        for _ in range(10):
            resp = client.get("/api/metrics")
            assert resp.status_code == 200
            assert "text/plain" in resp.headers.get("content-type", "")

    def test_instrumentator_metrics_exempt_under_throttle(self, client):
        """HTTP-level /metrics from prometheus-fastapi-instrumentator must bypass too."""
        self._exhaust_bucket(client)
        resp = client.get("/metrics")
        # The instrumentator serves Prometheus text; any non-429 proves exemption
        # is in effect (status 200 expected when instrumentator is mounted).
        assert resp.status_code != 429
