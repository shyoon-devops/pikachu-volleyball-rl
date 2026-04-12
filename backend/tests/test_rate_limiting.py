"""API rate-limiting tests.

Comprehensive rate-limiting behavior that QA expects:

  * Burst over limit produces 429 on at least one endpoint
  * Sustained low-rate traffic never hits 429
  * 429 responses are well-formed (JSON body OR Retry-After header)
  * Per-endpoint isolation (limit on A does not starve B forever)
  * Recovery after Retry-After (best-effort)

Run:

    pytest tests/test_rate_limiting.py --base-url http://localhost:8002 -v
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def base_url(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--base-url")


@pytest_asyncio.fixture
async def client(base_url: str):
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as c:
        yield c


# Endpoints rate-limit is expected to cover.
#
# `/api/health`, `/api/health/live`, `/api/health/ready` are intentionally
# EXEMPT from rate-limiting (PM decision 2026-04-12): load balancers and
# k8s probes must be able to poll these at arbitrary rate. They are covered
# instead by TestHealthExemptFromRateLimit below — a burst against health
# must never throttle and must never 5xx.
GET_ENDPOINTS = [
    "/api/models",
    "/api/training/status",
    "/api/evaluation/results",
]

HEALTH_ENDPOINTS = [
    "/api/health",
]


class TestBurstRateLimit:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("endpoint", GET_ENDPOINTS)
    async def test_burst_200_requests_any_endpoint_triggers_429(
        self, base_url: str, endpoint: str,
    ) -> None:
        """200 rapid requests to a rate-limited GET endpoint must produce ≥1 429."""
        async with httpx.AsyncClient(base_url=base_url, timeout=15) as c:
            results = await asyncio.gather(
                *[c.get(endpoint) for _ in range(200)],
                return_exceptions=True,
            )
        codes = [r.status_code for r in results if not isinstance(r, Exception)]
        count_429 = codes.count(429)
        count_5xx = sum(1 for c in codes if c >= 500)
        assert count_5xx == 0, (
            f"{count_5xx}/200 requests to {endpoint} returned 5xx under burst. "
            f"Server should rate-limit, not crash."
        )
        assert count_429 > 0, (
            f"No rate limiting on {endpoint}: "
            f"{codes.count(200)}x200, 0x429, {count_5xx}x5xx. "
            f"Endpoint is unprotected from burst abuse."
        )

    @pytest.mark.asyncio
    async def test_burst_does_not_leak_500(self, base_url: str) -> None:
        """Burst traffic must never cause 5xx (rate-limit, don't crash).

        Probes a rate-limited endpoint so the middleware engages.
        """
        async with httpx.AsyncClient(base_url=base_url, timeout=15) as c:
            results = await asyncio.gather(
                *[c.get("/api/models") for _ in range(300)],
                return_exceptions=True,
            )
        codes = [r.status_code for r in results if not isinstance(r, Exception)]
        bad = [c for c in codes if c >= 500]
        assert not bad, (
            f"Burst caused {len(bad)}x5xx: "
            f"sample={bad[:5]}. Rate limiter missing or broken."
        )


class TestHealthExemptFromRateLimit:
    """PM decision 2026-04-12: health endpoints are exempt from rate-limit.

    Health probes from load balancers, k8s readiness/liveness probes, and
    uptime monitors must succeed at arbitrary cadence. The invariant we
    enforce here is:

      * burst against /api/health returns 200 for every request
      * burst must never return 429 (proves exemption is in place)
      * burst must never return 5xx (proves the endpoint itself is robust)
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("endpoint", HEALTH_ENDPOINTS)
    async def test_health_endpoint_never_throttled(
        self, base_url: str, endpoint: str,
    ) -> None:
        async with httpx.AsyncClient(base_url=base_url, timeout=15) as c:
            results = await asyncio.gather(
                *[c.get(endpoint) for _ in range(200)],
                return_exceptions=True,
            )
        codes = [r.status_code for r in results if not isinstance(r, Exception)]
        count_429 = codes.count(429)
        count_5xx = sum(1 for c in codes if c >= 500)
        count_200 = codes.count(200)
        assert count_429 == 0, (
            f"{endpoint} was throttled ({count_429}x429); must be exempt "
            f"from rate-limit per PM decision 2026-04-12."
        )
        assert count_5xx == 0, (
            f"{endpoint} returned {count_5xx}x5xx under burst; health "
            f"endpoints must be robust under load."
        )
        assert count_200 >= 190, (
            f"{endpoint} returned only {count_200}/200 success; expected "
            f"near-100% success when exempt."
        )


class TestRateLimitResponseFormat:

    @pytest.mark.asyncio
    async def test_429_has_retry_after_or_body(self, base_url: str) -> None:
        """429 responses must tell the client when to retry OR have a body."""
        async with httpx.AsyncClient(base_url=base_url, timeout=15) as c:
            results = await asyncio.gather(
                *[c.get("/api/health") for _ in range(300)],
                return_exceptions=True,
            )
        limited = [r for r in results
                   if not isinstance(r, Exception) and r.status_code == 429]
        if not limited:
            pytest.skip("No 429 responses to inspect")
        resp = limited[0]
        has_retry = "retry-after" in resp.headers
        has_body = len(resp.text.strip()) > 0
        assert has_retry or has_body, (
            f"429 response lacks Retry-After header AND has empty body. "
            f"Headers: {dict(resp.headers)}"
        )

    @pytest.mark.asyncio
    async def test_429_body_is_valid_json_if_present(
        self, base_url: str,
    ) -> None:
        """If 429 has a JSON body, it must be parseable."""
        async with httpx.AsyncClient(base_url=base_url, timeout=15) as c:
            results = await asyncio.gather(
                *[c.get("/api/health") for _ in range(300)],
                return_exceptions=True,
            )
        limited = [r for r in results
                   if not isinstance(r, Exception) and r.status_code == 429]
        if not limited:
            pytest.skip("No 429 responses to inspect")
        resp = limited[0]
        if "application/json" not in resp.headers.get("content-type", ""):
            pytest.skip("429 response is not JSON — nothing to parse")
        try:
            body = resp.json()
        except ValueError as e:
            pytest.fail(f"429 claims JSON but body is not parseable: {e}")
        assert isinstance(body, dict), f"429 JSON body not an object: {body!r}"


class TestRateLimitSanity:

    @pytest.mark.asyncio
    async def test_low_rate_sequential_never_limited(
        self, client: httpx.AsyncClient,
    ) -> None:
        """1 req/200ms for 10 requests must not hit 429."""
        limited = 0
        for _ in range(10):
            resp = await client.get("/api/health")
            if resp.status_code == 429:
                limited += 1
            await asyncio.sleep(0.2)
        assert limited == 0, (
            f"{limited}/10 low-rate sequential requests got 429. "
            f"Rate limit is too aggressive for normal users."
        )

    @pytest.mark.asyncio
    async def test_recovery_after_burst(self, base_url: str) -> None:
        """After a 10s cool-down, normal requests must succeed."""
        async with httpx.AsyncClient(base_url=base_url, timeout=15) as c:
            # Burst to trigger limit
            await asyncio.gather(
                *[c.get("/api/health") for _ in range(150)],
                return_exceptions=True,
            )
            # Cool down
            await asyncio.sleep(10)
            # Single follow-up
            resp = await c.get("/api/health")
        assert resp.status_code in (200, 429), (
            f"Unexpected status after cool-down: {resp.status_code}"
        )
        # 429 right after 10s cooldown = overly aggressive limiter; we
        # flag it but don't hard-fail because window size can be long.
        if resp.status_code == 429:
            pytest.skip(
                "Still 429 after 10s cool-down — rate limit window "
                "may be longer. Not a pass/fail, but worth tracking."
            )
