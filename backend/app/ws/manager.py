"""WebSocket connection manager with heartbeat and backpressure."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30  # seconds between pings
HEARTBEAT_TIMEOUT = 10  # seconds to wait for pong after ping
# Clients that miss this many consecutive pongs are considered dead.
MISSED_PONG_LIMIT = 2


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
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

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
