"""Prometheus metrics — FastAPI instrumentation + custom app gauges.

Exposed at /api/metrics (see routes.py) in Prometheus text-exposition format.
The instrumentator also publishes HTTP-level metrics under /metrics for the
devops scrape config.
"""

from __future__ import annotations

import logging
from typing import Any

from prometheus_client import Counter, Gauge, Info
from prometheus_fastapi_instrumentator import Instrumentator

logger = logging.getLogger(__name__)

# --- Training metrics (updated by the metrics push loop) ---------------------

TRAINING_STEP = Gauge(
    "pikachu_training_step_total",
    "Current training timestep",
)
TRAINING_EPISODE = Gauge(
    "pikachu_training_episode_total",
    "Number of completed episodes",
)
TRAINING_MEAN_REWARD = Gauge(
    "pikachu_training_mean_reward",
    "Mean episode reward (rolling 100)",
)
TRAINING_WIN_RATE = Gauge(
    "pikachu_training_win_rate",
    "Win rate against bot (rolling 100)",
)
TRAINING_POLICY_LOSS = Gauge(
    "pikachu_training_policy_loss",
    "PPO policy gradient loss",
)
TRAINING_VALUE_LOSS = Gauge(
    "pikachu_training_value_loss",
    "PPO value function loss",
)
TRAINING_STATE = Info(
    "pikachu_training",
    "Training run metadata",
)

# --- Infrastructure metrics --------------------------------------------------

WS_ACTIVE_CONNECTIONS = Gauge(
    "pikachu_ws_active_connections",
    "Current number of live WebSocket clients",
)

GAME_SAVE_SUCCESS = Counter(
    "pikachu_game_save_success_total",
    "Game-result save operations that succeeded",
)

GAME_SAVE_FAILURE = Counter(
    "pikachu_game_save_failure_total",
    "Game-result save operations that hit the dead-letter sink",
)

MONGO_PING_LATENCY = Gauge(
    "pikachu_mongo_ping_latency_seconds",
    "Latest MongoDB ping latency in seconds",
)

MONGO_PING_OK = Gauge(
    "pikachu_mongo_ping_ok",
    "1 if the most recent MongoDB ping succeeded, else 0",
)

QUEUE_DEPTH = Gauge(
    "pikachu_queue_depth",
    "Current depth of a training pipeline queue",
    labelnames=("queue",),
)

QUEUE_CAPACITY = Gauge(
    "pikachu_queue_capacity",
    "Configured maxsize of a training pipeline queue",
    labelnames=("queue",),
)


def update_training_metrics(metrics: dict) -> None:
    """Called from the WebSocket metrics push loop to sync Prometheus gauges."""
    TRAINING_STEP.set(metrics.get("step", 0))
    TRAINING_EPISODE.set(metrics.get("episode", 0))
    TRAINING_MEAN_REWARD.set(metrics.get("mean_reward", 0.0))
    TRAINING_WIN_RATE.set(metrics.get("win_rate", 0.0))
    TRAINING_POLICY_LOSS.set(metrics.get("policy_loss", 0.0))
    TRAINING_VALUE_LOSS.set(metrics.get("value_loss", 0.0))


def sample_runtime_metrics(app_state: Any) -> None:
    """Refresh runtime gauges (WS count, queue depths) from live app state.

    Called at /api/metrics request time so the scrape always sees current
    values. Counters are driven by event paths (save/failure callers) and
    are never reset here.
    """
    ws_manager = getattr(app_state, "ws_manager", None)
    if ws_manager is not None:
        try:
            WS_ACTIVE_CONNECTIONS.set(ws_manager.active_count)
        except Exception:
            logger.exception("Failed to sample WS active_count")

    training_service = getattr(app_state, "training_service", None)
    manager = getattr(training_service, "manager", None) if training_service else None
    if manager is None:
        return
    for name in ("metrics_queue", "frames_queue", "results_queue"):
        q = getattr(manager, name, None)
        if q is None:
            continue
        try:
            QUEUE_DEPTH.labels(queue=name).set(q.qsize())
            QUEUE_CAPACITY.labels(queue=name).set(q.maxsize or 0)
        except Exception:
            logger.exception("Failed to sample queue %s", name)


def setup_instrumentator(app) -> None:
    """Attach prometheus-fastapi-instrumentator to the app."""
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/api/metrics", "/docs", "/openapi.json"],
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
