"""Tests for the time-series aggregation service + API endpoint."""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.evaluations import get_repository, router
from backend.app.models.evaluation import EvaluationRecord
from backend.app.services.evaluation_repository import EvaluationRepository
from backend.app.services.evaluation_timeseries import (
    SUPPORTED_METRICS,
    TimeSeries,
    TimeSeriesPoint,
    build_timeseries,
)
from backend.tests.fake_mongo import FakeCollection


def _record(
    *,
    id: str = "rec",
    model_path: str = "/models/a.zip",
    bot_level: int = 1,
    win_rate: float = 0.5,
    avg_rally_length: float = 80.0,
    timestamp: str = "2026-04-12T00:00:00+00:00",
    training_step: int | None = None,
    checkpoint_label: str | None = None,
    dominance_score: float = 0.5,
) -> EvaluationRecord:
    return EvaluationRecord(
        id=id,
        model_path=model_path,
        bot_level=bot_level,
        n_games=20,
        win_rate=win_rate,
        avg_score=10.0,
        avg_opponent_score=5.0,
        avg_rally_length=avg_rally_length,
        avg_episode_length=4500.0,
        timestamp=timestamp,
        dominance_score=dominance_score,
        training_step=training_step,
        checkpoint_label=checkpoint_label,
        inserted_at="2026-04-12T01:00:00+00:00",
    )


class TestBuildTimeseries:
    def test_groups_by_model_and_level(self) -> None:
        records = [
            _record(id="1", model_path="/a.zip", bot_level=1),
            _record(id="2", model_path="/a.zip", bot_level=3),
            _record(id="3", model_path="/b.zip", bot_level=1),
        ]
        series = build_timeseries(records, metric="win_rate")
        keys = {(s.model_path, s.bot_level) for s in series}
        assert keys == {("/a.zip", 1), ("/a.zip", 3), ("/b.zip", 1)}

    def test_points_sorted_oldest_first(self) -> None:
        records = [
            _record(id="2", timestamp="2026-04-12T00:00:00+00:00", win_rate=0.9),
            _record(id="1", timestamp="2026-04-10T00:00:00+00:00", win_rate=0.5),
            _record(id="3", timestamp="2026-04-11T00:00:00+00:00", win_rate=0.7),
        ]
        series = build_timeseries(records, metric="win_rate")
        assert len(series) == 1
        timestamps = [p.timestamp for p in series[0].points]
        assert timestamps == sorted(timestamps)
        values = [p.value for p in series[0].points]
        assert values == [0.5, 0.7, 0.9]

    def test_unsupported_metric_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported metric"):
            build_timeseries([_record()], metric="bogus_metric")

    def test_empty_records_returns_empty(self) -> None:
        assert build_timeseries([], metric="win_rate") == []

    def test_respects_metric_selection(self) -> None:
        records = [
            _record(
                id="1",
                avg_rally_length=120.0,
                timestamp="2026-04-10T00:00:00+00:00",
            ),
            _record(
                id="2",
                avg_rally_length=80.0,
                timestamp="2026-04-12T00:00:00+00:00",
            ),
        ]
        series = build_timeseries(records, metric="avg_rally_length")
        assert series[0].metric == "avg_rally_length"
        values = [p.value for p in series[0].points]
        assert values == [120.0, 80.0]

    def test_training_step_and_label_propagate(self) -> None:
        records = [
            _record(training_step=10000, checkpoint_label="step_10k"),
            _record(training_step=20000, checkpoint_label="step_20k"),
        ]
        series = build_timeseries(records, metric="win_rate")
        labels = [p.checkpoint_label for p in series[0].points]
        steps = [p.training_step for p in series[0].points]
        assert "step_10k" in labels and "step_20k" in labels
        assert 10000 in steps and 20000 in steps

    def test_group_by_level_false_collapses_levels(self) -> None:
        records = [
            _record(id="1", bot_level=1),
            _record(id="2", bot_level=3),
            _record(id="3", bot_level=5),
        ]
        series = build_timeseries(records, metric="win_rate", group_by_level=False)
        # All merged into a single series (bot_level key = 0 sentinel)
        assert len(series) == 1
        assert len(series[0].points) == 3

    def test_all_supported_metrics_work(self) -> None:
        for metric in SUPPORTED_METRICS:
            series = build_timeseries([_record()], metric=metric)
            assert len(series) == 1


