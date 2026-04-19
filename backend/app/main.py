"""FastAPI application entry-point."""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.logging_config import configure_logging

# Install JSON logging before anything else emits a record so we don't miss
# startup messages under the legacy format.
configure_logging()

logger = logging.getLogger(__name__)

from backend.app.api.routes import router
from backend.app.metrics import setup_instrumentator
from backend.app.middleware.correlation import CorrelationIdMiddleware
from backend.app.middleware.rate_limit import RateLimitMiddleware
from backend.app.services.db_utils import build_mongo_client
from backend.app.services.eval_service import EvalServiceWrapper
from backend.app.services.game_service import GameService
from backend.app.services.indexes import ensure_indexes
from backend.app.services.metrics_service import MetricsService
from backend.app.services.replay_service import ReplayService
from backend.app.services.title_service import TrainingRunsService
from backend.app.services.training_service import TrainingServiceWrapper
from backend.app.ws.handlers import (
    env_frames_push_loop,
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

    # Track both wall-clock and monotonic uptime — the liveness probe reports
    # monotonic seconds (immune to clock skew) while humans prefer ISO start.
    app.state.started_at_monotonic = time.monotonic()
    app.state.started_at_wall = time.time()

    client = build_mongo_client(mongodb_url)
    db = client.get_default_database()

    # Ensure the hot-path indexes exist before we start accepting traffic.
    # Failures are logged (index module is best-effort) so a transient Mongo
    # issue at boot does not prevent the app from coming up at all.
    try:
        await ensure_indexes(db)
    except Exception:  # noqa: BLE001 — logged and swallowed intentionally
        logger.exception("ensure_indexes failed at startup; continuing without indexes")

    app.state.mongo_client = client
    app.state.db = db
    app.state.game_service = GameService(db)
    app.state.metrics_service = MetricsService(db)
    app.state.replay_service = ReplayService(replay_dir=replay_dir, max_count=max_replays)
    app.state.training_service = TrainingServiceWrapper(model_dir=model_dir, replay_dir=replay_dir)
    # Title-scoped run registry (BE-T1). Attached to the training service
    # so the WS handler can reach it without another app_state lookup.
    training_runs_service = TrainingRunsService(db)
    app.state.training_runs_service = training_runs_service
    app.state.training_service.runs_service = training_runs_service
    app.state.eval_service = EvalServiceWrapper(db)
    # League repository (v2 Sprint-1 B-impl-2). Wire early so the read
    # endpoints work even before a training run kicks off.
    from backend.app.services.league_repository import LeagueRepository
    app.state.league_repository = LeagueRepository(
        db, league_dir=os.getenv("LEAGUE_DIR", str(Path(model_dir) / "league")),
    )
    app.state.ws_manager = ConnectionManager()

    push_tasks = [
        asyncio.create_task(
            metrics_push_loop(
                app.state.ws_manager,
                app.state.training_service,
                metrics_service=app.state.metrics_service,
            )
        ),
        asyncio.create_task(frames_push_loop(app.state.ws_manager, app.state.training_service)),
        asyncio.create_task(
            env_frames_push_loop(app.state.ws_manager, app.state.training_service)
        ),
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

_cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

app.add_middleware(
    RateLimitMiddleware,
    # Defaults raised again 2026-04-18 (round 2) after PM repro showed
    # users still hitting 429 on the history page. Two issues:
    #
    #   1. Per-row metadata fan-out — opening Recent Games fires the
    #      list endpoint plus N detail endpoints per row (games + game/{id}
    #      + replays + replays/{id} + evaluations). Two refreshes in 10s
    #      blew through the previous 100-token burst.
    #   2. Behind nginx every real user collapses into ONE shared bucket
    #      because uvicorn sees the proxy IP. Set RATE_LIMIT_TRUST_PROXY=true
    #      in the dev/qa/prod envs (where nginx is in front and strips
    #      external XFF) so each real client gets its own bucket.
    #
    # New defaults give ~10 req/s sustained per IP with a 200-burst
    # window. RATE_LIMIT_TRUST_PROXY defaults OFF — direct-internet
    # deploys must NOT trust XFF (trivially spoofable).
    requests_per_minute=int(os.getenv("RATE_LIMIT_RPM", "600")),
    burst=int(os.getenv("RATE_LIMIT_BURST", "200")),
    trust_proxy=os.getenv("RATE_LIMIT_TRUST_PROXY", "false").lower()
    in ("1", "true", "yes"),
)

# Correlation ID middleware is added last so it runs first in the Starlette
# stack — every log line from downstream middleware/handlers picks it up.
app.add_middleware(CorrelationIdMiddleware)

app.include_router(router, prefix="/api")

setup_instrumentator(app)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler so 500s never leak internals or crash the worker.

    Per-endpoint try/except + HTTPException is still the primary mechanism;
    this backstop catches unexpected errors in middleware or dependencies.
    """
    logger.exception(
        "Unhandled exception at %s %s: %s",
        request.method, request.url.path, exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": "internal_error", "path": request.url.path}},
    )


@app.websocket("/ws")
async def websocket_route(ws: WebSocket):
    await ws_endpoint(
        ws,
        manager=app.state.ws_manager,
        training_service=app.state.training_service,
        replay_service=app.state.replay_service,
    )
