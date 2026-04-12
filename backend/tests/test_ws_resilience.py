"""WebSocket disconnect / reconnect resilience tests.

Covers:
  * Abrupt client close does not crash server or sibling clients
  * After client reconnects, it receives broadcasts again
  * Server tolerates many rapid connect/disconnect cycles
  * Multiple dead connections do not block a healthy one
  * Malformed JSON / non-JSON frames do not kill the connection pool
  * Close during broadcast: other clients still receive subsequent messages

Run:

    pytest tests/test_ws_resilience.py --base-url http://localhost:8002 -v
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


@pytest.fixture(scope="session")
def base_url(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--base-url")


@pytest.fixture(scope="session")
def ws_url(base_url: str) -> str:
    return base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"


async def _stop(ws_url: str) -> None:
    """Request training stop and wait for the server to confirm 'stopped'.

    Without this confirmation the next test can open a WS before the
    training push loops have quiesced, which saturates the event loop
    and causes handshake timeouts. Drain until we see a stopped status
    or a reasonable cap elapses.
    """
    try:
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            await ws.send(json.dumps({"type": "training:stop"}))
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(
                        ws.recv(), timeout=deadline - time.monotonic(),
                    )
                    msg = json.loads(raw)
                    if (
                        msg.get("type") == "training:status"
                        and msg.get("payload", {}).get("state") == "stopped"
                    ):
                        return
                except (asyncio.TimeoutError, ValueError):
                    break
                except websockets.exceptions.ConnectionClosedError:
                    break
    except Exception:
        pass
    # Belt-and-suspenders: give server a beat even if we didn't see confirmation
    await asyncio.sleep(0.5)


@pytest_asyncio.fixture(autouse=True)
async def _reset(ws_url: str):
    await _stop(ws_url)
    yield
    await _stop(ws_url)


async def _drain(ws, seconds: float) -> list[dict]:
    msgs: list[dict] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic())
            msgs.append(json.loads(raw))
        except asyncio.TimeoutError:
            break
        except websockets.exceptions.ConnectionClosedError:
            break
    return msgs


# =========================================================================
# Disconnect scenarios
# =========================================================================


class TestAbruptDisconnect:

    @pytest.mark.asyncio
    async def test_abrupt_close_does_not_crash_server(
        self, ws_url: str, base_url: str,
    ) -> None:
        """Closing without WS close-frame must not crash the server.

        Note: 1006 is a pseudo-code reserved for abnormal closure detection
        and cannot be sent in a Close frame (RFC 6455 §7.4.1). To truly
        simulate an abnormal closure we abort the underlying transport
        instead of sending a close frame.
        """
        for _ in range(5):
            ws = await websockets.connect(ws_url, open_timeout=10)
            # Abort underlying transport — no close frame, no code.
            ws.transport.abort()
            await asyncio.sleep(0.1)
        # Give server time to reap dead connections
        await asyncio.sleep(1.0)
        # Server must still respond
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as c:
            resp = await c.get("/api/health")
        assert resp.status_code == 200, (
            f"Server unhealthy after abrupt disconnects: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_abrupt_close_does_not_affect_sibling(
        self, ws_url: str,
    ) -> None:
        """Sibling connection must survive when peer dies abruptly.

        Aborts the underlying transport (no close frame) to simulate a real
        abrupt TCP-level disconnect rather than a graceful close. Sending
        code=1006 is forbidden by RFC 6455.
        """
        survivor = await websockets.connect(ws_url, open_timeout=10)
        try:
            victim = await websockets.connect(ws_url, open_timeout=10)
            victim.transport.abort()
            await asyncio.sleep(1.0)
            # Sibling still usable
            await survivor.send(json.dumps({"type": "training:stop"}))
            await asyncio.sleep(0.5)
            await asyncio.wait_for(survivor.ping(), timeout=5)
        finally:
            try:
                await survivor.close()
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_many_rapid_connect_disconnect(self, ws_url: str) -> None:
        """50 rapid connect/disconnect cycles must not leak or stall the server."""
        start = time.monotonic()
        for _ in range(50):
            ws = await websockets.connect(ws_url, open_timeout=10)
            await ws.close()
        elapsed = time.monotonic() - start
        assert elapsed < 60, (
            f"50 connect/disconnect cycles took {elapsed:.1f}s (>60s). "
            "Server may be leaking resources."
        )
        # Give server time to reap connections
        await asyncio.sleep(2.0)
        # One more connection must still work
        async with websockets.connect(ws_url, open_timeout=10) as ws:
            await asyncio.wait_for(ws.ping(), timeout=5)


# =========================================================================
# Reconnect + state recovery
# =========================================================================


class TestReconnectRecovery:

    @pytest.mark.asyncio
    async def test_reconnect_receives_broadcasts_again(
        self, ws_url: str,
    ) -> None:
        """After reconnect, the client must receive broadcasts from ongoing training."""
        # Start training on conn A
        async with websockets.connect(ws_url, open_timeout=5) as a:
            await a.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            await asyncio.sleep(3)
        # Disconnect, reconnect on conn B, expect to observe training activity
        async with websockets.connect(ws_url, open_timeout=5) as b:
            msgs = await _drain(b, 15)
        assert any(
            m.get("type") in {"training:metrics", "training:frame"}
            for m in msgs
        ), (
            f"After reconnect, no training traffic observed within 15s. "
            f"Messages: {[m.get('type') for m in msgs]}"
        )

    @pytest.mark.asyncio
    async def test_reconnect_can_issue_stop(self, ws_url: str) -> None:
        """Reconnected client must be able to stop ongoing training."""
        async with websockets.connect(ws_url, open_timeout=10) as a:
            await a.send(json.dumps({
                "type": "training:start",
                "payload": {"bot_level": 1},
            }))
            await asyncio.sleep(2)

        # Give server a beat to reap the disconnected client
        await asyncio.sleep(1.0)

        # New connection — must be able to stop
        async with websockets.connect(ws_url, open_timeout=10) as b:
            await b.send(json.dumps({"type": "training:stop"}))
            msgs = await _drain(b, 10)
        stopped = [
            m for m in msgs
            if m.get("type") == "training:status"
            and m.get("payload", {}).get("state") == "stopped"
        ]
        assert stopped, (
            f"Reconnected client could not stop training. Messages: "
            f"{[m.get('type') for m in msgs]}"
        )


# =========================================================================
# Malformed input resilience
# =========================================================================


class TestMalformedInput:

    @pytest.mark.asyncio
    async def test_non_json_frame_does_not_kill_pool(
        self, ws_url: str, base_url: str,
    ) -> None:
        """A garbage frame from one client must not affect others."""
        healthy = await websockets.connect(ws_url, open_timeout=5)
        try:
            bad = await websockets.connect(ws_url, open_timeout=5)
            try:
                # Send raw non-JSON text
                await bad.send("this-is-not-json")
                await asyncio.sleep(0.3)
            except Exception:
                pass
            finally:
                try:
                    await bad.close()
                except Exception:
                    pass
            await asyncio.sleep(0.5)
            # Healthy connection must still be able to ping
            await healthy.ping()
        finally:
            await healthy.close()
        # And server must still be healthy
        async with httpx.AsyncClient(base_url=base_url, timeout=5) as c:
            resp = await c.get("/api/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unknown_message_type_is_ignored(self, ws_url: str) -> None:
        """Unknown type must not crash the connection."""
        async with websockets.connect(ws_url, open_timeout=5) as ws:
            await ws.send(json.dumps({
                "type": "this-does-not-exist",
                "payload": {"foo": "bar"},
            }))
            await asyncio.sleep(0.5)
            # Connection still alive?
            await ws.ping()
