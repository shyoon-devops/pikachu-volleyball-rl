"""REST API endpoints — see docs/PLAN.md section 3.1."""

import asyncio
import logging
import os
import shutil
from functools import wraps
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from backend.app.logging_config import process_uptime_seconds
from backend.app.metrics import (
    MONGO_PING_LATENCY,
    MONGO_PING_OK,
    sample_runtime_metrics,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Limit concurrent evaluations (each can run minutes)
_eval_semaphore = asyncio.Semaphore(1)

# Health check thresholds
_DISK_USAGE_THRESHOLD = 0.90  # 90%
_QUEUE_DEPTH_WARN_RATIO = 0.90  # warn if a queue is >=90% full
_MONGO_PING_TIMEOUT = 2.0  # seconds


def endpoint_guard(name: str):
    """Wrap an endpoint so unexpected exceptions are logged and returned as 500.

    HTTPException is re-raised untouched (FastAPI handles it); everything else
    becomes a 500 with a generic message so we do not leak internals. The full
    traceback is captured via logger.exception.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception:
                logger.exception("Unhandled error in endpoint %s", name)
                raise HTTPException(
                    status_code=500,
                    detail={"code": "internal_error", "endpoint": name},
                )

        return wrapper

    return decorator


async def _check_mongo(request: Request) -> dict:
    """Ping MongoDB; return {ok, latency_ms, error?} and publish gauges."""
    client = getattr(request.app.state, "mongo_client", None)
    if client is None:
        MONGO_PING_OK.set(0)
        return {"ok": False, "error": "mongo_client not initialized"}
    loop = asyncio.get_running_loop()
    start = loop.time()
    try:
        await asyncio.wait_for(client.admin.command("ping"), timeout=_MONGO_PING_TIMEOUT)
        latency_s = loop.time() - start
        MONGO_PING_LATENCY.set(latency_s)
        MONGO_PING_OK.set(1)
        return {"ok": True, "latency_ms": round(latency_s * 1000, 2)}
    except asyncio.TimeoutError:
        MONGO_PING_OK.set(0)
        return {"ok": False, "error": f"ping timed out after {_MONGO_PING_TIMEOUT}s"}
    except Exception as e:
        MONGO_PING_OK.set(0)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _check_disk() -> dict:
    """Check disk usage against threshold.

    Falls back to the current working directory when REPLAY_DIR is missing —
    a non-existent data directory is a configuration concern, not disk
    saturation.
    """
    candidates = [os.getenv("REPLAY_DIR", "./replays"), "."]
    for path in candidates:
        if path and Path(path).exists():
            try:
                usage = shutil.disk_usage(path)
                ratio = usage.used / usage.total if usage.total else 0.0
                return {
                    "ok": ratio < _DISK_USAGE_THRESHOLD,
                    "used_ratio": round(ratio, 4),
                    "free_bytes": usage.free,
                    "threshold": _DISK_USAGE_THRESHOLD,
                    "path": path,
                }
            except Exception as e:
                return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": False, "error": "no usable path for disk check"}


def _check_training(request: Request) -> dict:
    """Check training thread liveness relative to reported status."""
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is None:
        return {"ok": True, "state": "uninitialized"}
    manager = getattr(training_service, "manager", None)
    state = getattr(manager, "status", "stopped") if manager is not None else "stopped"
    thread = getattr(manager, "_thread", None) if manager is not None else None
    alive = bool(thread and thread.is_alive())
    # If reported "running" but thread is dead, that's a failure.
    if state == "running" and not alive:
        return {"ok": False, "state": state, "thread_alive": False,
                "error": "status=running but thread is not alive"}
    return {"ok": True, "state": state, "thread_alive": alive}


def _check_queues(request: Request) -> dict:
    """Report queue depths; flag not-ok only if a bounded queue is saturated."""
    training_service = getattr(request.app.state, "training_service", None)
    manager = getattr(training_service, "manager", None) if training_service else None
    if manager is None:
        return {"ok": True, "queues": {}}
    depths: dict[str, dict] = {}
    saturated = False
    for name in ("metrics_queue", "frames_queue", "results_queue"):
        q = getattr(manager, name, None)
        if q is None:
            continue
        size = q.qsize()
        maxsize = q.maxsize
        ratio = (size / maxsize) if maxsize else 0.0
        depths[name] = {"size": size, "maxsize": maxsize, "ratio": round(ratio, 3)}
        if maxsize and ratio >= _QUEUE_DEPTH_WARN_RATIO:
            saturated = True
    return {"ok": not saturated, "queues": depths}


def _uptime_seconds(request: Request) -> float:
    started = getattr(request.app.state, "started_at_monotonic", None)
    return round(process_uptime_seconds(started), 3)


@router.get("/health/live")
async def health_live(request: Request):
    """Liveness probe — the process is up and event loop is responsive.

    Used by k8s ``livenessProbe``: if this fails the pod gets restarted, so
    we deliberately avoid any external I/O here. Answering is evidence enough.
    """
    return {"status": "live", "uptime_seconds": _uptime_seconds(request)}


async def _readiness_payload(request: Request) -> tuple[dict, bool]:
    mongo = await _check_mongo(request)
    disk = _check_disk()
    training = _check_training(request)
    queues = _check_queues(request)

    # Mongo and disk are hard dependencies; training/queue saturation degrade status.
    healthy = mongo["ok"] and disk["ok"] and training["ok"] and queues["ok"]
    payload = {
        "status": "ok" if healthy else "unhealthy",
        "uptime_seconds": _uptime_seconds(request),
        "checks": {
            "mongo": mongo,
            "disk": disk,
            "training": training,
            "queues": queues,
        },
    }
    return payload, healthy


@router.get("/health/ready")
async def health_ready(request: Request):
    """Readiness probe — all critical dependencies are usable.

    Used by k8s ``readinessProbe``: if this fails the pod stays alive but is
    removed from the service mesh until it recovers.
    """
    payload, healthy = await _readiness_payload(request)
    if not healthy:
        logger.warning("Readiness check failed: %s", payload)
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/health")
async def health_check(request: Request):
    """Backward-compatible health check — delegates to readiness.

    Returns 200 when all checks pass, 503 if any critical check fails. Prefer
    ``/api/health/live`` and ``/api/health/ready`` for probe configurations.
    """
    payload, healthy = await _readiness_payload(request)
    if not healthy:
        logger.warning("Health check failed: %s", payload)
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/metrics", response_class=PlainTextResponse)
@endpoint_guard("metrics")
async def prometheus_metrics(request: Request) -> PlainTextResponse:
    """Expose app metrics in Prometheus text-exposition format.

    Samples live runtime state (WS connections, queue depths) before
    rendering so each scrape reflects current values. Counters are
    maintained by event paths (save success/failure) and simply reported.
    """
    # Make sure the mongo ping gauge is fresh; this is cheap and makes the
    # endpoint self-contained when /api/health has not been hit recently.
    await _check_mongo(request)
    sample_runtime_metrics(request.app.state)
    body = generate_latest()
    return PlainTextResponse(content=body, media_type=CONTENT_TYPE_LATEST)


@router.get("/training/status")
@endpoint_guard("training_status")
async def training_status(request: Request):
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is None:
        logger.info("training_status called before training_service init")
        return {"state": "stopped", "current_step": 0, "current_episode": 0}
    return training_service.status()


@router.get("/games")
@endpoint_guard("list_games")
async def list_games(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    game_service = getattr(request.app.state, "game_service", None)
    if game_service is None:
        logger.warning("list_games called but game_service is not initialized")
        raise HTTPException(status_code=503, detail="Game service not available")
    return await game_service.get_games(page=page, limit=limit)


@router.get("/games/{game_id}")
@endpoint_guard("get_game")
async def get_game(request: Request, game_id: str):
    game_service = getattr(request.app.state, "game_service", None)
    if game_service is None:
        logger.warning("get_game called but game_service is not initialized")
        raise HTTPException(status_code=503, detail="Game service not available")
    doc = await game_service.get_game(game_id)
    if doc is None:
        logger.info("get_game: not found (game_id=%s)", game_id)
        raise HTTPException(status_code=404, detail="Game not found")
    return doc


@router.get("/replays")
@endpoint_guard("list_replays")
async def list_replays(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    replay_service = getattr(request.app.state, "replay_service", None)
    if replay_service is None:
        logger.info("list_replays called before replay_service init; returning empty")
        return {"replays": [], "total": 0, "page": page, "limit": limit}
    all_replays = await replay_service.list_replays()
    total = len(all_replays)
    start = (page - 1) * limit
    sliced = all_replays[start : start + limit]
    return {"replays": sliced, "total": total, "page": page, "limit": limit}


@router.get("/replays/{game_id}")
@endpoint_guard("get_replay")
async def get_replay(request: Request, game_id: str):
    replay_service = getattr(request.app.state, "replay_service", None)
    if replay_service is None:
        logger.warning("get_replay called but replay_service is not initialized")
        raise HTTPException(status_code=501, detail="Replay service not available")
    frames = await replay_service.load_replay(game_id)
    if not frames:
        logger.info("get_replay: not found (game_id=%s)", game_id)
        raise HTTPException(status_code=404, detail="Replay not found")
    # Include linked game record if available. A game lookup failure should not
    # break the replay response — log and continue with game=None.
    game_service = getattr(request.app.state, "game_service", None)
    game = None
    if game_service is not None:
        try:
            game = await game_service.get_game_by_game_id(game_id)
        except Exception:
            logger.exception(
                "get_replay: failed to fetch linked game record (game_id=%s)", game_id
            )
    return {"game_id": game_id, "frames": frames, "game": game}


@router.get("/models")
@endpoint_guard("list_models")
async def list_models():
    model_dir = Path(os.getenv("MODEL_DIR", "./models")).resolve()
    if not model_dir.exists():
        logger.info("list_models: model_dir missing (%s)", model_dir)
        return {"models": []}
    try:
        files = sorted(
            model_dir.rglob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True
        )
    except OSError:
        logger.exception("list_models: failed to scan model_dir=%s", model_dir)
        raise HTTPException(status_code=500, detail="Failed to read model directory")
    # Only include files that resolve within the model directory
    safe_files = [f for f in files if str(f.resolve()).startswith(str(model_dir))]
    return {
        "models": [
            {"path": str(f.relative_to(model_dir)), "size_bytes": f.stat().st_size}
            for f in safe_files
        ]
    }


class EvalRunRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_path: str
    bot_level: int = Field(default=1, ge=1, le=5)
    n_games: int = Field(default=50, ge=1, le=500)


@router.post("/evaluation/run")
@endpoint_guard("run_evaluation")
async def run_evaluation(request: Request, body: EvalRunRequest):
    eval_service = getattr(request.app.state, "eval_service", None)
    if eval_service is None:
        logger.warning("run_evaluation called but eval_service is not initialized")
        raise HTTPException(status_code=501, detail="Evaluation service not available")
    if _eval_semaphore.locked():
        logger.info("run_evaluation rejected — another evaluation is in progress")
        raise HTTPException(status_code=409, detail="Evaluation already in progress")
    async with _eval_semaphore:
        try:
            result = await eval_service.run(
                model_path=body.model_path,
                bot_level=body.bot_level,
                n_games=body.n_games,
            )
        except FileNotFoundError as e:
            logger.info("run_evaluation: %s", e)
            raise HTTPException(status_code=404, detail=str(e))
    logger.info(
        "run_evaluation ok model=%s bot_level=%d n_games=%d",
        body.model_path, body.bot_level, body.n_games,
    )
    return result


@router.get("/evaluation/results")
@endpoint_guard("get_evaluation_results")
async def get_evaluation_results(request: Request):
    eval_service = getattr(request.app.state, "eval_service", None)
    if eval_service is None:
        logger.info("get_evaluation_results called before eval_service init")
        return {"data": []}
    return await eval_service.get_results()
