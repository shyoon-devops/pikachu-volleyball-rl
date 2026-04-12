"""REST API endpoints — see docs/PLAN.md section 3.1."""

import asyncio
import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)

# Limit concurrent evaluations (each can run minutes)
_eval_semaphore = asyncio.Semaphore(1)

# Health check thresholds
_DISK_USAGE_THRESHOLD = 0.90  # 90%
_QUEUE_DEPTH_WARN_RATIO = 0.90  # warn if a queue is >=90% full
_MONGO_PING_TIMEOUT = 2.0  # seconds


async def _check_mongo(request: Request) -> dict:
    """Ping MongoDB; return {ok, latency_ms, error?}."""
    client = getattr(request.app.state, "mongo_client", None)
    if client is None:
        return {"ok": False, "error": "mongo_client not initialized"}
    loop = asyncio.get_running_loop()
    start = loop.time()
    try:
        await asyncio.wait_for(client.admin.command("ping"), timeout=_MONGO_PING_TIMEOUT)
        return {"ok": True, "latency_ms": round((loop.time() - start) * 1000, 2)}
    except asyncio.TimeoutError:
        return {"ok": False, "error": f"ping timed out after {_MONGO_PING_TIMEOUT}s"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _check_disk() -> dict:
    """Check disk usage against threshold."""
    try:
        usage = shutil.disk_usage(os.getenv("REPLAY_DIR", "./replays") or ".")
        ratio = usage.used / usage.total if usage.total else 0.0
        return {
            "ok": ratio < _DISK_USAGE_THRESHOLD,
            "used_ratio": round(ratio, 4),
            "free_bytes": usage.free,
            "threshold": _DISK_USAGE_THRESHOLD,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


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


@router.get("/health")
async def health_check(request: Request):
    """Report live health of core subsystems.

    Returns 200 when all checks pass, 503 if any critical check fails.
    """
    mongo = await _check_mongo(request)
    disk = _check_disk()
    training = _check_training(request)
    queues = _check_queues(request)

    # Mongo and disk are hard dependencies; training/queue saturation degrade status.
    healthy = mongo["ok"] and disk["ok"] and training["ok"] and queues["ok"]
    payload = {
        "status": "ok" if healthy else "unhealthy",
        "checks": {
            "mongo": mongo,
            "disk": disk,
            "training": training,
            "queues": queues,
        },
    }
    if not healthy:
        logger.warning("Health check failed: %s", payload)
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/training/status")
async def training_status(request: Request):
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is None:
        return {"state": "stopped", "current_step": 0, "current_episode": 0}
    return training_service.status()


@router.get("/games")
async def list_games(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    game_service = request.app.state.game_service
    return await game_service.get_games(page=page, limit=limit)


@router.get("/games/{game_id}")
async def get_game(request: Request, game_id: str):
    game_service = request.app.state.game_service
    doc = await game_service.get_game(game_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return doc


@router.get("/replays")
async def list_replays(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    replay_service = getattr(request.app.state, "replay_service", None)
    if replay_service is None:
        return {"replays": [], "total": 0, "page": page, "limit": limit}
    all_replays = await replay_service.list_replays()
    total = len(all_replays)
    start = (page - 1) * limit
    sliced = all_replays[start : start + limit]
    return {"replays": sliced, "total": total, "page": page, "limit": limit}


@router.get("/replays/{game_id}")
async def get_replay(request: Request, game_id: str):
    replay_service = getattr(request.app.state, "replay_service", None)
    if replay_service is None:
        raise HTTPException(status_code=501, detail="Replay service not available")
    frames = await replay_service.load_replay(game_id)
    if not frames:
        raise HTTPException(status_code=404, detail="Replay not found")
    # Include linked game record if available
    game_service = request.app.state.game_service
    game = await game_service.get_game_by_game_id(game_id)
    return {"game_id": game_id, "frames": frames, "game": game}


@router.get("/models")
async def list_models():
    model_dir = Path(os.getenv("MODEL_DIR", "./models")).resolve()
    if not model_dir.exists():
        return {"models": []}
    files = sorted(model_dir.rglob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
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
async def run_evaluation(request: Request, body: EvalRunRequest):
    eval_service = getattr(request.app.state, "eval_service", None)
    if eval_service is None:
        raise HTTPException(status_code=501, detail="Evaluation service not available")
    if _eval_semaphore.locked():
        raise HTTPException(status_code=409, detail="Evaluation already in progress")
    async with _eval_semaphore:
        try:
            result = await eval_service.run(
                model_path=body.model_path,
                bot_level=body.bot_level,
                n_games=body.n_games,
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
    return result


@router.get("/evaluation/results")
async def get_evaluation_results(request: Request):
    eval_service = getattr(request.app.state, "eval_service", None)
    if eval_service is None:
        return {"data": []}
    return await eval_service.get_results()
