"""WebSocket message handlers and push loops."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.app.models.schemas import (
    WsReplayRequestPayload,
    WsSetLevelPayload,
    WsTrainingStartPayload,
)

if TYPE_CHECKING:
    from backend.app.services.replay_service import ReplayService
    from backend.app.services.training_service import TrainingServiceWrapper
    from backend.app.ws.manager import ConnectionManager

logger = logging.getLogger(__name__)


async def ws_endpoint(
    ws: WebSocket,
    manager: ConnectionManager,
    training_service: TrainingServiceWrapper,
    replay_service: ReplayService,
) -> None:
    """Handle a single WebSocket client lifecycle."""
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "")
            payload = data.get("payload", {})
            await _dispatch(ws, msg_type, payload, training_service, replay_service)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)


async def _send_error(ws: WebSocket, message: str) -> None:
    await ws.send_json({"type": "error", "payload": {"message": message}})


async def _dispatch(
    ws: WebSocket,
    msg_type: str,
    payload: dict[str, Any],
    training_service: TrainingServiceWrapper,
    replay_service: ReplayService,
) -> None:
    """Route incoming messages to the appropriate handler."""
    if msg_type == "training:start":
        current = training_service.status()
        if current["state"] == "running":
            await ws.send_json({
                "type": "training:error",
                "payload": {"message": "Training is already running"},
            })
            return
        try:
            params = WsTrainingStartPayload(**(payload or {}))
        except ValidationError as e:
            await _send_error(ws, f"Invalid training:start payload: {e.error_count()} errors")
            return
        experiment_id = await training_service.start(
            hyperparams=params.hyperparams,
            bot_level=params.bot_level,
            total_timesteps=params.total_timesteps,
        )
        logger.info("Training started: experiment=%s bot_level=%d", experiment_id, params.bot_level)
        await ws.send_json({
            "type": "training:status",
            "payload": {"state": "running", "experiment_id": experiment_id},
        })

    elif msg_type == "training:stop":
        await training_service.stop()
        logger.info("Training stopped")
        await ws.send_json({
            "type": "training:status",
            "payload": {"state": "stopped"},
        })

    elif msg_type == "training:resume":
        await training_service.resume()
        logger.info("Training resumed")
        await ws.send_json({
            "type": "training:status",
            "payload": {"state": "running"},
        })

    elif msg_type == "training:set_level":
        try:
            params = WsSetLevelPayload(**(payload or {}))
        except ValidationError as e:
            await _send_error(ws, f"Invalid level: {e.error_count()} errors")
            return
        training_service.set_bot_level(params.level)
        await ws.send_json({
            "type": "training:status",
            "payload": {"state": training_service.status()["state"], "bot_level": params.level},
        })

    elif msg_type == "replay:request":
        try:
            params = WsReplayRequestPayload(**(payload or {}))
        except ValidationError as e:
            await _send_error(ws, f"Invalid replay request: {e.error_count()} errors")
            return
        frames = await replay_service.load_replay(params.game_id)
        await ws.send_json({"type": "replay:data", "payload": {"frames": frames}})

    else:
        logger.warning("Unknown WS message type: %s", msg_type)


async def metrics_push_loop(
    manager: ConnectionManager,
    training_service: TrainingServiceWrapper,
) -> None:
    """Drain metrics queue and broadcast to all WS clients."""
    queue = training_service.manager.metrics_queue
    while True:
        data = await queue.get()
        await manager.broadcast({"type": "training:metrics", "payload": data})


async def frames_push_loop(
    manager: ConnectionManager,
    training_service: TrainingServiceWrapper,
) -> None:
    """Drain live-frame queue and broadcast to all WS clients."""
    queue = training_service.manager.frames_queue
    while True:
        data = await queue.get()
        await manager.broadcast({"type": "training:frame", "payload": data})


async def results_push_loop(
    manager: ConnectionManager,
    training_service: TrainingServiceWrapper,
    game_service: Any,
) -> None:
    """Drain game-result queue, save to DB, and broadcast."""
    from backend.app.models.schemas import GameRecord

    queue = training_service.manager.results_queue
    while True:
        data = await queue.get()
        record = GameRecord(
            experiment_id=data.get("experiment_id", ""),
            bot_level=data.get("bot_level", 1),
            score1=data["score1"],
            score2=data["score2"],
            winner=data["winner"],
            duration_frames=data["duration_frames"],
            rally_count=data.get("rally_count", 0),
        )
        try:
            await game_service.save_game(record)
        except Exception:
            logger.exception("Failed to save game result")
        await manager.broadcast({"type": "game:result", "payload": data})
