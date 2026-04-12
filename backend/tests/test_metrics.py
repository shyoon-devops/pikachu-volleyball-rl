"""Tests for /api/metrics Prometheus endpoint + infra metric plumbing."""

from __future__ import annotations

from unittest.mock import MagicMock

from prometheus_client import CONTENT_TYPE_LATEST

from backend.app.metrics import (
    GAME_SAVE_FAILURE,
    GAME_SAVE_SUCCESS,
    MONGO_PING_OK,
    QUEUE_CAPACITY,
    QUEUE_DEPTH,
    WS_ACTIVE_CONNECTIONS,
    sample_runtime_metrics,
    update_training_metrics,
)


# --- /api/metrics endpoint ---------------------------------------------------


def test_metrics_endpoint_returns_prometheus_content_type(client):
    r = client.get("/api/metrics")
    assert r.status_code == 200
    # starlette lowercases header names; match against CONTENT_TYPE_LATEST exactly
    assert r.headers["content-type"].startswith(CONTENT_TYPE_LATEST.split(";")[0])


def test_metrics_endpoint_exposes_app_metric_names(client):
    r = client.get("/api/metrics")
    body = r.text
    # Infra gauges
    assert "pikachu_ws_active_connections" in body
    assert "pikachu_mongo_ping_latency_seconds" in body
    assert "pikachu_mongo_ping_ok" in body
    # Queue gauges (labeled)
    assert "pikachu_queue_depth" in body
    assert "pikachu_queue_capacity" in body
    # Counters
    assert "pikachu_game_save_success_total" in body
    assert "pikachu_game_save_failure_total" in body
    # Training gauges
    assert "pikachu_training_step_total" in body
    assert "pikachu_training_episode_total" in body


def test_metrics_endpoint_reports_queue_labels(client):
    r = client.get("/api/metrics")
    body = r.text
    # Each of the three pipeline queues should surface as a labeled series
    assert 'queue="metrics_queue"' in body
    assert 'queue="frames_queue"' in body
    assert 'queue="results_queue"' in body


def test_metrics_endpoint_updates_mongo_ping_gauge(client):
    """Hitting /api/metrics should refresh the mongo_ping_ok gauge from the fake client."""
    # The fake mongo client returns ok, so the gauge should settle to 1.0
    MONGO_PING_OK.set(0)  # force to 0 beforehand to prove the endpoint refreshes it
    r = client.get("/api/metrics")
    assert r.status_code == 200
    assert MONGO_PING_OK._value.get() == 1.0


# --- sample_runtime_metrics --------------------------------------------------


def test_sample_runtime_metrics_reads_ws_count():
    WS_ACTIVE_CONNECTIONS.set(0)
    state = MagicMock()
    ws_manager = MagicMock()
    ws_manager.active_count = 7
    state.ws_manager = ws_manager
    state.training_service = None

    sample_runtime_metrics(state)
    assert WS_ACTIVE_CONNECTIONS._value.get() == 7.0


def test_sample_runtime_metrics_reads_queue_depths():
    state = MagicMock()
    state.ws_manager = None
    manager = MagicMock()
    q1 = MagicMock()
    q1.qsize.return_value = 3
    q1.maxsize = 500
    q2 = MagicMock()
    q2.qsize.return_value = 42
    q2.maxsize = 100
    q3 = MagicMock()
    q3.qsize.return_value = 0
    q3.maxsize = 200
    manager.metrics_queue = q1
    manager.frames_queue = q2
    manager.results_queue = q3
    state.training_service = MagicMock()
    state.training_service.manager = manager

    sample_runtime_metrics(state)

    assert QUEUE_DEPTH.labels(queue="metrics_queue")._value.get() == 3.0
    assert QUEUE_DEPTH.labels(queue="frames_queue")._value.get() == 42.0
    assert QUEUE_DEPTH.labels(queue="results_queue")._value.get() == 0.0
    assert QUEUE_CAPACITY.labels(queue="metrics_queue")._value.get() == 500.0
    assert QUEUE_CAPACITY.labels(queue="frames_queue")._value.get() == 100.0
    assert QUEUE_CAPACITY.labels(queue="results_queue")._value.get() == 200.0


def test_sample_runtime_metrics_handles_missing_state():
    """Absent ws_manager / training_service must not raise."""
    state = MagicMock()
    state.ws_manager = None
    state.training_service = None
    # Should not raise
    sample_runtime_metrics(state)


def test_sample_runtime_metrics_handles_missing_queue_attrs():
    """A manager without all queue attrs should still be handled cleanly."""
    state = MagicMock()
    state.ws_manager = None
    manager = MagicMock()
    # Explicitly omit some queues by setting them to None
    manager.metrics_queue = None
    manager.frames_queue = None
    manager.results_queue = None
    state.training_service = MagicMock()
    state.training_service.manager = manager
    # Should not raise even when queues are absent
    sample_runtime_metrics(state)


# --- Counters: success / failure semantics -----------------------------------


def test_game_save_success_counter_increments_monotonically():
    before = GAME_SAVE_SUCCESS._value.get()
    GAME_SAVE_SUCCESS.inc()
    GAME_SAVE_SUCCESS.inc()
    after = GAME_SAVE_SUCCESS._value.get()
    assert after - before == 2.0


def test_game_save_failure_counter_increments_monotonically():
    before = GAME_SAVE_FAILURE._value.get()
    GAME_SAVE_FAILURE.inc()
    after = GAME_SAVE_FAILURE._value.get()
    assert after - before == 1.0


# --- update_training_metrics -------------------------------------------------


def test_update_training_metrics_populates_gauges():
    update_training_metrics({
        "step": 1000,
        "episode": 50,
        "mean_reward": 12.5,
        "win_rate": 0.42,
        "policy_loss": 0.01,
        "value_loss": 0.2,
    })
    # Rendering should contain the updated values
    from prometheus_client import generate_latest

    body = generate_latest().decode()
    assert "pikachu_training_step_total 1000.0" in body
    assert "pikachu_training_episode_total 50.0" in body
    assert "pikachu_training_mean_reward 12.5" in body


def test_update_training_metrics_tolerates_missing_fields():
    """Partial payloads should not raise — defaults apply."""
    # Should not raise
    update_training_metrics({"step": 10})
    update_training_metrics({})
