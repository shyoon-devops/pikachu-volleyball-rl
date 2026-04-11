"""WebSocket message handlers and push loops."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket, WebSocketDisconnect

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


async def _dispatch(
    ws: WebSocket,
    msg_type: str,
    payload: dict[str, Any],
    training_service: TrainingServiceWrapper,
    replay_service: ReplayService,
) -> None:
    """Route incoming messages to the appropriate handler."""
    if msg_type == "training:start":
        experiment_id = await training_service.start(
            hyperparams=payload.get("hyperparams"),
            bot_level=payload.get("bot_level", 1),
        )
        await ws.send_json({
            "type": "training:status",
            "payload": {"state": "running", "experiment_id": experiment_id},
        })

    elif msg_type == "training:stop":
        force = payload.get("force", False)
        result = await training_service.stop(force=force)
        if result["stopped"]:
            await ws.send_json({
                "type": "training:status",
                "payload": {"state": "stopped"},
            })
        else:
            await ws.send_json({
                "type": "training:stop_rejected",
                "payload": result,
            })

    elif msg_type == "training:resume":
        await training_service.resume()
        await ws.send_json({
            "type": "training:status",
            "payload": {"state": "running"},
        })

    elif msg_type == "training:set_level":
        level = payload.get("level", 1)
        training_service.set_bot_level(level)
        await ws.send_json({
            "type": "training:status",
            "payload": {"state": training_service.status()["state"], "bot_level": level},
        })

    elif msg_type == "replay:request":
        game_id = payload.get("game_id", "")
        frames = await replay_service.load_replay(game_id)
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
