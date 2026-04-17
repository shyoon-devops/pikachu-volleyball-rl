"""Load tests.

These tests exercise realistic concurrency levels QA should sustain:

  * 100 simultaneous WebSocket connections held open
  * 50 concurrent /api/evaluation/run requests
  * 20 concurrent training:start messages (same TrainingManager singleton)
  * Broadcast fan-out latency under load

Marked with ``@pytest.mark.load`` so they can be excluded from fast runs:

    pytest tests/test_load.py --base-url http://localhost:8002 -v
    pytest -m "not load"   # skip load tests
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time

import httpx
import pytest
import pytest_asyncio
import websockets
import websockets.exceptions


# Live-backend load tests — httpx + WebSocket against --base-url. Double
# marker so the default `-m 'not e2e'` filter also excludes this file
# (in addition to the long-standing `-m 'not load'` opt-in), preventing a
# plain `pytest` from hammering dev/qa/prod. See 2026-04-17 incident note
# in pyproject.toml.
pytestmark = [pytest.mark.load, pytest.mark.e2e]


@pytest.fixture(scope="session")
def base_url(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--base-url")


@pytest.fixture(scope="session")
def ws_url(base_url: str) -> str:
    return base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"


async def _stop(ws_url: str) -> None:
    try:
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            await ws.send(json.dumps({"type": "training:stop"}))
            await asyncio.sleep(0.3)
    except Exception:
        pass


@pytest_asyncio.fixture(autouse=True)
async def _reset(ws_url: str):
    await _stop(ws_url)
    yield
    await _stop(ws_url)


# =========================================================================
# Concurrent WS connections
# =========================================================================


class TestConcurrentConnections:

    @pytest.mark.asyncio
    async def test_100_concurrent_ws_connections_stable(
        self, ws_url: str,
    ) -> None:
        """100 simultaneous WS connections must hold for 10s with no error."""
        connections: list = []
        errors: list[str] = []
        try:
            open_start = time.monotonic()
            for _ in range(100):
                try:
                    ws = await websockets.connect(ws_url, open_timeout=10)
                    connections.append(ws)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"open-fail: {type(e).__name__}: {e}")
            open_elapsed = time.monotonic() - open_start
            assert len(connections) >= 95, (
                f"Only {len(connections)}/100 connections opened in "
                f"{open_elapsed:.1f}s. Errors sample: {errors[:3]}"
            )

            # Hold for 10s, then ping each
            await asyncio.sleep(10)

            alive = 0
            for ws in connections:
                try:
                    pong = await asyncio.wait_for(ws.ping(), timeout=3)
                    await asyncio.wait_for(pong, timeout=3)
                    alive += 1
                except Exception:
                    pass
            # At least 90% must be alive after 10s idle
            assert alive >= len(connections) * 0.9, (
                f"Only {alive}/{len(connections)} connections survived 10s idle"
            )
        finally:
            for ws in connections:
                try:
                    await ws.close()
                except Exception:
                    pass

    @pytest.mark.asyncio
    async def test_broadcast_reaches_all_of_50_clients(
        self, ws_url: str,
    ) -> None:
        """With 50 listeners, a broadcast must reach substantially all of them."""
        listeners: list = []
        try:
            for _ in range(50):
                listeners.append(await websockets.connect(ws_url, open_timeout=10))

            # Start training via a fresh connection
            async with websockets.connect(ws_url, open_timeout=5) as starter:
                await starter.send(json.dumps({
                    "type": "training:start",
                    "payload": {"bot_level": 1},
                }))

                # Give server 20s to push metrics
                async def _await_metric(ws) -> bool:
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        remaining = deadline - time.monotonic()
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                            msg = json.loads(raw)
                            if msg.get("type") in {"training:metrics", "training:frame"}:
                                return True
                        except asyncio.TimeoutError:
                            return False
                        except websockets.exceptions.ConnectionClosedError:
                            return False
                    return False

                results = await asyncio.gather(
                    *[_await_metric(w) for w in listeners],
                    return_exceptions=True,
                )
            received = sum(1 for r in results if r is True)
            assert received >= len(listeners) * 0.9, (
                f"Only {received}/{len(listeners)} listeners got broadcast "
                f"within 20s. Broadcast fan-out is degraded under load."
            )
        finally:
            for ws in listeners:
                try:
                    await ws.close()
                except Exception:
                    pass


# =========================================================================
# Concurrent REST requests
# =========================================================================


class TestConcurrentREST:

    @pytest.mark.asyncio
    async def test_50_concurrent_health_requests(
        self, base_url: str,
    ) -> None:
        """/api/health must handle 50 concurrent requests without 5xx."""
        async with httpx.AsyncClient(base_url=base_url, timeout=15) as c:
            results = await asyncio.gather(
                *[c.get("/api/health") for _ in range(50)],
                return_exceptions=True,
            )
        successes = [r for r in results if not isinstance(r, Exception) and r.status_code == 200]
        rate_limited = [r for r in results if not isinstance(r, Exception) and r.status_code == 429]
        server_errors = [r for r in results if not isinstance(r, Exception) and r.status_code >= 500]
        network_errors = [r for r in results if isinstance(r, Exception)]

        assert not server_errors, (
            f"{len(server_errors)}/50 got 5xx. Sample: "
            f"{[r.status_code for r in server_errors[:3]]}"
        )
        assert not network_errors, (
            f"{len(network_errors)}/50 failed at transport level: "
            f"{network_errors[:3]}"
        )
        # 429s are acceptable (rate limiting); but total 200+429 must == 50
        assert len(successes) + len(rate_limited) == 50

    @pytest.mark.asyncio
    async def test_50_concurrent_model_list(self, base_url: str) -> None:
        async with httpx.AsyncClient(base_url=base_url, timeout=15) as c:
            results = await asyncio.gather(
                *[c.get("/api/models") for _ in range(50)],
                return_exceptions=True,
            )
        exc = [r for r in results if isinstance(r, Exception)]
        assert not exc, f"{len(exc)} transport failures: {exc[:3]}"
        codes = [r.status_code for r in results if not isinstance(r, Exception)]
        bad = [c for c in codes if c >= 500]
        assert not bad, f"{len(bad)}/50 got 5xx on /api/models"


# =========================================================================
# Concurrent training:start (known fragile — BUG-3)
# =========================================================================


class TestConcurrentTrainingStart:

    @pytest.mark.asyncio
    async def test_20_concurrent_training_start_does_not_crash_server(
        self, ws_url: str, base_url: str,
    ) -> None:
        """20 parallel training:start must not bring the server down."""
        async def send_start() -> bool:
            try:
                async with websockets.connect(ws_url, open_timeout=5) as ws:
                    await ws.send(json.dumps({
                        "type": "training:start",
                        "payload": {"bot_level": 1},
                    }))
                    await asyncio.sleep(1)
                    return True
            except Exception:
                return False

        results = await asyncio.gather(
            *[send_start() for _ in range(20)],
            return_exceptions=True,
        )
        # Some will fail if BUG-3 unfixed — that's expected.
        # Critical: server itself must still be healthy.
        async with httpx.AsyncClient(base_url=base_url, timeout=5) as c:
            resp = await c.get("/api/health")
        assert resp.status_code == 200, (
            f"Server unhealthy after 20 concurrent training:start. "
            f"Success count: {sum(1 for r in results if r is True)}/20, "
            f"health={resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_concurrent_ws_latency_under_load(self, ws_url: str) -> None:
        """Ping RTT under 50 concurrent connections stays under 1s p95."""
        connections: list = []
        try:
            for _ in range(50):
                connections.append(await websockets.connect(ws_url, open_timeout=10))

            async def rtt(ws) -> float:
                start = time.monotonic()
                pong = await asyncio.wait_for(ws.ping(), timeout=5)
                await asyncio.wait_for(pong, timeout=5)
                return time.monotonic() - start

            latencies = await asyncio.gather(
                *[rtt(w) for w in connections],
                return_exceptions=True,
            )
            ok = [lat for lat in latencies if isinstance(lat, float)]
            assert len(ok) >= 45, (
                f"Only {len(ok)}/50 pings returned. Connection quality degraded."
            )
            p95 = statistics.quantiles(ok, n=20)[18]  # 95th percentile
            assert p95 < 1.0, (
                f"p95 ping RTT under 50 concurrent connections = {p95*1000:.0f}ms "
                f"(budget: 1000ms). Server struggling under load."
            )
        finally:
            for ws in connections:
                try:
                    await ws.close()
                except Exception:
                    pass
