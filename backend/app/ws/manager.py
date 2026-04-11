"""WebSocket connection manager with heartbeat and backpressure."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 10  # seconds


class ConnectionManager:
    """Manages active WebSocket connections with heartbeat keepalive."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, asyncio.Task] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        task = asyncio.create_task(self._heartbeat(ws))
        self._connections[ws] = task
        logger.info("WS connected — active: %d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        task = self._connections.pop(ws, None)
        if task:
            task.cancel()
        logger.info("WS disconnected — active: %d", len(self._connections))

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
        """Ping client periodically; close stale connections."""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                try:
                    await asyncio.wait_for(
                        ws.send_json({"type": "ping"}),
                        timeout=HEARTBEAT_TIMEOUT,
                    )
                except (asyncio.TimeoutError, Exception):
                    logger.warning("Heartbeat failed, closing stale connection")
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    return
        except asyncio.CancelledError:
            pass
