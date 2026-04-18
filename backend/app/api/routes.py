"""REST API endpoints — see docs/PLAN.md section 3.1."""

import asyncio
import logging
import os
import shutil
from functools import wraps
from pathlib import Path
from typing import Any

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
from backend.app.models.schemas import PaginatedResponse
from backend.app.services.eval_jobs import EvalJobRegistry
from backend.app.services.metrics_service import allowed_buckets
from backend.app.util.ttl_cache import cache_ttl

router = APIRouter()
logger = logging.getLogger(__name__)

# Limit concurrent evaluations (each can run minutes). Evaluations now
# run as background tasks; the semaphore still gates them to 1-at-a-time
# so a flood of POSTs cannot starve the GPU or spawn parallel PPO loads.
_eval_semaphore = asyncio.Semaphore(1)

# In-memory job registry — async-safe, LRU-capped. See eval_jobs.py for
# the rationale on why restart-loss of in-flight state is acceptable.
_eval_jobs = EvalJobRegistry()

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
        return {
            "state": "stopped",
            "current_step": 0,
            "current_episode": 0,
            "bot_level": 1,
            "experiment_id": None,
            "started_at": None,
        }
    return training_service.status()


# --- Training control (REST) -------------------------------------------------
#
# These are REST mirrors of the existing WS control messages. FE-8's refresh-
# resilience story needs plain HTTP — not every dashboard mount opens a WS
# immediately, and a button click should not silently fail because the socket
# is reconnecting. Each handler does the mutation via TrainingServiceWrapper
# and then broadcasts the resulting ``training:status`` to every live WS
# client so open dashboards stay in sync with the button-clicker.


async def _broadcast_status(request: Request, payload: dict[str, Any]) -> None:
    """Fan a training:status message out to every connected WS client.

    Lives here (not in handlers.py) because REST endpoints don't see a WS
    ``ws`` argument — they only have ``request.app.state.ws_manager``. When
    the manager is missing (early startup / some test fixtures) we no-op
    rather than 500ing the REST call, since the mutation itself succeeded.
    """
    ws_manager = getattr(request.app.state, "ws_manager", None)
    if ws_manager is None:
        return
    try:
        await ws_manager.broadcast({"type": "training:status", "payload": payload})
    except Exception:
        # Broadcast is best-effort — we never want a WS fan-out failure to
        # mask a successful REST mutation.
        logger.exception("Failed to broadcast training:status over WS")


@router.post("/training/stop")
@endpoint_guard("training_stop")
async def training_stop_rest(request: Request):
    """Stop training (REST mirror of WS ``training:stop``).

    Always sends ``force=True`` — see TrainingServiceWrapper.stop for the
    rationale (UI click is explicit intent; protection threshold only guards
    against accidental background callers).
    """
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is None:
        raise HTTPException(status_code=503, detail="Training service not available")
    result = await training_service.stop(force=True)
    state = training_service.status()
    logger.info(
        "REST training/stop: stopped=%s reason=%s actual_state=%s",
        result.get("stopped"), result.get("reason"), state["state"],
    )
    await _broadcast_status(request, {"state": state["state"]})
    return {"ok": True, "result": result, "status": state}


@router.post("/training/pause")
@endpoint_guard("training_pause")
async def training_pause_rest(request: Request):
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is None:
        raise HTTPException(status_code=503, detail="Training service not available")
    result = await training_service.pause()
    state = training_service.status()
    logger.info(
        "REST training/pause: paused=%s reason=%s actual_state=%s",
        result.get("paused"), result.get("reason"), state["state"],
    )
    await _broadcast_status(request, {"state": state["state"]})
    return {"ok": True, "result": result, "status": state}


@router.post("/training/resume")
@endpoint_guard("training_resume")
async def training_resume_rest(request: Request):
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is None:
        raise HTTPException(status_code=503, detail="Training service not available")
    try:
        result = await training_service.resume()
    except FileNotFoundError as e:
        # resume-from-stopped needs a checkpoint; surface 409 so FE shows an
        # actionable error instead of a generic 500.
        logger.info("REST training/resume rejected: no checkpoint (%s)", e)
        raise HTTPException(status_code=409, detail=str(e)) from e
    state = training_service.status()
    logger.info(
        "REST training/resume: reason=%s actual_state=%s",
        result.get("reason"), state["state"],
    )
    await _broadcast_status(request, {"state": state["state"]})
    return {"ok": True, "result": result, "status": state}


