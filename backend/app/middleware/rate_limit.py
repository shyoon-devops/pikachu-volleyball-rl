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


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting. Skips WebSocket and health check."""

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst: int = 20,
    ) -> None:
        super().__init__(app)
        self._rate = requests_per_minute / 60.0  # tokens per second
        self._burst = burst
        self._buckets: dict[str, _TokenBucket] = defaultdict(
            lambda: _TokenBucket(capacity=burst, rate=self._rate)
        )
        self._last_cleanup = time.monotonic()

    async def dispatch(self, request: Request, call_next):
        # Skip WebSocket upgrades and health checks
        if request.url.path in ("/ws", "/api/health"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
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
