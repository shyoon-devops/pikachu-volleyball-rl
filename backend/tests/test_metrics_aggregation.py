"""Tests for MetricsService persistence + aggregation (BE-7).

MetricsService talks to Mongo through ``$dateTrunc``/``$group`` aggregation
pipelines. We don't want to require a running Mongo for unit tests, so we
stand up a ``_FakeAggregationDB`` that captures the pipeline and returns
canned results. The goal is twofold:

  * Verify the **pipeline** we emit — wrong bucket units, a missing timezone
    hint, or a detached ``$match`` stage would all silently corrupt the
    dashboard without the test catching them.
  * Verify the **service contract** — input validation, best-effort
    persistence (never raise into callers), and the sensible-default time
    window when neither ``since`` nor ``until`` is given.

The endpoint tests use the ``FakeMetricsService`` from conftest.py so the
HTTP-layer concerns (query param parsing, cache decorator, 400 on bad
bucket) can be exercised without re-implementing the aggregation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import AutoReconnect

from backend.app.services.metrics_service import (
    MetricsService,
    allowed_buckets,
)


# --- Fake Mongo for MetricsService unit tests -------------------------------


class _FakeCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    async def to_list(self, length: int | None = None) -> list[dict]:
        return self._docs[: length or len(self._docs)]


class _FakeCollection:
    def __init__(self) -> None:
        self.inserted: list[dict] = []
        self.last_pipeline: list[dict] | None = None
        self.aggregate_result: list[dict] = []
        self.insert_one = AsyncMock(side_effect=self._insert_one)

    async def _insert_one(self, doc: dict) -> None:
        self.inserted.append(dict(doc))

    def aggregate(self, pipeline: list[dict]) -> _FakeCursor:
        self.last_pipeline = pipeline
        return _FakeCursor(self.aggregate_result)


class _FakeDB:
    def __init__(self) -> None:
        self.metrics = _FakeCollection()

    def __getitem__(self, name: str) -> _FakeCollection:
        assert name == "metrics", f"MetricsService must only touch 'metrics', got {name!r}"
        return self.metrics


# --- record() behavior ------------------------------------------------------


@pytest.mark.asyncio
async def test_record_stores_experiment_id_and_server_timestamp():
    db = _FakeDB()
    svc = MetricsService(db)  # type: ignore[arg-type]

    payload = {"step": 100, "mean_reward": 1.5, "win_rate": 0.3}
    before = datetime.now(timezone.utc)
    await svc.record(experiment_id="exp-abc", data=payload)
    after = datetime.now(timezone.utc)

    assert len(db.metrics.inserted) == 1
    stored = db.metrics.inserted[0]
    assert stored["experiment_id"] == "exp-abc"
    # Server-side timestamp, within the narrow window we just measured.
    assert before <= stored["timestamp"] <= after
    # Original payload fields survive untouched.
    assert stored["step"] == 100
    assert stored["mean_reward"] == 1.5


@pytest.mark.asyncio
async def test_record_does_not_mutate_caller_dict():
    """Best-effort contract: the push loop reuses dicts; we must not stamp them."""
    db = _FakeDB()
    svc = MetricsService(db)  # type: ignore[arg-type]

    payload = {"step": 5, "mean_reward": 2.0}
    original_keys = set(payload.keys())
    await svc.record(experiment_id="exp", data=payload)

    # The caller's dict must not have picked up server-stamped fields.
    assert set(payload.keys()) == original_keys
    assert "experiment_id" not in payload
    assert "timestamp" not in payload


@pytest.mark.asyncio
async def test_record_swallows_mongo_failure(caplog):
    """A transient Mongo error must not propagate into the push loop."""
    import logging

    db = _FakeDB()
    db.metrics.insert_one = AsyncMock(side_effect=AutoReconnect("mongo down"))
    svc = MetricsService(db)  # type: ignore[arg-type]

    with caplog.at_level(logging.ERROR, logger="backend.app.services.metrics_service"):
        # Must not raise — this is the whole point of the best-effort contract.
        await svc.record(experiment_id="e", data={"step": 1})

    assert any("metrics_record failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_record_tolerates_empty_experiment_id():
    """Metrics produced before a training run is assigned an id still persist."""
    db = _FakeDB()
    svc = MetricsService(db)  # type: ignore[arg-type]

    await svc.record(experiment_id="", data={"step": 0})
    assert db.metrics.inserted[0]["experiment_id"] == ""


# --- aggregate() pipeline ---------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_rejects_unknown_bucket():
    svc = MetricsService(_FakeDB())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown bucket"):
        await svc.aggregate(bucket="7m")


@pytest.mark.asyncio
async def test_aggregate_emits_correct_datetrunc_unit_and_size():
    """The pipeline must carry the right (unit, binSize) pair for each bucket.

    Regression net: a swap of ``5m`` → ``("hour", 5)`` would silently
    return 5-hour buckets labeled as 5-minute ones.
    """
    db = _FakeDB()
    svc = MetricsService(db)  # type: ignore[arg-type]

    cases = {"1m": ("minute", 1), "5m": ("minute", 5), "1h": ("hour", 1)}
    for bucket, (unit, bin_size) in cases.items():
        await svc.aggregate(bucket=bucket)
        # $group stage holds the $dateTrunc spec.
        group = next(s for s in db.metrics.last_pipeline if "$group" in s)
        date_trunc = group["$group"]["_id"]["$dateTrunc"]
        assert date_trunc["unit"] == unit
        assert date_trunc["binSize"] == bin_size
        assert date_trunc["timezone"] == "UTC"


@pytest.mark.asyncio
async def test_aggregate_applies_experiment_id_and_timestamp_filters():
    db = _FakeDB()
    svc = MetricsService(db)  # type: ignore[arg-type]

    since = datetime(2026, 4, 12, 0, 0, tzinfo=timezone.utc)
    until = datetime(2026, 4, 12, 6, 0, tzinfo=timezone.utc)
    await svc.aggregate(experiment_id="exp-1", since=since, until=until)

    match = next(s for s in db.metrics.last_pipeline if "$match" in s)["$match"]
    assert match["experiment_id"] == "exp-1"
    assert match["timestamp"]["$gte"] == since
    assert match["timestamp"]["$lt"] == until


@pytest.mark.asyncio
async def test_aggregate_defaults_to_last_6h_when_no_bounds():
    """Sensible default prevents an unqualified query from scanning the whole collection."""
    db = _FakeDB()
    svc = MetricsService(db)  # type: ignore[arg-type]

    before = datetime.now(timezone.utc)
    await svc.aggregate()
    after = datetime.now(timezone.utc)

    match = next(s for s in db.metrics.last_pipeline if "$match" in s)["$match"]
    # Default window: last 6 hours → since ∈ [before-6h, after-6h].
    lower = match["timestamp"]["$gte"]
    assert (before - timedelta(hours=6)) <= lower <= (after - timedelta(hours=6))
    assert "$lt" not in match["timestamp"]


@pytest.mark.asyncio
async def test_aggregate_returns_projected_docs():
    db = _FakeDB()
    db.metrics.aggregate_result = [
        {
            "bucket_start": datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc),
            "count": 3,
            "step_max": 300,
            "avg_mean_reward": 1.2,
            "avg_win_rate": 0.4,
            "avg_policy_loss": 0.01,
            "avg_value_loss": 0.02,
        }
    ]
    svc = MetricsService(db)  # type: ignore[arg-type]
    result = await svc.aggregate(experiment_id="e", bucket="1m")

    assert result == db.metrics.aggregate_result


def test_allowed_buckets_is_stable_and_complete():
    """If this changes, routes.py Query description and caches must follow."""
    assert allowed_buckets() == ("1m", "5m", "1h")


# --- Endpoint integration (via FakeMetricsService + TestClient) ------------


def test_endpoint_rejects_unknown_bucket(client):
    resp = client.get("/api/training/metrics/aggregate?bucket=17m")
    assert resp.status_code == 400
    assert "Invalid bucket" in resp.json()["detail"]


def test_endpoint_rejects_malformed_since(client):
    resp = client.get("/api/training/metrics/aggregate?since=not-a-timestamp")
    assert resp.status_code == 400
    assert "Invalid since" in resp.json()["detail"]


def test_endpoint_returns_empty_envelope_when_no_metrics(client):
    resp = client.get("/api/training/metrics/aggregate?experiment_id=missing")
    assert resp.status_code == 200
    body = resp.json()
    assert body["experiment_id"] == "missing"
    assert body["bucket"] == "1m"
    assert body["count"] == 0
    assert body["data"] == []


def test_endpoint_returns_bucket_from_recorded_metrics(client, app_instance):
    svc = app_instance.state.metrics_service

    # Seed the in-memory FakeMetricsService directly.
    import asyncio

    async def _seed():
        await svc.record(
            experiment_id="exp-42",
            data={"step": 100, "mean_reward": 1.0, "win_rate": 0.5},
        )
        await svc.record(
            experiment_id="exp-42",
            data={"step": 200, "mean_reward": 2.0, "win_rate": 0.7},
        )

    asyncio.get_event_loop().run_until_complete(_seed())

    resp = client.get("/api/training/metrics/aggregate?experiment_id=exp-42&bucket=1m")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    b = body["data"][0]
    assert b["count"] == 2
    assert b["step_max"] == 200
    assert b["avg_mean_reward"] == pytest.approx(1.5)
    assert b["avg_win_rate"] == pytest.approx(0.6)


def test_endpoint_accepts_z_suffix_iso_timestamp(client):
    resp = client.get("/api/training/metrics/aggregate?bucket=5m&since=2026-04-12T00:00:00Z")
    assert resp.status_code == 200