class TrainingLevelPatch(BaseModel):
    """Request body for PATCH /api/training/level."""

    level: int = Field(ge=1, le=5, description="Bot difficulty 1-5")


@router.get("/training/level")
@endpoint_guard("training_level_get")
async def training_level_get(request: Request):
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is None:
        raise HTTPException(status_code=503, detail="Training service not available")
    return {"level": training_service.status()["bot_level"]}


@router.get("/training/titles")
@endpoint_guard("training_titles")
async def training_titles(
    request: Request,
    q: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List training titles for FE autocomplete / duplicate check.

    Spec references DESIGN-TRAINING-TITLE.md §1 (debounced uniqueness
    lookup) and §3 (autocomplete combobox). ``q`` is a case-insensitive
    substring filter — missing ``q`` returns the most recent ``limit``
    titles. The service returns plain dicts so the FE can render the
    "prior run's date" hint on a duplicate without a second fetch.
    """
    runs_service = getattr(request.app.state, "training_runs_service", None)
    if runs_service is None:
        # Training runs collection hasn't been initialized (likely a
        # no-Mongo test harness). Surface an empty list rather than 503
        # so the FE autocomplete degrades gracefully.
        return {"titles": []}
    titles = await runs_service.list_titles(q=q, limit=limit)
    return {"titles": titles}


@router.patch("/training/level")
@endpoint_guard("training_level_patch")
async def training_level_patch(request: Request, body: TrainingLevelPatch):
    """Change bot difficulty.

    Mirrors the WS ``training:set_level`` handler: the mutation is applied
    synchronously via ``set_bot_level``, then the new ``bot_level`` is
    broadcast in a ``training:status`` frame so other dashboards re-render.
    """
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is None:
        raise HTTPException(status_code=503, detail="Training service not available")
    try:
        training_service.set_bot_level(body.level)
    except ValueError as e:
        # The manager validates too — duplicate the bound here so the 400
        # carries the underlying message instead of a generic pydantic error.
        raise HTTPException(status_code=400, detail=str(e)) from e
    state = training_service.status()
    await _broadcast_status(
        request,
        {"state": state["state"], "bot_level": body.level},
    )
    return {"level": body.level}


# Metric aliases the FE actually asks for vs the field names MetricsCallback
# emits. Keeping an explicit table — rather than echoing whatever the client
# sends — guarantees we never pass an arbitrary field name into Mongo.
_TIMESERIES_METRICS: dict[str, str] = {
    "reward": "mean_reward",
    "win_rate": "win_rate",
    "loss": "policy_loss",
    "policy_loss": "policy_loss",
    "value_loss": "value_loss",
}


@router.get("/training/timeseries")
@endpoint_guard("training_timeseries")
async def training_timeseries(
    request: Request,
    metric: str = Query(
        "reward",
        description=f"Metric name. One of: {', '.join(sorted(_TIMESERIES_METRICS))}.",
    ),
    limit: int = Query(
        1000, ge=1, le=10000,
        description=(
            "Maximum number of points, newest last. Cap raised from 1000 "
            "to 10000 so long training runs (MetricsCallback now emits "
            "every 256 steps → ~3900 points at 1M steps) can be fetched "
            "in a single call without client-side pagination."
        ),
    ),
    experiment_id: str | None = Query(
        None, description="Restrict to a single experiment_id.",
    ),
):
    """Raw recent metric points for chart recovery on page refresh.

    This is deliberately a thin wrapper over ``MetricsService.recent_points``.
    The pre-existing ``/api/training/metrics/aggregate`` endpoint is the
    bucketed / downsampled view; this one streams the raw (step, value)
    pairs so the frontend can re-plot exactly what the live WS stream will
    continue from. Returning them newest-last means the chart can extend to
    the right as WS frames arrive without needing to sort.
    """
    if metric not in _TIMESERIES_METRICS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown metric {metric!r}; "
                f"allowed: {sorted(_TIMESERIES_METRICS)}"
            ),
        )
    metrics_service = getattr(request.app.state, "metrics_service", None)
    if metrics_service is None:
        # Degrade gracefully — FE still gets a valid envelope, just empty.
        logger.info("training_timeseries called before metrics_service init")
        return {"metric": metric, "experiment_id": experiment_id, "points": []}

    field = _TIMESERIES_METRICS[metric]
    points = await metrics_service.recent_points(
        field=field, limit=limit, experiment_id=experiment_id,
    )
    return {
        "metric": metric,
        "experiment_id": experiment_id,
        "points": points,
    }


@router.get("/training/current_frame")
@endpoint_guard("training_current_frame")
async def training_current_frame(request: Request):
    """Return the most recent live-demo frame, or 404 when none is cached.

    Served from ``TrainingManager.last_frame`` (updated by LiveFrameCallback).
    FE uses this on page mount to repaint the canvas instantly instead of
    waiting for the next WS ``training:frame`` push. Returns 404 rather
    than ``null`` so a missing frame is distinguishable from a real frame
    whose keys happen to be zero.
    """
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is None:
        raise HTTPException(status_code=503, detail="Training service not available")
    frame = training_service.last_frame()
    if frame is None:
        raise HTTPException(status_code=404, detail="No live frame available")
    return frame


@router.get("/training/metrics/aggregate")
@endpoint_guard("training_metrics_aggregate")
@cache_ttl(seconds=10, max_entries=128, include=("experiment_id", "bucket", "since", "until"))
async def training_metrics_aggregate(
    request: Request,
    experiment_id: str | None = Query(
        None, description="Restrict aggregation to a single experiment_id."
    ),
    bucket: str = Query(
        "1m",
        description=f"Bucket grain. One of: {', '.join(allowed_buckets())}.",
    ),
    since: str | None = Query(
        None, description="Inclusive lower bound, ISO-8601 timestamp."
    ),
    until: str | None = Query(
        None, description="Exclusive upper bound, ISO-8601 timestamp."
    ),
):
    """Time-bucketed training-metric aggregates (BE-7).

    Returns an ordered list of buckets with averages for reward, win-rate,
    and policy/value loss. ``since`` / ``until`` accept ISO-8601 strings and
    default to the last 6 hours when both are omitted so the query is
    always index-bounded. Cached for 10s — at a 100ms metric cadence the
    freshness penalty is negligible and dashboards that poll at 1Hz would
    otherwise hammer the aggregation pipeline.
    """
    from datetime import datetime

    metrics_service = getattr(request.app.state, "metrics_service", None)
    if metrics_service is None:
        logger.warning(
            "training_metrics_aggregate called before metrics_service init"
        )
        raise HTTPException(status_code=503, detail="Metrics service not available")

    if bucket not in allowed_buckets():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bucket {bucket!r}; allowed: {list(allowed_buckets())}",
        )

    def _parse(value: str | None, field: str) -> datetime | None:
        if value is None:
            return None
        try:
            # fromisoformat handles both naive and tz-aware strings, and the
            # trailing-Z shorthand emitted by JS Date.toISOString().
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid {field} timestamp: {e}"
            ) from e

    since_dt = _parse(since, "since")
    until_dt = _parse(until, "until")

    buckets = await metrics_service.aggregate(
        experiment_id=experiment_id,
        bucket=bucket,
        since=since_dt,
        until=until_dt,
    )
    return {
        "experiment_id": experiment_id,
        "bucket": bucket,
        "count": len(buckets),
        "data": buckets,
    }


@router.get("/games")
@endpoint_guard("list_games")
@cache_ttl(seconds=5, max_entries=64, include=("page", "limit"))
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
@cache_ttl(seconds=5, max_entries=64, include=("page", "limit"))
async def list_replays(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """List available replays with unified pagination envelope.

    The response carries the standard ``{data, total, page, limit, has_more}``
    shape. ``replays`` is retained as an alias of ``data`` so existing
    frontend callers (see frontend/src/lib/api.ts) keep working until they
    migrate to the new envelope.
    """
    replay_service = getattr(request.app.state, "replay_service", None)
    if replay_service is None:
        logger.info("list_replays called before replay_service init; returning empty")
        envelope = PaginatedResponse(data=[], total=0, page=page, limit=limit).model_dump()
        envelope["replays"] = []
        return envelope
    all_replays = await replay_service.list_replays()
    total = len(all_replays)
    start = (page - 1) * limit
    sliced = all_replays[start : start + limit]
    envelope = PaginatedResponse(data=sliced, total=total, page=page, limit=limit).model_dump()
    envelope["replays"] = sliced  # backward-compat alias for the frontend
    return envelope


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
@cache_ttl(seconds=10, max_entries=1)
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


async def _run_evaluation_job(
    job_id: str,
    eval_service: Any,
    body: EvalRunRequest,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Background task body for a single evaluation.

    Runs under ``_eval_semaphore`` so only one evaluation executes at a
    time even if multiple POSTs queue up. Exceptions are caught and
    surfaced through the job registry — they MUST NOT propagate, or the
    task would die silently and the poller would see a stuck "running".
    """
    # Progress callback fires on the worker thread; marshal the state
    # update back onto the event loop so the registry lock stays on a
    # single thread. Fire-and-forget — a dropped progress update is a
    # cosmetic issue, not a correctness one.
    def _on_progress(current: int, total: int) -> None:
        asyncio.run_coroutine_threadsafe(
            _eval_jobs.update_progress(job_id, current), loop
        )

    async with _eval_semaphore:
        try:
            # Total isn't known inside the evaluator at callback-time, so
            # seed it here from the request before running. This also
            # gives the UI a "0 / N" to render while waiting on game 1.
            await _eval_jobs.mark_running(job_id, body.n_games)
            result = await eval_service.run(
                model_path=body.model_path,
                bot_level=body.bot_level,
                n_games=body.n_games,
                progress_callback=_on_progress,
            )
        except FileNotFoundError as e:
            logger.info("eval job %s: %s", job_id, e)
            await _eval_jobs.mark_failed(job_id, f"not_found: {e}")
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("eval job %s crashed", job_id)
            await _eval_jobs.mark_failed(job_id, f"{type(e).__name__}: {e}")
            return

    await _eval_jobs.mark_done(job_id, result)
    logger.info(
        "eval job %s ok model=%s bot_level=%d n_games=%d",
        job_id, body.model_path, body.bot_level, body.n_games,
    )


@router.post("/evaluation/run", status_code=202)
@endpoint_guard("run_evaluation")
async def run_evaluation(request: Request, body: EvalRunRequest):
    """Fire-and-forget evaluation: returns immediately with a job_id.

    The evaluation itself (minutes to tens of minutes) runs as a
    background asyncio task. Poll GET /api/evaluation/status/{job_id}
    for progress and the final result. 409 is still returned when
    another job is already running — FE can render "busy" without
    having to mint a dead job id.
    """
    eval_service = getattr(request.app.state, "eval_service", None)
    if eval_service is None:
        logger.warning("run_evaluation called but eval_service is not initialized")
        raise HTTPException(status_code=501, detail="Evaluation service not available")
    if _eval_semaphore.locked():
        logger.info("run_evaluation rejected — another evaluation is in progress")
        raise HTTPException(status_code=409, detail="Evaluation already in progress")

    # Synchronous path pre-flight — traversal / missing-file errors come
    # back as a 404 on the POST itself. Otherwise the job would always
    # accept (202), only for the poller to discover the failure on the
    # next tick. Keeps backward-compat with callers that treat the POST
    # as "reject-fast on obvious input errors".
    if hasattr(eval_service, "validate_model_path"):
        try:
            eval_service.validate_model_path(body.model_path)
        except FileNotFoundError as e:
            logger.info("run_evaluation rejected: %s", e)
            raise HTTPException(status_code=404, detail=str(e))

    job_id = await _eval_jobs.create()
    loop = asyncio.get_running_loop()
    # Detach the task — we never await it; the response must return now
    # so nginx's upstream timeout does not eat the HTTP connection.
    asyncio.create_task(
        _run_evaluation_job(job_id, eval_service, body, loop),
        name=f"eval-job-{job_id}",
    )
    logger.info(
        "eval job %s accepted model=%s bot_level=%d n_games=%d",
        job_id, body.model_path, body.bot_level, body.n_games,
    )
    return {"job_id": job_id, "state": "pending"}


@router.get("/evaluation/status/{job_id}")
@endpoint_guard("get_evaluation_status")
async def get_evaluation_status(job_id: str):
    """Return the current state of an async evaluation job.

    Response shape is stable across states; ``result`` is populated only
    when ``state == "done"`` and ``error`` only when ``state == "failed"``.
    Unknown job_id returns 404 so FE polling loops can detect evicted /
    restart-lost jobs cleanly.
    """
    job = await _eval_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job["job_id"],
        "state": job["state"],
        "progress": {
            "current": job["progress_current"],
            "total": job["progress_total"],
        },
        "result": job["result"],
        "error": job["error"],
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
    }


@router.get("/evaluation/results")
@endpoint_guard("get_evaluation_results")
async def get_evaluation_results(request: Request):
    eval_service = getattr(request.app.state, "eval_service", None)
    if eval_service is None:
        logger.info("get_evaluation_results called before eval_service init")
        return {"data": []}
    return await eval_service.get_results()
