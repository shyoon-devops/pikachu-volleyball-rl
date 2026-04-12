"""WebSocket connection manager with heartbeat and backpressure."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30  # seconds between pings
HEARTBEAT_TIMEOUT = 10  # seconds to wait for pong after ping
# Clients that miss this many consecutive pongs are considered dead.
MISSED_PONG_LIMIT = 2
# Per-client send budget for broadcasts. Slow / wedged clients cannot hold up
# the push loops; instead they are timed out and disconnected so the rest of
# the fleet continues receiving updates. 5s is generous enough for a healthy
# TCP retransmit cycle but short enough to keep the broadcast fan-out latency
# bounded at O(SEND_TIMEOUT) rather than O(N * slowest_client).
SEND_TIMEOUT = 5.0


class ConnectionManager:
    """Manages active WebSocket connections with ping/pong heartbeat."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, asyncio.Task] = {}
        # Per-connection bookkeeping for pong tracking.
        self._last_pong: dict[WebSocket, float] = {}
        self._last_ping: dict[WebSocket, float] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        now = time.monotonic()
        self._last_pong[ws] = now
        self._last_ping[ws] = now
        task = asyncio.create_task(self._heartbeat(ws))
        self._connections[ws] = task
        logger.info("WS connected — active: %d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        task = self._connections.pop(ws, None)
        self._last_pong.pop(ws, None)
        self._last_ping.pop(ws, None)
        if task:
            task.cancel()
        logger.info("WS disconnected — active: %d", len(self._connections))

    def record_pong(self, ws: WebSocket) -> None:
        """Update last-pong timestamp for a client."""
        if ws in self._connections:
            self._last_pong[ws] = time.monotonic()

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Fan out a message to every active connection in parallel.

        Three concerns drive the implementation (BE-6):

        1. **Serialize once**: ``ws.send_json`` would re-encode the payload per
           client. For a broadcast of ``N`` clients that is ``N`` redundant
           json.dumps calls. We encode once and use ``send_text`` per client.
        2. **Parallel dispatch**: a sequential loop makes total latency
           ``sum(send_time_i)``; a single slow client blocks every other client
           from receiving the message. ``asyncio.gather`` dispatches all sends
           concurrently so the loop completes in roughly ``max(send_time_i)``.
        3. **Per-client timeout**: a wedged client (unresponsive TCP) must not
           pin a push loop forever. ``asyncio.wait_for(..., SEND_TIMEOUT)``
           bounds each client's slice; offenders are disconnected so subsequent
           broadcasts don't keep paying for them.

        Dead clients — those raising on send or exceeding the timeout — are
        collected from the gather results and disconnected after the fan-out.
        Disconnecting mid-iteration would mutate ``self._connections`` while
        other coroutines hold references to it; deferring the cleanup keeps
        the concurrent sends pointing at a stable set.
        """
        clients = list(self._connections)
        if not clients:
            return

        try:
            payload = json.dumps(message, default=str)
        except (TypeError, ValueError):
            # Refuse to let a malformed broadcast poison every connection —
            # the push-loop caller should have validated, so we log loudly.
            logger.exception("broadcast payload is not JSON-serializable; dropping")
            return

        results = await asyncio.gather(
            *(self._send_one(ws, payload) for ws in clients),
            return_exceptions=False,
        )
        for ws, ok in zip(clients, results):
            if not ok:
                self.disconnect(ws)

    async def _send_one(self, ws: WebSocket, payload: str) -> bool:
        """Send a pre-serialized payload to one client with a hard timeout.

        Returns ``True`` on success, ``False`` if the client should be
        disconnected (send raised or timed out). Never re-raises — callers
        rely on the boolean to decide cleanup.
        """
        try:
            await asyncio.wait_for(ws.send_text(payload), timeout=SEND_TIMEOUT)
            return True
        except asyncio.TimeoutError:
            logger.warning("broadcast send timed out after %.1fs; disconnecting", SEND_TIMEOUT)
            return False
        except Exception:
            # send_text raises on closed/aborted sockets; treat any failure as
            # a disconnect signal rather than propagating into the push loop.
            return False

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def _heartbeat(self, ws: WebSocket) -> None:
        """Ping client periodically and close connections that miss pongs."""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                # Send ping
                try:
                    self._last_ping[ws] = time.monotonic()
                    await asyncio.wait_for(
                        ws.send_json({"type": "ping"}),
                        timeout=HEARTBEAT_TIMEOUT,
                    )
                except Exception:
                    logger.warning("Heartbeat send failed, closing connection")
                    await self._close_and_cleanup(ws)
                    return

                # Wait for pong window then check liveness
                await asyncio.sleep(HEARTBEAT_TIMEOUT)
                last_pong = self._last_pong.get(ws, 0.0)
                last_ping = self._last_ping.get(ws, 0.0)
                # Consider the client stale if it has not responded since the
                # ping was sent for more than MISSED_PONG_LIMIT intervals.
                stale_seconds = time.monotonic() - last_pong
                if last_pong < last_ping and stale_seconds > (
                    HEARTBEAT_INTERVAL * MISSED_PONG_LIMIT
                ):
                    logger.warning(
                        "No pong for %.1fs (limit %ds), closing stale connection",
                        stale_seconds,
                        HEARTBEAT_INTERVAL * MISSED_PONG_LIMIT,
                    )
                    await self._close_and_cleanup(ws)
                    return
        except asyncio.CancelledError:
            pass

    async def _close_and_cleanup(self, ws: WebSocket) -> None:
        try:
            await ws.close()
        except Exception:
            pass
        # Ensure bookkeeping is purged even if the caller hasn't disconnected yet.
        self._last_pong.pop(ws, None)
        self._last_ping.pop(ws, None)