class TestSerialization:
    def test_timeseries_to_dict_shape(self) -> None:
        ts = TimeSeries(
            model_path="/a.zip",
            bot_level=1,
            metric="win_rate",
            points=[TimeSeriesPoint(timestamp="t", value=0.5)],
        )
        d = ts.to_dict()
        assert d["model_path"] == "/a.zip"
        assert d["bot_level"] == 1
        assert d["metric"] == "win_rate"
        assert d["points"][0]["value"] == 0.5


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    repo = EvaluationRepository(FakeCollection())
    app.dependency_overrides[get_repository] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


def _post(client: TestClient, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "model_path": "/models/a.zip",
        "bot_level": 1,
        "n_games": 20,
        "win_rate": 0.8,
        "avg_score": 10.0,
        "avg_opponent_score": 5.0,
        "avg_rally_length": 80.0,
        "avg_episode_length": 4500.0,
        "timestamp": "2026-04-12T00:00:00+00:00",
    }
    payload.update(overrides)
    resp = client.post("/evaluations", json=payload)
    assert resp.status_code == 201
    return resp.json()


class TestTimeseriesEndpoint:
    def test_returns_empty_when_no_data(self, client: TestClient) -> None:
        resp = client.get("/evaluations/timeseries")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_series_sorted(self, client: TestClient) -> None:
        _post(client, timestamp="2026-04-10T00:00:00+00:00", win_rate=0.5)
        _post(client, timestamp="2026-04-12T00:00:00+00:00", win_rate=0.9)
        resp = client.get("/evaluations/timeseries")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        values = [p["value"] for p in body[0]["points"]]
        assert values == [0.5, 0.9]

    def test_metric_selection(self, client: TestClient) -> None:
        _post(client, avg_rally_length=120.0, timestamp="2026-04-10T00:00:00+00:00")
        _post(client, avg_rally_length=80.0, timestamp="2026-04-12T00:00:00+00:00")
        resp = client.get(
            "/evaluations/timeseries", params={"metric": "avg_rally_length"}
        )
        body = resp.json()
        assert body[0]["metric"] == "avg_rally_length"
        values = [p["value"] for p in body[0]["points"]]
        assert values == [120.0, 80.0]

    def test_rejects_unknown_metric(self, client: TestClient) -> None:
        resp = client.get("/evaluations/timeseries", params={"metric": "bogus"})
        assert resp.status_code == 400

    def test_model_path_filter(self, client: TestClient) -> None:
        _post(client, model_path="/a.zip")
        _post(client, model_path="/b.zip")
        resp = client.get(
            "/evaluations/timeseries", params={"model_path": "/b.zip"}
        )
        body = resp.json()
        assert len(body) == 1
        assert body[0]["model_path"] == "/b.zip"

    def test_bot_level_filter(self, client: TestClient) -> None:
        _post(client, bot_level=1)
        _post(client, bot_level=3)
        resp = client.get(
            "/evaluations/timeseries", params={"bot_level": 3}
        )
        body = resp.json()
        assert [s["bot_level"] for s in body] == [3]

    def test_group_by_level_false(self, client: TestClient) -> None:
        _post(client, bot_level=1, timestamp="2026-04-10T00:00:00+00:00")
        _post(client, bot_level=3, timestamp="2026-04-12T00:00:00+00:00")
        resp = client.get(
            "/evaluations/timeseries", params={"group_by_level": "false"}
        )
        body = resp.json()
        assert len(body) == 1
        assert len(body[0]["points"]) == 2
