"""Idempotent backfill of policy_type on pre-Sprint-3 training_runs.

Mirror of ``test_reward_model_migration.py`` for ADR 0016 §9. The
backfill runs at lifespan startup; these tests exercise the backfill
function against a fake Mongo collection so the suite stays Mongo-
less.
"""

from __future__ import annotations

import pytest

from backend.app.services.migrations import (
    backfill_training_runs_policy_type,
)


class _FakeUpdateResult:
    def __init__(self, modified: int) -> None:
        self.modified_count = modified


class _FakeCollection:
    """Matches the shape the migration uses: one ``update_many`` call."""

    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.calls: list[tuple[dict, dict]] = []

    async def update_many(self, query: dict, update: dict) -> _FakeUpdateResult:
        self.calls.append((query, update))
        # Contract: only the "$exists: False" filter path is valid.
        assert query == {"policy_type": {"$exists": False}}
        assert update == {"$set": {"policy_type": "mlp_v1"}}
        modified = 0
        for d in self.docs:
            if "policy_type" not in d:
                d["policy_type"] = "mlp_v1"
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
        count = await backfill_training_runs_policy_type(None)
        assert count == 0

    @pytest.mark.asyncio
    async def test_sets_policy_type_on_legacy_rows(self):
        col = _FakeCollection([
            {"experiment_id": "exp-1"},
            {"experiment_id": "exp-2"},
        ])
        count = await backfill_training_runs_policy_type(_FakeDB(col))
        assert count == 2
        assert all(d["policy_type"] == "mlp_v1" for d in col.docs)

    @pytest.mark.asyncio
    async def test_preserves_explicit_values(self):
        """A row that already opts into lstm_v1 must NOT be overwritten
        — the migration's contract is to fill missing fields, not to
        reset deliberately-set ones."""
        col = _FakeCollection([
            {"experiment_id": "exp-lstm", "policy_type": "lstm_v1"},
            {"experiment_id": "exp-legacy"},
        ])
        count = await backfill_training_runs_policy_type(_FakeDB(col))
        assert count == 1
        lstm = next(d for d in col.docs if d["experiment_id"] == "exp-lstm")
        legacy = next(d for d in col.docs if d["experiment_id"] == "exp-legacy")
        assert lstm["policy_type"] == "lstm_v1"
        assert legacy["policy_type"] == "mlp_v1"

    @pytest.mark.asyncio
    async def test_reserved_values_preserved(self):
        """Reserved values (``gru_v1`` / ``transformer_v1``) survive the
        backfill — they'll be runtime-gated by the trainer, not by data
        rewriting."""
        col = _FakeCollection([
            {"experiment_id": "exp-gru", "policy_type": "gru_v1"},
            {"experiment_id": "exp-tfm", "policy_type": "transformer_v1"},
            {"experiment_id": "exp-legacy"},
        ])
        count = await backfill_training_runs_policy_type(_FakeDB(col))
        assert count == 1
        gru = next(d for d in col.docs if d["experiment_id"] == "exp-gru")
        tfm = next(d for d in col.docs if d["experiment_id"] == "exp-tfm")
        assert gru["policy_type"] == "gru_v1"
        assert tfm["policy_type"] == "transformer_v1"


class TestIdempotence:
    @pytest.mark.asyncio
    async def test_second_run_finds_nothing(self):
        col = _FakeCollection([{"experiment_id": "exp-1"}])
        db = _FakeDB(col)

        first = await backfill_training_runs_policy_type(db)
        assert first == 1

        second = await backfill_training_runs_policy_type(db)
        assert second == 0

    @pytest.mark.asyncio
    async def test_third_run_still_idempotent(self):
        col = _FakeCollection([
            {"experiment_id": "exp-a"},
            {"experiment_id": "exp-b", "policy_type": "lstm_v1"},
        ])
        db = _FakeDB(col)

        counts = [
            await backfill_training_runs_policy_type(db) for _ in range(3)
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

        count = await backfill_training_runs_policy_type(_RaisingDB())
        assert count == 0


class TestRegistrationBackfillParity:
    """The ``TrainingRunsService.register`` default MUST match the
    migration's backfill value — otherwise a fresh run without the
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
        assert inserted[0]["policy_type"] == "mlp_v1"


class TestApiSurfacesPolicyType:
    """``/api/training/runs`` + single-run endpoint attach policy_type
    via the shared decoration helper (mirrors S2 reward_model API
    test)."""

    def _seed(self, client, games):
        svc = client.app.state.game_service
        for g in games:
            svc._games.append({"_id": str(len(svc._games)), **g})

    def _base_game(self, **overrides):
        from datetime import datetime, timezone

        base = {
            "game_id": "g1",
            "experiment_id": "exp-a",
            "timestamp": datetime(2026, 4, 21, tzinfo=timezone.utc),
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

    def test_list_endpoint_attaches_policy_type(self, client):
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-a": {
                "experiment_id": "exp-a",
                "policy_type": "lstm_v1",
            }
        })
        resp = client.get("/api/training/runs")
        assert resp.status_code == 200
        row = resp.json()["data"][0]
        assert row["policy_type"] == "lstm_v1"

    def test_list_endpoint_defaults_mlp_v1_for_legacy(self, client):
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-a": {"experiment_id": "exp-a"},  # no policy_type
        })
        resp = client.get("/api/training/runs")
        assert resp.json()["data"][0]["policy_type"] == "mlp_v1"

    def test_single_run_endpoint_carries_policy_type(self, client):
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-a": {
                "experiment_id": "exp-a",
                "policy_type": "gru_v1",
            }
        })
        resp = client.get("/api/training/runs/run-alpha")
        assert resp.status_code == 200
        assert resp.json()["policy_type"] == "gru_v1"

    def test_both_selectors_decorate_together(self, client):
        """S2 reward_model + S3 policy_type ride the same decoration
        pass — neither clobbers the other."""
        self._seed(client, [self._base_game()])
        client.app.state.training_runs_service = self._fake_runs_service({
            "exp-a": {
                "experiment_id": "exp-a",
                "reward_model": "sparse_v1",
                "policy_type": "lstm_v1",
            }
        })
        resp = client.get("/api/training/runs")
        row = resp.json()["data"][0]
        assert row["reward_model"] == "sparse_v1"
        assert row["policy_type"] == "lstm_v1"
