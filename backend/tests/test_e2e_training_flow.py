"""End-to-end training lifecycle tests.

Covers the full training flow against a running environment:

  1. training:start → training:status (running) + experiment_id
  2. training:metrics pushed within reasonable time
  3. training:set_level mid-run
  4. training:stop → training:status (stopped)
  5. training:resume → running again
  6. /api/training/status REST reflects WS state

Run against QA:

    pytest tests/test_e2e_training_flow.py --base-url http://localhost:8002 -v
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
import pytest_asyncio
import websockets
import websockets.exceptions

# Every test in this module talks to a live backend (httpx + WebSocket)
# and mutates training state. Module-level marker keeps the default
# `-m 'not e2e'` addopts filter excluding the whole file. See the
# 2026-04-17 incident note in pyproject.toml.
pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session")
def base_url(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--base-url")


@pytest.fixture(scope="session")
def ws_url(base_url: str) -> str:
    return base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"


@pytest_asyncio.fixture
async def client(base_url: str):
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as c:
        yield c


async def _stop_via_ws(ws_url: str) -> None:
    """Best-effort stop to reset state between tests."""
    try:
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            await ws.send(json.dumps({"type": "training:stop"}))
            await asyncio.sleep(0.5)
    except Exception:
        pass


async def _collect_until(
    ws: websockets.WebSocketClientProtocol,
    predicate,
    timeout: float,
) -> tuple[list[dict], dict | None]:
    """Collect messages until *predicate(msg)* is True or timeout hits."""
    collected: list[dict] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            msg = json.loads(raw)
            collected.append(msg)
            if predicate(msg):
                return collected, msg
        except asyncio.TimeoutError:
            break
        except websockets.exceptions.ConnectionClosedError:
            break
    return collected, None


@pytest_asyncio.fixture(autouse=True)
async def _reset_training(ws_url: str):
    await _stop_via_ws(ws_url)
    await asyncio.sleep(0.3)
    yield
    await _stop_via_ws(ws_url)
    await asyncio.sleep(0.3)


# =========================================================================
# Training lifecycle
# =========================================================================


class TestTrainingLifecycle:

    @pytest.mark.asyncio
    async def test_start_returns_running_status_with_experiment_id(
        self, ws_url: str,
    ) -> None:
        # Widened from 5s → 15s: under a loaded QA instance after many prior
        # tests, training thread spin-up + first broadcast can cross a 5s
        # boundary. 15s is still tight enough to catch real stalls.
        async with websockets.connect(ws_url, open_timeout=10) as ws:
            await ws.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            _, msg = await _collect_until(
                ws,
                lambda m: m.get("type") == "training:status"
                and m.get("payload", {}).get("state") == "running",
                timeout=15,
            )
        assert msg is not None, (
            "No training:status(running) received within 15s after start"
        )
        payload = msg["payload"]
        assert payload.get("state") == "running"
        exp_id = payload.get("experiment_id")
        assert exp_id, f"experiment_id missing from payload: {payload}"
        assert isinstance(exp_id, str) and len(exp_id) >= 8

    @pytest.mark.asyncio
    async def test_metrics_stream_within_20s_of_start(self, ws_url: str) -> None:
        """Training must produce at least one training:metrics within 20s."""
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            await ws.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            _, metric_msg = await _collect_until(
                ws,
                lambda m: m.get("type") == "training:metrics",
                timeout=20,
            )
        assert metric_msg is not None, (
            "No training:metrics emitted within 20s — trainer is stalled or "
            "the metrics push loop is not running."
        )
        # Payload sanity check
        payload = metric_msg.get("payload") or {}
        assert isinstance(payload, dict), f"metrics payload not dict: {payload}"

    @pytest.mark.asyncio
    async def test_stop_returns_stopped_status(self, ws_url: str) -> None:
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            await ws.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            await asyncio.sleep(2)
            await ws.send(json.dumps({"type": "training:stop"}))
            _, msg = await _collect_until(
                ws,
                lambda m: m.get("type") == "training:status"
                and m.get("payload", {}).get("state") == "stopped",
                timeout=10,
            )
        assert msg is not None, (
            "No training:status(stopped) within 10s after training:stop"
        )

    @pytest.mark.asyncio
    async def test_rest_status_matches_ws_state(
        self, ws_url: str, client: httpx.AsyncClient,
    ) -> None:
        """REST /api/training/status must reflect running state after WS start."""
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            await ws.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            await asyncio.sleep(2)
            resp = await client.get("/api/training/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("state") == "running", (
            f"REST training status mismatch. Expected 'running', got {body}"
        )

    @pytest.mark.asyncio
    async def test_set_level_reflects_in_status(self, ws_url: str) -> None:
        """Mid-run set_level must mutate state and be echoed back."""
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            await ws.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            await asyncio.sleep(1.5)
            await ws.send(json.dumps({
                "type": "training:set_level",
                "payload": {"level": 4},
            }))
            _, msg = await _collect_until(
                ws,
                lambda m: m.get("type") == "training:status"
                and m.get("payload", {}).get("bot_level") == 4,
                timeout=5,
            )
        assert msg is not None, (
            "set_level(4) did not produce a training:status with bot_level=4"
        )

    @pytest.mark.asyncio
    async def test_stop_then_resume(self, ws_url: str) -> None:
        """Stop must fully halt; resume must return state to running.

        Timeouts widened (5s → 15s) because this test runs late in the suite
        after the rate-limit / broadcast-storm tests, by which time the QA
        server's event loop is under GC pressure and a resume handshake can
        cross the tighter boundary. 15s still catches real stalls.
        """
        async with websockets.connect(ws_url, open_timeout=10) as ws:
            await ws.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            await asyncio.sleep(2)
            await ws.send(json.dumps({"type": "training:stop"}))
            await _collect_until(
                ws,
                lambda m: m.get("payload", {}).get("state") == "stopped",
                timeout=10,
            )
            await asyncio.sleep(0.5)
            await ws.send(json.dumps({"type": "training:resume"}))
            _, resumed = await _collect_until(
                ws,
                lambda m: m.get("type") == "training:status"
                and m.get("payload", {}).get("state") == "running",
                timeout=15,
            )
        assert resumed is not None, (
            "training:resume did not produce running status within 15s"
        )

    @pytest.mark.asyncio
    async def test_broadcast_reaches_second_client(self, ws_url: str) -> None:
        """Starting from client A must push metrics to client B."""
        async with websockets.connect(ws_url, open_timeout=5) as a, \
                   websockets.connect(ws_url, open_timeout=5) as b:
            await a.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            _, seen_on_b = await _collect_until(
                b,
                lambda m: m.get("type") in {"training:metrics", "training:status"},
                timeout=20,
            )
        assert seen_on_b is not None, (
            "Client B received no broadcast from A's training:start"
        )
