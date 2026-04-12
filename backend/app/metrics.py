"""Prometheus metrics — FastAPI instrumentation + custom training gauges."""

from __future__ import annotations

from prometheus_client import Gauge, Info
from prometheus_fastapi_instrumentator import Instrumentator

# --- Custom training metrics (updated by the metrics push loop) ---

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


def update_training_metrics(metrics: dict) -> None:
    """Called from the WebSocket metrics push loop to sync Prometheus gauges."""
    TRAINING_STEP.set(metrics.get("step", 0))
    TRAINING_EPISODE.set(metrics.get("episode", 0))
    TRAINING_MEAN_REWARD.set(metrics.get("mean_reward", 0.0))
    TRAINING_WIN_RATE.set(metrics.get("win_rate", 0.0))
    TRAINING_POLICY_LOSS.set(metrics.get("policy_loss", 0.0))
    TRAINING_VALUE_LOSS.set(metrics.get("value_loss", 0.0))


def setup_instrumentator(app) -> None:
    """Attach prometheus-fastapi-instrumentator to the app."""
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/docs", "/openapi.json"],
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
