"""WebSocket message handlers and push loops."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket, WebSocketDisconnect

from backend.app.metrics import (
    GAME_SAVE_FAILURE,
    GAME_SAVE_SUCCESS,
    update_training_metrics,
)
from backend.app.models.schemas import (
    WsReplayRequestPayload,
    WsSetLevelPayload,
    WsTrainingStartPayload,
)
from backend.app.ws.validation import (
    ParsedMessage,
    ValidationFailure,
    parse_ws_message,
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
            parsed = parse_ws_message(data)
            if isinstance(parsed, ValidationFailure):
                logger.info(
                    "Rejecting WS message: code=%s message=%s",
                    parsed.code, parsed.message,
                )
                await _send_error(ws, parsed.code, parsed.message)
                continue
            # Heartbeat: clients reply to "ping" with "pong"; update liveness
            # here so the manager can close truly stale connections.
            if parsed.type == "pong":
                manager.record_pong(ws)
                continue
            await _dispatch(ws, parsed, training_service, replay_service, manager)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)


async def _send_error(ws: WebSocket, code: str, message: str) -> None:
    await ws.send_json(
        {"type": "error", "payload": {"code": code, "message": message}}
    )


async def _emit_status(
    ws: WebSocket,
    manager: ConnectionManager | None,
    message: dict[str, Any],
) -> None:
    """Fan out a training:status transition to every connected client.

    Hotfix for BE-6 regression: we previously acked state changes to the
    requesting socket only (``ws.send_json``). After BE-6's parallel-broadcast
    refactor that left other tabs — e.g. a second dashboard open on the same
    session, or FE-8's ``TrainingStateProvider`` mounted in a neighboring
    window — stuck on a stale "stopped" view while training was actually
    running, because they never saw the status frame.

    training:status is a *session-wide* transition; every live client needs
    it. Error rejections like training:error remain per-requester because
    they answer one caller's specific action, not a global state change.

    ``manager`` is typed ``Optional`` only so the function is safe to call
    from tests that exercise ``_dispatch`` without a full lifespan; in
    production ``ws_endpoint`` always supplies it.
    """
    if manager is not None:
        await manager.broadcast(message)
    else:
        # Defensive fallback — keeps the dispatcher usable in isolation
        # without forcing callers to build a ConnectionManager.
        await ws.send_json(message)


async def _dispatch(
    ws: WebSocket,
    msg: ParsedMessage,
    training_service: TrainingServiceWrapper,
    replay_service: ReplayService,
    manager: ConnectionManager | None = None,
) -> None:
    """Route validated messages to the appropriate handler.

    Payloads are already parsed into typed Pydantic models by parse_ws_message,
    so handlers can rely on field presence and type without re-validating.
    """
    if msg.type == "training:start":
        current = training_service.status()
        if current["state"] == "running":
            # Rejection is caller-specific — don't broadcast it.
            await ws.send_json({
                "type": "training:error",
                "payload": {"message": "Training is already running"},
            })
            return
        params: WsTrainingStartPayload = msg.payload  # type: ignore[assignment]
        # If the caller omitted bot_level, carry over the current difficulty
        # from status instead of silently dropping to L1 — the dashboard is
        # the single source of truth for difficulty via training:set_level.
        effective_bot_level = (
            params.bot_level
            if params.bot_level is not None
            else current["bot_level"]
        )
        # Title allocation (BE-T1): caller-supplied title wins if valid
        # and unique; otherwise the server generates one. The final
        # title is surfaced in the training:status broadcast below so
        # the FE can display what actually got allocated.
        from backend.app.services.title_service import (
            TrainingRunsService,
            allocate_title,
            slugify,
        )

        runs_service = getattr(training_service, "runs_service", None)
        # Accept only a real TrainingRunsService instance — MagicMocks
        # from older test harnesses auto-create attributes and would
        # otherwise expose a non-awaitable "service" here. Fall back to
        # a db-less registry so allocate_title still runs (no
        # collision check possible without Mongo — acceptable).
        if not isinstance(runs_service, TrainingRunsService):
            runs_service = TrainingRunsService(db=None)

        final_title = await allocate_title(runs_service, params.title)
        final_slug = slugify(final_title)
        # Extended PPO hyperparams (2026-04-18): n_epochs / ent_coef /
        # gae_lambda are already consumed from the hp dict by
        # ``TrainingManager._train_loop``, but the WS envelope used to
        # expose them only via the free-form ``hyperparams`` blob. Now
        # each has a first-class range-validated field on the payload;
        # merge any supplied top-level field into the hp dict so the
        # trainer path stays a single source of truth and explicit
        # top-level fields win over ``hyperparams``-blob duplicates.
        hp: dict[str, Any] = dict(params.hyperparams or {})
        if params.n_epochs is not None:
            hp["n_epochs"] = params.n_epochs
        if params.ent_coef is not None:
            hp["ent_coef"] = params.ent_coef
        if params.gae_lambda is not None:
            hp["gae_lambda"] = params.gae_lambda
        # n_envs is NOT a PPO ctor arg — it configures make_vec_env, so
        # it travels as a separate kwarg to manager.start (below). None
        # means "use the manager default".
        start_kwargs: dict[str, Any] = {
            "hyperparams": hp,
            "bot_level": effective_bot_level,
            "total_timesteps": params.total_timesteps,
            "title": final_title,
            "slug": final_slug,
        }
        if params.n_envs is not None:
            start_kwargs["n_envs"] = params.n_envs
        experiment_id = await training_service.start(**start_kwargs)
        # Persist the run record (BE-T1) so future uniqueness checks
        # see this title. Best-effort — failure logs but doesn't fail
        # the start; the in-memory manager already knows the title.
        try:
            from datetime import datetime, timezone

            await runs_service.register(
                experiment_id=experiment_id,
                title=final_title,
                slug=final_slug,
                bot_level=effective_bot_level,
                started_at=datetime.now(timezone.utc),
            )
        except Exception:  # noqa: BLE001
            logger.exception("training_runs register failed for %s", experiment_id)
        logger.info(
            "Training started: experiment=%s bot_level=%d title=%s",
            experiment_id, effective_bot_level, final_title,
        )
        await _emit_status(ws, manager, {
            "type": "training:status",
            "payload": {
                "state": "running",
                "experiment_id": experiment_id,
                "title": final_title,
            },
        })

    elif msg.type == "training:stop":
        # User-initiated Stop: pass force=True (see
        # TrainingServiceWrapper.stop docstring). Inspect the result so we
        # don't broadcast a false "stopped" when the manager declined — the
        # previous wrapper dropped this value, which is exactly how QA's
        # "Stop 버튼 클릭해도 학습 안 멈춤" regression leaked to dev.
        result = await training_service.stop(force=True)
        actual_state = training_service.status()["state"]
        logger.info(
            "Training stop requested: stopped=%s reason=%s actual_state=%s",
            result.get("stopped"), result.get("reason"), actual_state,
        )
        await _emit_status(ws, manager, {
            "type": "training:status",
            "payload": {"state": actual_state},
        })

    elif msg.type == "training:pause":
        result = await training_service.pause()
        actual_state = training_service.status()["state"]
        logger.info(
            "Training pause requested: paused=%s reason=%s actual_state=%s",
            result.get("paused"), result.get("reason"), actual_state,
        )
        await _emit_status(ws, manager, {
            "type": "training:status",
            "payload": {"state": actual_state},
        })

    elif msg.type == "training:resume":
        # resume() is overloaded: unpause from paused, or reload checkpoint
        # from stopped. Report the resulting state so every client lands in
        # sync rather than assuming "running" on success.
        try:
            result = await training_service.resume()
        except FileNotFoundError as e:
            logger.info("Resume rejected: no checkpoint available")
            await ws.send_json({
                "type": "training:error",
                "payload": {"message": str(e)},
            })
            return
        actual_state = training_service.status()["state"]
        logger.info(
            "Training resume requested: reason=%s actual_state=%s",
            result.get("reason"), actual_state,
        )
        await _emit_status(ws, manager, {
            "type": "training:status",
            "payload": {"state": actual_state},
        })

    elif msg.type == "training:set_level":
        params_lvl: WsSetLevelPayload = msg.payload  # type: ignore[assignment]
        training_service.set_bot_level(params_lvl.level)
        await _emit_status(ws, manager, {
            "type": "training:status",
            "payload": {
                "state": training_service.status()["state"],
                "bot_level": params_lvl.level,
            },
        })

    elif msg.type == "replay:request":
        params_rep: WsReplayRequestPayload = msg.payload  # type: ignore[assignment]
        frames = await replay_service.load_replay(params_rep.game_id)
        await ws.send_json({"type": "replay:data", "payload": {"frames": frames}})

    elif msg.type == "ping":
        # Server-initiated ping is the usual direction, but accept client pings
        # too — reply with pong so the client can measure round-trip.
        await ws.send_json({"type": "pong", "payload": {}})

    else:
        # Should be unreachable: parse_ws_message rejects unknown types.
        logger.warning("Dispatched unexpected WS message type: %s", msg.type)


async def metrics_push_loop(
    manager: ConnectionManager,
    training_service: TrainingServiceWrapper,
    metrics_service: Any | None = None,
) -> None:
    """Drain metrics queue, persist (if configured), and broadcast.

    Persistence is best-effort and happens *before* the broadcast so a live
    dashboard frame isn't visible ahead of its persisted counterpart — we'd
    rather eat a few milliseconds of latency on a metric frame than create
    a user-visible gap in the aggregation endpoint. MetricsService.record
    swallows its own errors so a Mongo hiccup cannot stall this loop.
    """
    queue = training_service.manager.metrics_queue
    while True:
        data = await queue.get()
        update_training_metrics(data)
        if metrics_service is not None:
            experiment_id = getattr(training_service.manager, "_experiment_id", "") or ""
            await metrics_service.record(experiment_id=experiment_id, data=data)
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


async def env_frames_push_loop(
    manager: ConnectionManager,
    training_service: TrainingServiceWrapper,
) -> None:
    """Drain per-env frame queue and broadcast to all WS clients.

    Separate channel from ``training:frame`` (the demo game) — each
    payload is ``{env_id, frame, score, state_name, step}`` so the FE
    can render all 8 parallel envs side-by-side. Graceful degradation:
    if the manager has no ``env_frames_queue`` attribute (older
    manager, or a test fake), this loop parks idle.
    """
    queue = getattr(training_service.manager, "env_frames_queue", None)
    if queue is None:
        logger.info("env_frames_push_loop: no env_frames_queue attribute; idle")
        return
    while True:
        data = await queue.get()
        await manager.broadcast({"type": "training:env_frame", "payload": data})


SAVE_RETRY_ATTEMPTS = 3
SAVE_RETRY_BASE_DELAY = 0.5  # seconds; doubled each attempt (0.5, 1.0, 2.0)
DEAD_LETTER_PATH = Path(os.getenv("FAILED_RESULTS_PATH", "data/failed_results.jsonl"))


async def _save_with_retry(game_service: Any, record: Any) -> Exception | None:
    """Attempt save_game with exponential backoff. Return last error or None."""
    last_err: Exception | None = None
    for attempt in range(1, SAVE_RETRY_ATTEMPTS + 1):
        try:
            await game_service.save_game(record)
            if attempt > 1:
                logger.info("save_game succeeded on attempt %d", attempt)
            return None
        except Exception as e:  # noqa: BLE001 — we intentionally retry all errors
            last_err = e
            logger.warning(
                "save_game attempt %d/%d failed: %s",
                attempt, SAVE_RETRY_ATTEMPTS, e,
            )
            if attempt < SAVE_RETRY_ATTEMPTS:
                await asyncio.sleep(SAVE_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
    return last_err


def _write_dead_letter(record_data: dict[str, Any], error: str) -> None:
    """Append a failed record to the dead-letter JSONL file."""
    try:
        DEAD_LETTER_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error,
            "record": record_data,
        }
        with DEAD_LETTER_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        # Dead-letter sink is a last resort — do not crash the loop.
        logger.exception("Failed to write dead-letter entry")


async def results_push_loop(
    manager: ConnectionManager,
    training_service: TrainingServiceWrapper,
    game_service: Any,
) -> None:
    """Drain game-result queue, save to DB with retries, and broadcast."""
    from backend.app.models.schemas import GameRecord

    queue = training_service.manager.results_queue
    while True:
        data = await queue.get()
        # bot_level and experiment_id MUST be present on the wire — the
        # producer (LiveFrameCallback._on_step) snapshots both from the
        # TrainingManager before the demo runs. If either is missing we
        # fall through to the exception branch → dead-letter, rather
        # than silently coercing to L1 (the previous default) which
        # masked the "every game saved as L1" regression FE reported.
        if "bot_level" not in data:
            logger.warning(
                "results_push_loop received payload without bot_level "
                "(game_id=%s) — routing to dead-letter",
                data.get("game_id", "?"),
            )
        if "experiment_id" not in data:
            logger.warning(
                "results_push_loop received payload without experiment_id "
                "(game_id=%s) — routing to dead-letter",
                data.get("game_id", "?"),
            )
        try:
            record = GameRecord(
                game_id=data.get("game_id", ""),
                experiment_id=data["experiment_id"],
                bot_level=data["bot_level"],
                score1=data["score1"],
                score2=data["score2"],
                winner=data["winner"],
                duration_frames=data["duration_frames"],
                rally_count=data.get("rally_count", 0),
                # env_id: "demo" for the demo callback; "0".."7" for
                # parallel training envs (BE-A2). Legacy producers that
                # never learned the field are treated as demo — matches
                # pre-A2 behavior since only the demo saved games.
                env_id=data.get("env_id"),
                # Denormalised title snapshot (BE-T1) — empty string
                # from legacy pre-title producers is stored as None so
                # pydantic/serde consumers can render "-" cleanly.
                title=data.get("title") or None,
                # Episode counter snapshot (BE-T6). Absent from legacy
                # payloads; coerced to None so FE "-" fallback kicks in.
                episode=data.get("episode"),
            )
        except Exception as e:
            logger.exception("Invalid game result payload, routing to dead-letter")
            _write_dead_letter(data, f"ValidationError: {e}")
            GAME_SAVE_FAILURE.inc()
            await manager.broadcast({
                "type": "error",
                "payload": {
                    "source": "results_push_loop",
                    "message": "Invalid game result payload, preserved to dead-letter",
                    "game_id": data.get("game_id", ""),
                },
            })
            continue

        err = await _save_with_retry(game_service, record)
        if err is not None:
            logger.error(
                "save_game failed after %d attempts, writing dead-letter (game_id=%s)",
                SAVE_RETRY_ATTEMPTS, record.game_id,
            )
            _write_dead_letter(data, f"{type(err).__name__}: {err}")
            GAME_SAVE_FAILURE.inc()
            await manager.broadcast({
                "type": "error",
                "payload": {
                    "source": "results_push_loop",
                    "message": "Failed to persist game result after retries",
                    "game_id": record.game_id,
                },
            })
        else:
            GAME_SAVE_SUCCESS.inc()
            # BE-T7: emit a structured `training:game_end` frame so the
            # FE history view can prepend this row in real time without
            # re-polling /api/games. Stable subset of the record (the
            # FE documents these fields). Timestamp is stamped here
            # (not from the manager) so it's JSON-ready.
            await manager.broadcast({
                "type": "training:game_end",
                "payload": {
                    "record": {
                        "game_id": record.game_id,
                        "title": record.title,
                        "env_id": record.env_id,
                        "score1": record.score1,
                        "score2": record.score2,
                        "winner": record.winner,
                        "episode": record.episode,
                        "duration_frames": record.duration_frames,
                        "experiment_id": record.experiment_id,
                        "timestamp": (
                            record.timestamp.isoformat()
                            if record.timestamp is not None
                            else None
                        ),
                    },
                },
            })
        await manager.broadcast({"type": "game:result", "payload": data})
