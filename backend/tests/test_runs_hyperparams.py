"""Hyperparams join in /api/training/runs + single-run endpoint (BE-T10)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


def _seed_games(client, games: list[dict]) -> None:
    svc = client.app.state.game_service
    for g in games:
        svc._games.append({"_id": str(len(svc._games)), **g})


def _fake_runs_service(lookup: dict[str, dict]) -> MagicMock:
    """MagicMock TrainingRunsService returning a preset lookup dict."""
    svc = MagicMock()
    svc.get_by_experiment_ids = AsyncMock(return_value=lookup)
    return svc


def _base_game(**overrides) -> dict:
    base = {
        "game_id": "g1",
        "experiment_id": "exp-a",
        "timestamp": datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc),
        "bot_level": 1,
        "score1": 15,
        "score2": 10,
        "winner": 1,
        "duration_frames": 1000,
        "rally_count": 20,
        "title": "run-alpha",
    }
    base.update(overrides)
    return base


class TestRunsHyperparamJoin:
    def test_aggregate_row_includes_hyperparams(self, client):
        _seed_games(client, [_base_game()])
        client.app.state.training_runs_service = _fake_runs_service({
            "exp-a": {
                "experiment_id": "exp-a",
                "hyperparams": {
                    "n_envs": 16,
                    "total_timesteps": 3_000_000,
                    "learning_rate": 1e-4,
                    "n_steps": 1024,
                    "batch_size": 128,
                    "n_epochs": 12,
                    "gamma": 0.995,
                    "clip_range": 0.25,
                    "ent_coef": 0.02,
                    "gae_lambda": 0.97,
                },
            }
        })

        resp = client.get("/api/training/runs")
        assert resp.status_code == 200
        row = resp.json()["data"][0]
        assert row["title"] == "run-alpha"
        hp = row["hyperparams"]
        assert hp == {
            "n_envs": 16,
            "total_timesteps": 3_000_000,
            "learning_rate": 1e-4,
            "n_steps": 1024,
            "batch_size": 128,
            "n_epochs": 12,
            "gamma": 0.995,
            "clip_range": 0.25,
            "ent_coef": 0.02,
            "gae_lambda": 0.97,
        }

    def test_missing_run_doc_uses_defaults(self, client):
        """Legacy runs with no training_runs row still get a canonical shape."""
        _seed_games(client, [_base_game()])
        client.app.state.training_runs_service = _fake_runs_service({})

        resp = client.get("/api/training/runs")
        hp = resp.json()["data"][0]["hyperparams"]
        # Every canonical field is present, filled from library defaults.
        assert set(hp.keys()) == {
            "n_envs", "total_timesteps", "learning_rate",
            "n_steps", "batch_size", "n_epochs",
            "gamma", "clip_range", "ent_coef", "gae_lambda",
        }
        assert hp["n_envs"] == 8
        assert hp["total_timesteps"] == 2_000_000
        assert hp["learning_rate"] == 3e-4
        assert hp["gae_lambda"] == 0.95

    def test_partial_run_doc_fills_remaining_defaults(self, client):
        """Run doc with only some hyperparams — rest default-filled."""
        _seed_games(client, [_base_game()])
        client.app.state.training_runs_service = _fake_runs_service({
            "exp-a": {
                "experiment_id": "exp-a",
                "hyperparams": {"learning_rate": 5e-5, "n_envs": 4},
            }
        })
        resp = client.get("/api/training/runs")
        hp = resp.json()["data"][0]["hyperparams"]
        assert hp["learning_rate"] == 5e-5
        assert hp["n_envs"] == 4
        # Unspecified → default.
        assert hp["total_timesteps"] == 2_000_000
        assert hp["batch_size"] == 64

    def test_lookup_failure_falls_back_to_defaults(self, client):
        _seed_games(client, [_base_game()])
        svc = MagicMock()
        svc.get_by_experiment_ids = AsyncMock(side_effect=RuntimeError("mongo down"))
        client.app.state.training_runs_service = svc

        resp = client.get("/api/training/runs")
        # Still 200 — degraded-to-defaults response rather than 500.
        assert resp.status_code == 200
        hp = resp.json()["data"][0]["hyperparams"]
        assert hp["n_envs"] == 8


class TestRunsSingleEndpoint:
    def test_single_run_returns_same_shape(self, client):
        _seed_games(client, [_base_game()])
        client.app.state.training_runs_service = _fake_runs_service({
            "exp-a": {
                "experiment_id": "exp-a",
                "hyperparams": {"learning_rate": 1e-4},
            }
        })
        resp = client.get("/api/training/runs/run-alpha")
        assert resp.status_code == 200
        body = resp.json()
        # Matches the aggregation entry shape plus hyperparams.
        assert body["title"] == "run-alpha"
        assert body["total_games"] == 1
        assert body["win_rate"] == 1.0
        assert body["hyperparams"]["learning_rate"] == 1e-4
        # Canonical fields always present.
        assert body["hyperparams"]["n_envs"] == 8

    def test_single_run_404_on_unknown_title(self, client):
        _seed_games(client, [_base_game()])
        resp = client.get("/api/training/runs/never-existed")
        assert resp.status_code == 404

    def test_single_run_400_on_oversize_title(self, client):
        resp = client.get("/api/training/runs/" + "x" * 61)
        assert resp.status_code == 400

    def test_single_run_untitled_bucket(self, client):
        """Pre-title legacy rows surface under the ``untitled`` bucket."""
        legacy = _base_game()
        legacy.pop("title")
        _seed_games(client, [legacy])
        resp = client.get("/api/training/runs/untitled")
        assert resp.status_code == 200
        assert resp.json()["title"] == "untitled"


class TestRunsServiceRegistersHyperparams:
    """TrainingRunsService.register persists a hyperparams snapshot."""

    @pytest.mark.asyncio
    async def test_register_stores_hyperparams_dict(self):
        from backend.app.services.title_service import TrainingRunsService

        inserted: list[dict] = []

        class _FakeCol:
            async def insert_one(self, doc):
                inserted.append(doc)

        svc = TrainingRunsService(db=None)
        svc._col = _FakeCol()  # swap in the fake collection after init

        await svc.register(
            experiment_id="exp-xyz",
            title="run-hp",
            slug="run-hp",
            bot_level=2,
            started_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
            hyperparams={
                "n_envs": 4,
                "learning_rate": 1e-4,
            },
        )
        assert len(inserted) == 1
        assert inserted[0]["hyperparams"] == {
            "n_envs": 4,
            "learning_rate": 1e-4,
        }

    @pytest.mark.asyncio
    async def test_register_without_hyperparams_omits_field(self):
        """No hyperparams → no ``hyperparams`` key in the doc."""
        from backend.app.services.title_service import TrainingRunsService

        inserted: list[dict] = []

        class _FakeCol:
            async def insert_one(self, doc):
                inserted.append(doc)

        svc = TrainingRunsService(db=None)
        svc._col = _FakeCol()

        await svc.register(
            experiment_id="exp-a",
            title="t",
            slug="t",
            bot_level=1,
            started_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        )
        assert "hyperparams" not in inserted[0]

    @pytest.mark.asyncio
    async def test_get_by_experiment_ids_bulk_lookup(self):
        from backend.app.services.title_service import TrainingRunsService

        class _FakeCursor:
            def __init__(self, docs):
                self._docs = docs

            async def to_list(self, length):
                return list(self._docs)[:length]

        class _FakeCol:
            def find(self, query, projection=None):
                ids = query["experiment_id"]["$in"]
                return _FakeCursor([
                    {"experiment_id": i, "hyperparams": {"learning_rate": 1e-4}}
                    for i in ids
                    if i in {"exp-1", "exp-3"}
                ])

        svc = TrainingRunsService(db=None)
        svc._col = _FakeCol()

        out = await svc.get_by_experiment_ids(["exp-1", "exp-2", "exp-3"])
        assert set(out.keys()) == {"exp-1", "exp-3"}
        assert out["exp-1"]["hyperparams"]["learning_rate"] == 1e-4
