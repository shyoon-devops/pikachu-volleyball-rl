"""REST API endpoints — see docs/PLAN.md section 3.1."""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timezone
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


@router.get("/league/standings")
@endpoint_guard("league_standings")
@cache_ttl(seconds=5, max_entries=4, include=("limit",))
async def league_standings(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
):
    """Top-N league pool standings (v2 Sprint-1 B-impl-4).

    Returns a ``LeagueStandings`` envelope: top-N rows by Elo
    (ties broken by games-desc), plus ``champion_id`` /
    ``generation`` / ``pool_size`` / ``total_checkpoints``. See
    docs/adr/0014-self-play-league.md §8 ("API").
    """
    repo = getattr(request.app.state, "league_repository", None)
    if repo is None:
        # Older deployments may not have wired the repository yet —
        # an empty envelope is a better FE experience than a 503
        # because the dashboard can still render the empty state.
        from backend.app.models.league import LEAGUE_POOL_SIZE, LeagueStandings

        return LeagueStandings(
            top=[], champion_id=None, generation=0,
            pool_size=LEAGUE_POOL_SIZE, total_checkpoints=0,
        )
    return await repo.standings_envelope(limit=limit)


@router.get("/league/checkpoint/{checkpoint_id}")
@endpoint_guard("league_checkpoint_detail")
async def league_checkpoint_detail(
    request: Request,
    checkpoint_id: str,
    head_to_head_limit: int = Query(default=10, ge=1, le=100),
):
    """Single checkpoint detail + recent head-to-head summary.

    Head-to-head lookup is served from the ``games`` collection
    (``experiment_id`` filter) — we show the most-recent N matches
    the pool entry participated in. Checkpoint id must be URL-safe
    (Pydantic league schema bounds it at ≤200 chars) so we skip the
    extra path-traversal check.
    """
    if not checkpoint_id or len(checkpoint_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid checkpoint_id")
    repo = getattr(request.app.state, "league_repository", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="League repository not available")
    checkpoint = await repo.get_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    # Head-to-head via games collection — filter by experiment_id
    # (null-safe: anchor rows have no experiment and return []).
    recent_matches: list[dict] = []
    if checkpoint.experiment_id:
        game_service = getattr(request.app.state, "game_service", None)
        if game_service is not None:
            try:
                resp = await game_service.get_games(
                    page=1, limit=head_to_head_limit,
                )
                # Filter to this experiment on the response side —
                # GameService doesn't have an experiment_id filter
                # yet, and the page-1 top-N is bounded so the cost
                # is O(limit) not O(collection).
                recent_matches = [
                    g for g in (resp.data if hasattr(resp, "data") else [])
                    if g.get("experiment_id") == checkpoint.experiment_id
                ][:head_to_head_limit]
            except Exception:  # noqa: BLE001
                logger.exception(
                    "league_checkpoint_detail: h2h lookup failed for %s",
                    checkpoint_id,
                )
    return {
        "checkpoint": checkpoint.model_dump(mode="json"),
        "head_to_head": recent_matches,
    }


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
@cache_ttl(seconds=5, max_entries=64, include=("page", "limit", "title"))
async def list_games(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    title: str | None = Query(default=None, max_length=60),
):
    """List completed games, optionally filtered by title (BE-T5).

    ``title`` — exact-match filter for the drill-down from the
    per-run aggregation view. ``title=untitled`` buckets pre-title
    legacy rows so the FE has a stable click-through.
    """
    game_service = getattr(request.app.state, "game_service", None)
    if game_service is None:
        logger.warning("list_games called but game_service is not initialized")
        raise HTTPException(status_code=503, detail="Game service not available")
    return await game_service.get_games(page=page, limit=limit, title=title)


# Canonical hyperparam shape surfaced alongside each run row
# (BE-T10). Every field is always present — legacy runs that predate
# BE-T10 (no stored hyperparams doc) get the library defaults so the
# FE never has to branch on missing keys. Defaults mirror
# ``backend.rl.trainer.DEFAULT_HYPERPARAMS`` + the service-level
# defaults for the two non-PPO dials (n_envs, total_timesteps).
_RUN_HYPERPARAM_FIELDS: dict[str, Any] = {
    "n_envs": 8,
    "total_timesteps": 2_000_000,
    "learning_rate": 3e-4,
    "n_steps": 2048,
    "batch_size": 64,
    "n_epochs": 10,
    "gamma": 0.99,
    "clip_range": 0.2,
    "ent_coef": 0.01,
    "gae_lambda": 0.95,
}


def _normalize_hyperparams(stored: dict[str, Any] | None) -> dict[str, Any]:
    """Return a canonical hyperparam dict for /api/training/runs.

    Missing keys are filled from ``_RUN_HYPERPARAM_FIELDS``, so the FE
    renders a consistent shape for every run regardless of whether
    BE-T10 was live at start time.
    """
    src = stored or {}
    out: dict[str, Any] = {}
    for key, default in _RUN_HYPERPARAM_FIELDS.items():
        val = src.get(key)
        out[key] = val if val is not None else default
    return out


async def _decorate_runs_with_hyperparams(
    request: Request, rows: list[dict[str, Any]]
) -> None:
    """Join hyperparams + reward_model onto each aggregation row in place.

    Bulk ``$in`` lookup so the query cost is O(1) regardless of page
    size. Rows without a training_runs record (pre-T10 games, demo-only
    experiments) get the canonical defaults via normalize so FE never
    sees a missing key. ``reward_model`` (ADR 0015) piggy-backs on the
    same lookup — legacy rows resolve to ``"shaped_v1"`` which also
    matches the migration backfill default, so the FE can't tell a
    pre-S2 row from a v1.0.0-era run explicitly tagged that way.
    """
    runs_service = getattr(request.app.state, "training_runs_service", None)
    exp_ids = [row.get("experiment_id") for row in rows if row.get("experiment_id")]
    lookup: dict[str, dict[str, Any]] = {}
    if runs_service is not None and exp_ids:
        try:
            lookup = await runs_service.get_by_experiment_ids(exp_ids)
        except Exception:  # noqa: BLE001 — degrade to defaults-only
            logger.exception("training_runs hyperparam lookup failed")
    for row in rows:
        exp_id = row.get("experiment_id") or ""
        run_doc = lookup.get(exp_id) or {}
        row["hyperparams"] = _normalize_hyperparams(run_doc.get("hyperparams"))
        row["reward_model"] = run_doc.get("reward_model") or "shaped_v1"


def _overlay_running_status(
    request: Request, rows: list[dict[str, Any]]
) -> None:
    """Flip ``status`` to "running" on the row matching the live title."""
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is None:
        return
    status = training_service.status()
    if status.get("state") != "running":
        return
    live_title = (status.get("title") or "").strip()
    if not live_title:
        return
    for row in rows:
        if (row.get("title") or "") == live_title:
            row["status"] = "running"


@router.get("/training/runs")
@endpoint_guard("training_runs_aggregate")
@cache_ttl(seconds=5, max_entries=16, include=("page", "limit"))
async def list_training_runs(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Per-title training-run aggregates (BE-T4 + BE-T10).

    Powers the history page's 1st-level drill-down view. Delegates
    grouping to MongoDB so a multi-GB ``games`` collection doesn't
    stream into Python. Each row is decorated with a canonical
    ``hyperparams`` sub-object joined from the ``training_runs``
    collection. Status is overlaid with "running" when the row
    matches the live training manager's current title.
    """
    game_service = getattr(request.app.state, "game_service", None)
    if game_service is None:
        raise HTTPException(status_code=503, detail="Game service not available")

    aggregated = await game_service.aggregate_by_title(page=page, limit=limit)
    await _decorate_runs_with_hyperparams(request, aggregated.data)
    _overlay_running_status(request, aggregated.data)
    return aggregated


@router.get("/training/runs/{title}")
@endpoint_guard("training_run_by_title")
async def get_training_run(request: Request, title: str):
    """Single-run drill-down for the FE detail view (BE-T10).

    Returns the same shape as ``/api/training/runs`` entries plus
    the hyperparams join. 404 when no games exist under the title.
    Supports the literal ``"untitled"`` bucket for pre-title rows.
    """
    if not title or len(title) > 60:
        raise HTTPException(status_code=400, detail="Invalid title")
    game_service = getattr(request.app.state, "game_service", None)
    if game_service is None:
        raise HTTPException(status_code=503, detail="Game service not available")

    # Reuse the aggregation to keep win_rate / avg_rally_length math
    # in one place. Page 1/limit large-enough-to-see-anything — but
    # capped so an API caller can't DoS the endpoint by asking for
    # a giant page.
    aggregated = await game_service.aggregate_by_title(page=1, limit=100)
    row = next(
        (r for r in aggregated.data if (r.get("title") or "") == title),
        None,
    )
    if row is None:
        # The aggregation pagination cap may have missed this title —
        # walk subsequent pages until we find it or exhaust the list.
        # In practice the cap should never be hit (total titles <<< 100
        # in single-user dev setups) but we handle it for correctness.
        page_ix = 2
        while row is None and (page_ix - 1) * 100 < aggregated.total:
            more = await game_service.aggregate_by_title(page=page_ix, limit=100)
            row = next(
                (r for r in more.data if (r.get("title") or "") == title),
                None,
            )
            page_ix += 1
    if row is None:
        raise HTTPException(status_code=404, detail="Training run not found")

    await _decorate_runs_with_hyperparams(request, [row])
    _overlay_running_status(request, [row])
    return row


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


def _parse_checkpoint_filename(stem: str) -> tuple[str | None, int | None]:
    """Return ``(slug, step)`` parsed from a ``{slug}__{exp8}__{step}`` stem.

    Legacy files (``{exp_id}/final``, ``{exp_id}/200000``) have no
    double-underscore marker and return ``(None, None)``. The ``step``
    segment can be either an int string or the literal ``"final"`` —
    we coerce ``"final"`` to a sentinel large-but-finite integer so it
    always sorts above numbered checkpoints for the UI "latest" view.
    """
    parts = stem.split("__")
    if len(parts) < 3:
        return None, None
    slug = parts[0] or None
    step_str = parts[-1]
    if step_str == "final":
        # Finite sentinel — large enough to win a ``key=step desc``
        # sort against any real step value we'd actually train to.
        return slug, 10**12
    try:
        return slug, int(step_str)
    except ValueError:
        return slug, None


@router.get("/models")
@endpoint_guard("list_models")
@cache_ttl(seconds=10, max_entries=8, include=("title", "limit"))
async def list_models(
    title: str | None = Query(default=None, max_length=60),
    limit: int | None = Query(default=None, ge=1, le=500),
):
    """List model checkpoints, optionally filtered by training title (BE-T8).

    Without ``title``: returns every ``*.zip`` under ``MODEL_DIR`` with
    the legacy ``{path, size_bytes}`` shape plus the new enriched
    fields (``filename``, ``slug``, ``step``, ``created_at``, ``title``).
    Legacy callers that only read ``path`` / ``size_bytes`` keep working.

    With ``title``: returns ONLY checkpoints whose filename slug
    matches ``slugify(title)``. Sorted by ``step`` desc (latest first)
    per the drill-down spec. Unparseable filenames are excluded from
    the filtered response.
    """
    from backend.app.services.title_service import slugify

    model_dir = Path(os.getenv("MODEL_DIR", "./models")).resolve()
    if not model_dir.exists():
        logger.info("list_models: model_dir missing (%s)", model_dir)
        return {"models": []}
    try:
        files = list(model_dir.rglob("*.zip"))
    except OSError:
        logger.exception("list_models: failed to scan model_dir=%s", model_dir)
        raise HTTPException(status_code=500, detail="Failed to read model directory")
    # Defensive: a ``.zip`` symlinked outside the model dir would be a
    # path-traversal smell. Exclude it.
    safe_files = [f for f in files if str(f.resolve()).startswith(str(model_dir))]

    filter_slug: str | None = None
    if title is not None:
        filter_slug = slugify(title)

    rows: list[dict[str, Any]] = []
    for f in safe_files:
        stat = f.stat()
        slug, step = _parse_checkpoint_filename(f.stem)
        if filter_slug is not None and slug != filter_slug:
            continue
        rows.append({
            # Backward-compat fields for callers that haven't migrated.
            "path": str(f.relative_to(model_dir)),
            "size_bytes": stat.st_size,
            # Enriched fields (BE-T8).
            "filename": f.name,
            "slug": slug,
            # Surfaced as ``title`` for the FE drill-down — this is the
            # slug extracted from the filename, not the original user
            # title. Good enough for the evaluation dialog's label.
            "title": slug,
            "step": step,
            "created_at": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        })

    if filter_slug is not None:
        # Drill-down view: newest-step-first. Rows whose step didn't
        # parse go to the tail so the UI can still render them.
        rows.sort(key=lambda r: (r["step"] is None, -(r["step"] or 0)))
    else:
        # Default view keeps the old mtime-desc ordering so the
        # evaluation dialog's "latest model" dropdown stays stable.
        rows.sort(
            key=lambda r: r.get("created_at") or "",
            reverse=True,
        )
    if limit is not None:
        rows = rows[:limit]
    return {"models": rows}


class DeleteModelsRequest(BaseModel):
    """Bulk-delete request body for ``DELETE /api/models`` (BE-T9)."""

    # Capped at 100 so a stray loop on the FE can't issue an arbitrarily
    # large delete. Empty list is accepted (no-op) so the FE can replay
    # the last request idempotently after a network blip.
    paths: list[str] = Field(default_factory=list, max_length=100)


@router.delete("/models")
@endpoint_guard("delete_models")
async def delete_models(request: Request, body: DeleteModelsRequest):
    """Bulk-delete checkpoint files under ``MODEL_DIR`` (BE-T9).

    Per-path validation:
      * Must resolve inside ``MODEL_DIR`` (path-traversal rejection).
      * Must not be the active training run's experiment directory
        (returns 409 for the whole request — "fail loud, fail early"
        so the UI shows the user exactly which run is protected).
      * File must exist — missing paths appear in ``failed`` as
        ``reason="not_found"``.
      * Symlinks resolved, never followed outside ``MODEL_DIR``.

    Response shape:
      { "deleted": ["a.zip", "b.zip"],
        "failed":  [{"path": "c.zip", "reason": "..."}] }
    """
    model_dir = Path(os.getenv("MODEL_DIR", "./models")).resolve()

    # Active-training protection. If ANY requested path points into
    # the running experiment's directory, reject the WHOLE batch with
    # 409 — FE can then re-surface the list minus the protected rows.
    # Deliberately coarse: protecting individual files inside the
    # active dir is still racy (the training thread may write a new
    # checkpoint between our check and the unlink), so the safe
    # boundary is the directory.
    training_service = getattr(request.app.state, "training_service", None)
    active_exp_dir: Path | None = None
    if training_service is not None:
        status = training_service.status()
        if status.get("state") == "running":
            active_exp_id = status.get("experiment_id") or ""
            if active_exp_id:
                active_exp_dir = (model_dir / active_exp_id).resolve()

    # Two-pass: resolve + validate every path first so a protected
    # entry can abort the batch before any ``unlink`` runs. Partial
    # deletion before a 409 would be worse than useless — the user
    # couldn't tell from the response which files are still on disk.
    resolved: list[tuple[str, Path]] = []
    failed: list[dict[str, str]] = []
    protected: list[str] = []

    for raw_path in body.paths:
        rel = (raw_path or "").strip()
        if not rel:
            failed.append({"path": raw_path, "reason": "empty_path"})
            continue
        # Strip any leading ``models/`` the FE may have supplied so
        # the UX matches the ``path`` field /api/models returns.
        if rel.startswith(("models/", "./models/")):
            rel = rel.split("models/", 1)[1]

        try:
            target = (model_dir / rel).resolve()
        except (OSError, ValueError):
            failed.append({"path": raw_path, "reason": "invalid_path"})
            continue

        # Containment check — rejects ``..``, absolute paths escaping
        # the model dir, and symlinks pointing elsewhere.
        try:
            target.relative_to(model_dir)
        except ValueError:
            logger.warning(
                "delete_models: traversal rejected path=%r resolved=%s",
                raw_path, target,
            )
            failed.append({"path": raw_path, "reason": "outside_model_dir"})
            continue

        if active_exp_dir is not None:
            try:
                target.relative_to(active_exp_dir)
                protected.append(raw_path)
                continue
            except ValueError:
                # Not inside the active dir — allowed to delete.
                pass

        resolved.append((raw_path, target))

    if protected:
        logger.info(
            "delete_models: %d path(s) belonged to active run; rejecting batch",
            len(protected),
        )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Refusing to delete checkpoints of an active run",
                "protected": protected,
            },
        )

    deleted: list[str] = []
    for raw_path, target in resolved:
        if not target.exists():
            failed.append({"path": raw_path, "reason": "not_found"})
            continue
        if not target.is_file():
            failed.append({"path": raw_path, "reason": "not_a_file"})
            continue

        try:
            size = target.stat().st_size
            target.unlink()
        except OSError as e:
            logger.exception("delete_models: unlink failed for %s", target)
            failed.append({"path": raw_path, "reason": f"unlink_failed: {e}"})
            continue
        deleted.append(raw_path)
        # Audit trail — INFO level so the operator can reconstruct
        # who deleted what without turning on debug logs.
        logger.info(
            "delete_models: removed %s (%d bytes)",
            target,
            size,
        )

    logger.info(
        "delete_models: deleted=%d failed=%d",
        len(deleted),
        len(failed),
    )
    return {"deleted": deleted, "failed": failed}


class EvalRunRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_path: str
    bot_level: int = Field(default=1, ge=1, le=5)
    n_games: int = Field(default=50, ge=1, le=500)


def _experiment_id_from_model_path(model_path: str) -> str | None:
    """Extract the experiment_id from a model_path (BE-T11).

    ``model_path`` is served as ``{experiment_id}/{slug}__{exp8}__{step}.zip``
    per the T2 checkpoint layout. The first path segment IS the
    experiment_id. Returns ``None`` when the path doesn't match this
    shape (ad-hoc uploads, legacy flat layouts) so the caller can
    degrade gracefully to a title-less record.
    """
    if not model_path:
        return None
    # Normalise back-slashes that might slip in from a Windows client.
    rel = model_path.replace("\\", "/")
    # Strip optional leading ./ and any ``models/`` prefix — the FE may
    # send either form depending on which endpoint it first hit.
    rel = rel.removeprefix("./")
    if rel.startswith("models/"):
        rel = rel.split("models/", 1)[1]
    head, _, _ = rel.partition("/")
    if not head or "." in head:
        # Flat layout like ``final.zip`` — no experiment_id to extract.
        return None
    return head


async def _resolve_training_identity(
    request: Any, model_path: str
) -> tuple[str | None, str | None]:
    """Return ``(title, experiment_id)`` for a model path (BE-T11).

    Used by the evaluation job to denormalise training identity onto
    the saved eval record. Resolution order:

      1. Extract ``experiment_id`` from the path's first segment.
      2. If the live TrainingManager is running that experiment, read
         its ``title`` directly (fastest + handles the in-flight case).
      3. Otherwise look the title up in the ``training_runs``
         collection via ``TrainingRunsService.get_by_experiment_ids``.
      4. Any step missing → ``(None, None)`` so the record is simply
         title-less.
    """
    exp_id = _experiment_id_from_model_path(model_path)
    if exp_id is None:
        return None, None

    # Live-training fast-path.
    training_service = getattr(request.app.state, "training_service", None)
    if training_service is not None:
        try:
            status = training_service.status()
            if (
                status.get("experiment_id") == exp_id
                and (status.get("title") or "")
            ):
                return status["title"], exp_id
        except Exception:  # noqa: BLE001 — defensive; fall through to db
            logger.debug("training_service.status() threw during eval job setup")

    # Persisted lookup for stopped runs.
    runs_service = getattr(request.app.state, "training_runs_service", None)
    if runs_service is None:
        return None, exp_id
    try:
        lookup = await runs_service.get_by_experiment_ids([exp_id])
    except Exception:  # noqa: BLE001
        logger.exception("training_runs lookup failed for exp=%s", exp_id)
        return None, exp_id
    doc = lookup.get(exp_id)
    if doc is None:
        return None, exp_id
    return (doc.get("title") or None), exp_id


async def _run_evaluation_job(
    job_id: str,
    eval_service: Any,
    body: EvalRunRequest,
    loop: asyncio.AbstractEventLoop,
    training_title: str | None = None,
    experiment_id: str | None = None,
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
                training_title=training_title,
                experiment_id=experiment_id,
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

    # Resolve training identity SYNCHRONOUSLY before accepting the job
    # (BE-T11): the POST returns 202 immediately, so the background
    # task can't ask the event-loop to read request.app.state once the
    # request context is gone.
    training_title, experiment_id = await _resolve_training_identity(
        request, body.model_path
    )

    job_id = await _eval_jobs.create()
    loop = asyncio.get_running_loop()
    # Detach the task — we never await it; the response must return now
    # so nginx's upstream timeout does not eat the HTTP connection.
    asyncio.create_task(
        _run_evaluation_job(
            job_id, eval_service, body, loop,
            training_title=training_title,
            experiment_id=experiment_id,
        ),
        name=f"eval-job-{job_id}",
    )
    logger.info(
        "eval job %s accepted model=%s bot_level=%d n_games=%d title=%s",
        job_id, body.model_path, body.bot_level, body.n_games, training_title,
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


async def _backfill_eval_titles(
    request: Request, docs: list[dict[str, Any]]
) -> None:
    """Populate ``title`` on legacy evaluation docs in place (BE-T12).

    Legacy docs (saved before BE-T11) have no ``title`` / no
    ``experiment_id``. We extract ``experiment_id`` from ``model_path``
    where we can, bulk-lookup the ``training_runs`` collection in one
    round-trip, and inject ``title`` (+ ``experiment_id`` for good
    measure) on the response dict so the FE's title-filter matches.

    Runs AFTER ``eval_service.get_results()`` so a db outage on the
    runs-service path degrades to "no title on legacy rows" rather
    than breaking the whole endpoint.
    """
    # Figure out which docs actually need backfill.
    needs: list[tuple[dict[str, Any], str]] = []  # (doc, exp_id)
    for d in docs:
        if d.get("title") or d.get("training_title"):
            # Already has a title snapshot — nothing to backfill.
            continue
        exp_id = d.get("experiment_id") or _experiment_id_from_model_path(
            d.get("model_path", "")
        )
        if exp_id:
            needs.append((d, exp_id))
            # Surface exp_id on the doc too so the FE can cross-link
            # without re-parsing model_path on its side.
            d.setdefault("experiment_id", exp_id)

    if not needs:
        return
    runs_service = getattr(request.app.state, "training_runs_service", None)
    if runs_service is None:
        return

    exp_ids = list({exp_id for _, exp_id in needs})
    try:
        lookup = await runs_service.get_by_experiment_ids(exp_ids)
    except Exception:  # noqa: BLE001
        logger.exception(
            "evaluation title backfill: training_runs lookup failed for %d exp(s)",
            len(exp_ids),
        )
        return

    for doc, exp_id in needs:
        run_doc = lookup.get(exp_id)
        if run_doc is None:
            continue
        title = run_doc.get("title")
        if title:
            doc["title"] = title
            # Keep ``training_title`` aligned for readers keying off it.
            doc.setdefault("training_title", title)


@router.get("/evaluation/results")
@endpoint_guard("get_evaluation_results")
async def get_evaluation_results(request: Request):
    """List recent evaluations; legacy rows get ``title`` backfilled (BE-T12).

    Backfill walks rows missing ``title`` / ``training_title``, pulls
    the source training's title from the ``training_runs`` collection
    via the experiment_id (either stored on the row or parsed from
    ``model_path``), and mutates the response dict in place so the
    FE's title filter matches. Degrades to "no title" on lookup
    failures — never blocks the endpoint.
    """
    eval_service = getattr(request.app.state, "eval_service", None)
    if eval_service is None:
        logger.info("get_evaluation_results called before eval_service init")
        return {"data": []}
    response = await eval_service.get_results()
    docs = response.get("data") or []
    if isinstance(docs, list):
        await _backfill_eval_titles(request, docs)
    return response
