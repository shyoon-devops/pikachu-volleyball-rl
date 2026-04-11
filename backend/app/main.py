"""FastAPI application entry-point."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

from backend.app.api.routes import router
from backend.app.services.eval_service import EvalServiceWrapper
from backend.app.services.game_service import GameService
from backend.app.services.replay_service import ReplayService
from backend.app.services.training_service import TrainingServiceWrapper
from backend.app.ws.handlers import (
    frames_push_loop,
    metrics_push_loop,
    results_push_loop,
    ws_endpoint,
)
from backend.app.ws.manager import ConnectionManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/pikachu_rl")
    model_dir = os.getenv("MODEL_DIR", "./models")
    replay_dir = os.getenv("REPLAY_DIR", "./replays")
    max_replays = int(os.getenv("MAX_REPLAYS", "1000"))

    client = AsyncIOMotorClient(mongodb_url)
    db = client.get_default_database()

    app.state.mongo_client = client
    app.state.db = db
    app.state.game_service = GameService(db)
    app.state.replay_service = ReplayService(replay_dir=replay_dir, max_count=max_replays)
    app.state.training_service = TrainingServiceWrapper(model_dir=model_dir, replay_dir=replay_dir)
    app.state.eval_service = EvalServiceWrapper(db)
    app.state.ws_manager = ConnectionManager()

    push_tasks = [
        asyncio.create_task(metrics_push_loop(app.state.ws_manager, app.state.training_service)),
        asyncio.create_task(frames_push_loop(app.state.ws_manager, app.state.training_service)),
        asyncio.create_task(
            results_push_loop(
                app.state.ws_manager, app.state.training_service, app.state.game_service
            )
        ),
    ]

    yield

    for t in push_tasks:
        t.cancel()
    await asyncio.gather(*push_tasks, return_exceptions=True)

    await app.state.training_service.stop()
    client.close()


app = FastAPI(
    title="Pikachu Volleyball RL",
    version="0.1.0",
    lifespan=lifespan,
)

_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.websocket("/ws")
async def websocket_route(ws: WebSocket):
    await ws_endpoint(
        ws,
        manager=app.state.ws_manager,
        training_service=app.state.training_service,
        replay_service=app.state.replay_service,
    )
