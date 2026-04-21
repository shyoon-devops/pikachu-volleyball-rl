"""Idempotent backfill of algorithm on pre-Sprint-4 training_runs.

Mirror of the reward_model / policy_type migration tests for ADR
0017. Also covers the wrapper→manager kwarg forwarding so the full
S4 plumbing stays behaviour-tested in one place (S2/S3 split those
across three files; at this point the contract is stable enough that
the kwarg test reads as a tiny extension of the migration suite).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services.migrations import (
    backfill_training_runs_algorithm,
)
from backend.app.services.training_service import TrainingServiceWrapper


class _FakeUpdateResult:
    def __init__(self, modified: int) -> None:
        self.modified_count = modified


class _FakeCollection:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.calls: list[tuple[dict, dict]] = []

    async def update_many(self, query: dict, update: dict) -> _FakeUpdateResult:
        self.calls.append((query, update))
        assert query == {"algorithm": {"$exists": False}}
        assert update == {"$set": {"algorithm": "ppo"}}
        modified = 0
        for d in self.docs:
            if "algorithm" not in d:
                d["algorithm"] = "ppo"
                modified += 1
        return _FakeUpdateResult(modified)


class _FakeDB:
    def __init__(self, col: _FakeCollection) -> None:
        self._col = col

    def __getitem__(self, name: str) -> _FakeCollection:
        assert name == "training_runs"
        return self._col


class TestBackfillBehavior:
    @pytest.mark.asyncio
    async def test_mongoless_is_noop(self):
        count = await backfill_training_runs_algorithm(None)
        assert count == 0

    @pytest.mark.asyncio
    async def test_sets_algorithm_on_legacy_rows(self):
        col = _FakeCollection([
            {"experiment_id": "exp-1"},
            {"experiment_id": "exp-2"},
        ])
        count = await backfill_training_runs_algorithm(_FakeDB(col))
        assert count == 2
        assert all(d["algorithm"] == "ppo" for d in col.docs)

    @pytest.mark.asyncio
    async def test_preserves_explicit_sac(self):
        """A SAC run inserted after S4 must NOT be overwritten by a
        redeploy backfill — contract is fill missing, not reset."""
        col = _FakeCollection([
            {"experiment_id": "exp-sac", "algorithm": "sac"},
            {"experiment_id": "exp-legacy"},
        ])
        count = await backfill_training_runs_algorithm(_FakeDB(col))
        assert count == 1
        sac = next(d for d in col.docs if d["experiment_id"] == "exp-sac")
        legacy = next(d for d in col.docs if d["experiment_id"] == "exp-legacy")
        assert sac["algorithm"] == "sac"
        assert legacy["algorithm"] == "ppo"


class TestIdempotence:
    @pytest.mark.asyncio
    async def test_second_run_finds_nothing(self):
        col = _FakeCollection([{"experiment_id": "exp-1"}])
        db = _FakeDB(col)

        first = await backfill_training_runs_algorithm(db)
        assert first == 1

        second = await backfill_training_runs_algorithm(db)
        assert second == 0

    @pytest.mark.asyncio
    async def test_third_run_still_idempotent(self):
        col = _FakeCollection([
            {"experiment_id": "exp-a"},
            {"experiment_id": "exp-b", "algorithm": "sac"},
        ])
        db = _FakeDB(col)

        counts = [
            await backfill_training_runs_algorithm(db) for _ in range(3)
        ]
        assert counts == [1, 0, 0]

    @pytest.mark.asyncio
    async def test_exception_swallowed_and_returns_zero(self):
        class _RaisingCol:
            async def update_many(self, *_, **__):
                raise RuntimeError("mongo down")

        class _RaisingDB:
            def __getitem__(self, _):
                return _RaisingCol()

        count = await backfill_training_runs_algorithm(_RaisingDB())
        assert count == 0


class TestRegistrationBackfillParity:
    @pytest.mark.asyncio
    async def test_register_default_matches_migration_default(self):
        from datetime import datetime, timezone

        from backend.app.services.title_service import TrainingRunsService

        inserted: list[dict] = []

        class _Col:
            async def insert_one(self, doc):
                inserted.append(doc)

        svc = TrainingRunsService(db=None)
        svc._col = _Col()
        await svc.register(
            experiment_id="exp-x",
            title="t", slug="t", bot_level=1,
            started_at=datetime.now(timezone.utc),
        )
        assert inserted[0]["algorithm"] == "ppo"


class TestServiceKwargForwarding:
    """Wrapper → manager pass-through (S2/S3 pattern)."""

    @pytest.mark.asyncio
    async def test_default_is_ppo(self, tmp_path):
        w = TrainingServiceWrapper(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        w.manager.start = AsyncMock(return_value="exp-1")
        await w.start()
        assert w.manager.start.await_args.kwargs["algorithm"] == "ppo"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", ["ppo", "sac"])
    async def test_explicit_value_passes_through(self, tmp_path, value):
        w = TrainingServiceWrapper(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        w.manager.start = AsyncMock(return_value="exp-1")
        await w.start(algorithm=value)
        assert w.manager.start.await_args.kwargs["algorithm"] == value

    @pytest.mark.asyncio
    async def test_manager_stores_value_before_thread(self, tmp_path):
        w = TrainingServiceWrapper(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        with patch("threading.Thread") as _MockThread:
            _MockThread.return_value.start = lambda: None
            await w.start(algorithm="sac")
        assert w.manager._algorithm == "sac"

    @pytest.mark.asyncio
    async def test_all_three_selectors_land_independently(self, tmp_path):
        """algorithm + policy_type + reward_model all reach the manager
        without collision."""
        w = TrainingServiceWrapper(
            model_dir=str(tmp_path / "models"),
            replay_dir=str(tmp_path / "replays"),
        )
        with patch("threading.Thread") as _MockThread:
            _MockThread.return_value.start = lambda: None
            await w.start(
                algorithm="sac",
                policy_type="mlp_v1",
                reward_model="sparse_v1",
            )
        assert w.manager._algorithm == "sac"
        assert w.manager._policy_type == "mlp_v1"
        assert w.manager._reward_model == "sparse_v1"


class TestApiSurfacesAlgorithm:
    """``/api/training/runs`` + single-run endpoint carry algorithm."""

    def _seed(self, client, games):
        svc = client.app.state.game_service
        for g in games:
            svc._games.append({"_id": str(len(svc._games)), **g})

    def _base_game(self, **overrides):
        from datetime import datetime, timezone

        base = {
            "game_id": "g1",
            "experiment_id": "exp-a",
            "timestamp": datetime(2026, 4, 22, tzinfo=timezone.utc),
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

    def _fake_runs_service(self, lookup):
        from unittest.mock import AsyncMock, MagicMock

        svc = MagicMock()
        svc.get_by_experiment_ids = AsyncMock(return_value=lookup)
        return svc

    def test_list_endpoint_attaches_algorithm(self, client):
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-a": {"experiment_id": "exp-a", "algorithm": "sac"}
        })
        resp = client.get("/api/training/runs")
        assert resp.status_code == 200
        assert resp.json()["data"][0]["algorithm"] == "sac"

    def test_list_endpoint_defaults_ppo_for_legacy(self, client):
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-a": {"experiment_id": "exp-a"},  # no algorithm
        })
        resp = client.get("/api/training/runs")
        assert resp.json()["data"][0]["algorithm"] == "ppo"

    def test_single_run_endpoint_carries_algorithm(self, client):
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-a": {"experiment_id": "exp-a", "algorithm": "sac"}
        })
        resp = client.get("/api/training/runs/run-alpha")
        assert resp.status_code == 200
        assert resp.json()["algorithm"] == "sac"

    def test_all_selectors_decorate_together(self, client):
        """S2 + S3 + S4 decorations land on the same row — no shadow,
        no collision."""
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-a": {
                "experiment_id": "exp-a",
                "algorithm": "sac",
                "policy_type": "mlp_v1",
                "reward_model": "sparse_v1",
            }
        })
        row = client.get("/api/training/runs").json()["data"][0]
        assert row["algorithm"] == "sac"
        assert row["policy_type"] == "mlp_v1"
        assert row["reward_model"] == "sparse_v1"
