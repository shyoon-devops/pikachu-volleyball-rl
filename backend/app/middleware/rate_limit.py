"""Simple in-memory rate limiting middleware using token bucket algorithm."""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class _TokenBucket:
    __slots__ = ("capacity", "rate", "tokens", "last_refill")

    def __init__(self, capacity: int, rate: float) -> None:
        self.capacity = capacity
        self.rate = rate  # tokens per second
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


# Paths that must never be rate-limited. Health probes and metrics scrapes
# come from infrastructure (k8s, Prometheus, Promtail, Loki); throttling them
# causes cascading failures — a busy node gets marked unhealthy and pulled
# from rotation, which makes the remaining nodes even busier. Explicit exact
# matches plus a prefix list so we cover ``/api/health/live``,
# ``/api/health/ready``, and any future probe endpoints.
_EXEMPT_EXACT: frozenset[str] = frozenset(
    {
        "/ws",
        "/api/health",
        "/api/metrics",  # custom app-level Prometheus endpoint
        "/metrics",  # prometheus-fastapi-instrumentator HTTP-level metrics
    }
)
_EXEMPT_PREFIX: tuple[str, ...] = ("/api/health/",)


def _is_exempt(path: str) -> bool:
    if path in _EXEMPT_EXACT:
        return True
    return any(path.startswith(p) for p in _EXEMPT_PREFIX)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting. Skips WebSocket, health probes, and metrics scrapes."""

    def __init__(
        self,
        app,
        requests_per_minute: int = 600,
        burst: int = 200,
        *,
        trust_proxy: bool = False,
    ) -> None:
        super().__init__(app)
        self._rate = requests_per_minute / 60.0  # tokens per second
        self._burst = burst
        self._buckets: dict[str, _TokenBucket] = defaultdict(
            lambda: _TokenBucket(capacity=burst, rate=self._rate)
        )
        self._last_cleanup = time.monotonic()
        # Behind nginx (or any reverse proxy) every request reaches uvicorn
        # from the proxy IP, so without ``trust_proxy`` every real user
        # collapses into a single shared bucket and 429s start firing the
        # moment two tabs sync. When this flag is on, the first hop in
        # ``X-Forwarded-For`` is treated as the real client IP. MUST stay
        # off for direct-internet deploys — XFF is trivially spoofable.
        self._trust_proxy = trust_proxy

    def _client_id(self, request: Request) -> str:
        if self._trust_proxy:
            xff = request.headers.get("x-forwarded-for")
            if xff:
                # Standard format: "client, proxy1, proxy2". First hop is
                # the originating client; later hops are intermediate proxies.
                first = xff.split(",", 1)[0].strip()
                if first:
                    return first
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        if _is_exempt(request.url.path):
            return await call_next(request)

        client_ip = self._client_id(request)
        bucket = self._buckets[client_ip]

        # Periodic cleanup of stale buckets (every 5 min)
        now = time.monotonic()
        if now - self._last_cleanup > 300:
            self._cleanup(now)
            self._last_cleanup = now

        if not bucket.consume():
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers={"Retry-After": str(int(1.0 / self._rate))},
            )

        return await call_next(request)

    def _cleanup(self, now: float) -> None:
        """Remove buckets idle for more than 10 minutes."""
        stale = [
            ip for ip, b in self._buckets.items()
            if now - b.last_refill > 600
        ]
        for ip in stale:
            del self._buckets[ip]
