"""Idempotent backfill of reward_model on pre-v2.x training_runs (S2).

The migration runs once per process at lifespan startup. These tests
drive it against a fake Mongo collection so they run without a live
instance, matching the rest of the suite's Mongo-less posture.
"""

from __future__ import annotations

import pytest

from backend.app.services.migrations import (
    backfill_training_runs_reward_model,
)


class _FakeUpdateResult:
    def __init__(self, modified: int) -> None:
        self.modified_count = modified


class _FakeCollection:
    """Tiny stand-in for a Motor collection's ``update_many``.

    Tracks filters + updates so the test can assert on the query
    shape, and flips ``reward_model`` on matching docs so a second
    call finds nothing to do (idempotence check).
    """

    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.calls: list[tuple[dict, dict]] = []

    async def update_many(self, query: dict, update: dict) -> _FakeUpdateResult:
        self.calls.append((query, update))
        # Only the "$exists: False" filter path is exercised here; any
        # other filter shape means the migration grew and the test
        # should grow with it.
        assert query == {"reward_model": {"$exists": False}}
        assert update == {"$set": {"reward_model": "shaped_v1"}}
        modified = 0
        for d in self.docs:
            if "reward_model" not in d:
                d["reward_model"] = "shaped_v1"
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
        """db=None → return 0 without touching anything."""
        count = await backfill_training_runs_reward_model(None)
        assert count == 0

    @pytest.mark.asyncio
    async def test_sets_reward_model_on_legacy_rows(self):
        col = _FakeCollection([
            {"experiment_id": "exp-1"},
            {"experiment_id": "exp-2"},
        ])
        db = _FakeDB(col)
        count = await backfill_training_runs_reward_model(db)
        assert count == 2
        assert all(d["reward_model"] == "shaped_v1" for d in col.docs)

    @pytest.mark.asyncio
    async def test_preserves_explicit_values(self):
        """A row that already carries a non-default value must NOT be
        overwritten — otherwise a subsequent backfill after an opt-in
        sparse run would silently revert it to shaped_v1."""
        col = _FakeCollection([
            {"experiment_id": "exp-sparse", "reward_model": "sparse_v1"},
            {"experiment_id": "exp-legacy"},
        ])
        db = _FakeDB(col)
        count = await backfill_training_runs_reward_model(db)
        assert count == 1
        sparse = next(d for d in col.docs if d["experiment_id"] == "exp-sparse")
        legacy = next(d for d in col.docs if d["experiment_id"] == "exp-legacy")
        assert sparse["reward_model"] == "sparse_v1"
        assert legacy["reward_model"] == "shaped_v1"


class TestIdempotence:
    @pytest.mark.asyncio
    async def test_second_run_finds_nothing(self):
        """Re-running after completion must be a no-op (modified=0)."""
        col = _FakeCollection([{"experiment_id": "exp-1"}])
        db = _FakeDB(col)

        first = await backfill_training_runs_reward_model(db)
        assert first == 1

        second = await backfill_training_runs_reward_model(db)
        assert second == 0

    @pytest.mark.asyncio
    async def test_third_run_still_idempotent(self):
        """N consecutive invocations all match the same 0-count result
        after the first."""
        col = _FakeCollection([
            {"experiment_id": "exp-a"},
            {"experiment_id": "exp-b", "reward_model": "learned_shaped_v1"},
        ])
        db = _FakeDB(col)

        counts = [
            await backfill_training_runs_reward_model(db) for _ in range(3)
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

        count = await backfill_training_runs_reward_model(_RaisingDB())
        assert count == 0


class TestApiSurfacesRewardModel:
    """/api/training/runs + single-run endpoint carry the decorated
    reward_model so the FE can render which reward function a run
    used without a separate fetch."""

    def _seed(self, client, games):
        svc = client.app.state.game_service
        for g in games:
            svc._games.append({"_id": str(len(svc._games)), **g})

    def _base_game(self, **overrides):
        from datetime import datetime, timezone

        base = {
            "game_id": "g1",
            "experiment_id": "exp-a",
            "timestamp": datetime(2026, 4, 20, tzinfo=timezone.utc),
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

    def test_list_endpoint_attaches_reward_model(self, client):
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-a": {
                "experiment_id": "exp-a",
                "reward_model": "sparse_v1",
            }
        })
        resp = client.get("/api/training/runs")
        assert resp.status_code == 200
        row = resp.json()["data"][0]
        assert row["reward_model"] == "sparse_v1"

    def test_list_endpoint_defaults_shaped_v1_for_legacy(self, client):
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-a": {"experiment_id": "exp-a"},  # no reward_model
        })
        resp = client.get("/api/training/runs")
        assert resp.json()["data"][0]["reward_model"] == "shaped_v1"

    def test_single_run_endpoint_carries_reward_model(self, client):
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-a": {
                "experiment_id": "exp-a",
                "reward_model": "learned_shaped_v1",
            }
        })
        resp = client.get("/api/training/runs/run-alpha")
        assert resp.status_code == 200
        assert resp.json()["reward_model"] == "learned_shaped_v1"


class TestRegistrationBackfillParity:
    """The ``TrainingRunsService.register`` default MUST match the
    migration's backfill value — otherwise a run inserted without the
    kwarg would look different from a backfilled legacy row."""

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
        assert inserted[0]["reward_model"] == "shaped_v1"
