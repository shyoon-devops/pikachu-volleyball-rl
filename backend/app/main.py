"""FastAPI application entry-point."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

from backend.app.api.routes import router
from backend.app.services.game_service import GameService


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/pikachu_rl")
    client = AsyncIOMotorClient(mongodb_url)
    db = client.get_default_database()

    app.state.mongo_client = client
    app.state.db = db
    app.state.game_service = GameService(db)

    yield

    client.close()


app = FastAPI(
    title="Pikachu Volleyball RL",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
