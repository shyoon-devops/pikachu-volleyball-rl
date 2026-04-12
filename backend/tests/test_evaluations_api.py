"""Tests for the FastAPI evaluation router."""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.evaluations import get_repository, router
from backend.app.services.evaluation_repository import EvaluationRepository
from backend.tests.fake_mongo import FakeCollection


@pytest.fixture
def app_and_repo() -> Iterator[tuple[FastAPI, EvaluationRepository]]:
    app = FastAPI()
    app.include_router(router)
    repo = EvaluationRepository(FakeCollection())
    app.dependency_overrides[get_repository] = lambda: repo
    yield app, repo
    app.dependency_overrides.clear()


@pytest.fixture
def client(app_and_repo: tuple[FastAPI, EvaluationRepository]) -> TestClient:
    app, _ = app_and_repo
    return TestClient(app)


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
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
    base.update(overrides)
    return base


class TestCreate:
    def test_returns_201_with_record(self, client: TestClient) -> None:
        resp = client.post("/evaluations", json=_payload())
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"]
        assert data["inserted_at"]
        assert data["dominance_score"] is not None

    def test_rejects_invalid_payload(self, client: TestClient) -> None:
        resp = client.post("/evaluations", json=_payload(win_rate=5.0))
        assert resp.status_code == 422

    def test_rejects_extra_fields(self, client: TestClient) -> None:
        payload = _payload()
        payload["mystery"] = 1
        resp = client.post("/evaluations", json=payload)
        assert resp.status_code == 422


class TestList:
    def test_empty_when_no_records(self, client: TestClient) -> None:
        resp = client.get("/evaluations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_records_newest_first(self, client: TestClient) -> None:
        client.post("/evaluations", json=_payload(timestamp="2026-04-10T00:00:00+00:00"))
        client.post("/evaluations", json=_payload(timestamp="2026-04-12T00:00:00+00:00"))
        resp = client.get("/evaluations")
        items = resp.json()
        assert [i["timestamp"] for i in items] == [
            "2026-04-12T00:00:00+00:00",
            "2026-04-10T00:00:00+00:00",
        ]

    def test_filters_by_model_path(self, client: TestClient) -> None:
        client.post("/evaluations", json=_payload(model_path="/a.zip"))
        client.post("/evaluations", json=_payload(model_path="/b.zip"))
        resp = client.get("/evaluations", params={"model_path": "/a.zip"})
        items = resp.json()
        assert len(items) == 1
        assert items[0]["model_path"] == "/a.zip"

    def test_filters_by_bot_level(self, client: TestClient) -> None:
        client.post("/evaluations", json=_payload(bot_level=1))
        client.post("/evaluations", json=_payload(bot_level=3))
        resp = client.get("/evaluations", params={"bot_level": 3})
        items = resp.json()
        assert [i["bot_level"] for i in items] == [3]

    def test_rejects_out_of_range_bot_level(self, client: TestClient) -> None:
        resp = client.get("/evaluations", params={"bot_level": 9})
        assert resp.status_code == 422

    def test_limit_is_bounded(self, client: TestClient) -> None:
        resp = client.get("/evaluations", params={"limit": 99999})
        assert resp.status_code == 422


class TestGet:
    def test_404_when_missing(self, client: TestClient) -> None:
        resp = client.get("/evaluations/does-not-exist")
        assert resp.status_code == 404

    def test_returns_record(self, client: TestClient) -> None:
        created = client.post("/evaluations", json=_payload()).json()
        resp = client.get(f"/evaluations/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]


class TestCheckpoints:
    def test_distinct_model_paths(self, client: TestClient) -> None:
        client.post("/evaluations", json=_payload(model_path="/a.zip", bot_level=1))
        client.post("/evaluations", json=_payload(model_path="/a.zip", bot_level=3))
        client.post("/evaluations", json=_payload(model_path="/b.zip", bot_level=1))
        resp = client.get("/evaluations/checkpoints")
        assert resp.status_code == 200
        assert set(resp.json()) == {"/a.zip", "/b.zip"}


class TestDependencyGuard:
    def test_unconfigured_dependency_raises(self) -> None:
        app = FastAPI()
        app.include_router(router)
        # No override → the default get_repository raises at resolution time
        client = TestClient(app, raise_server_exceptions=True)
        with pytest.raises(RuntimeError, match="not configured"):
            client.get("/evaluations")
