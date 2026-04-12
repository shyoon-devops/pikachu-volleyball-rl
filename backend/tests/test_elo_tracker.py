"""Tests for the background Elo tracker."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.app.models.evaluation import EvaluationCreate
from backend.app.services.elo_tracker import (
    EloTracker,
    InMemoryEloStore,
    MongoEloStore,
    TickReport,
)
from backend.app.services.evaluation_repository import EvaluationRepository
from backend.rl.elo import BOT_ANCHOR_RATINGS, bot_player_id
from backend.tests.fake_mongo import FakeCollection


def _payload(
    *,
    model_path: str = "/m1",
    bot_level: int = 1,
    win_rate: float = 0.8,
    timestamp: str = "2026-04-12T00:00:00+00:00",
) -> EvaluationCreate:
    return EvaluationCreate(
        model_path=model_path,
        bot_level=bot_level,
        n_games=10,
        win_rate=win_rate,
        avg_score=10.0,
        avg_opponent_score=5.0,
        avg_rally_length=80.0,
        avg_episode_length=4000.0,
        timestamp=timestamp,
        dominance_score=0.6,
    )


@pytest.fixture
def repo() -> EvaluationRepository:
    return EvaluationRepository(FakeCollection())


@pytest.fixture
def store() -> InMemoryEloStore:
    return InMemoryEloStore()


@pytest.fixture
def tracker(repo: EvaluationRepository, store: InMemoryEloStore) -> EloTracker:
    return EloTracker(repo, store)


class TestTickEmpty:
    @pytest.mark.asyncio
    async def test_empty_repo_produces_empty_tick(
        self, tracker: EloTracker
    ) -> None:
        report = await tracker.tick()
        assert report.ok
        assert report.records_applied == 0
        assert report.last_cursor is None


class TestTickIngestion:
    @pytest.mark.asyncio
    async def test_single_record_updates_elo(
        self,
        tracker: EloTracker,
        repo: EvaluationRepository,
    ) -> None:
        await repo.save(_payload(model_path="/m1", win_rate=0.8))
        report = await tracker.tick()
        assert report.records_applied == 1
        ratings = await tracker.get_ratings()
        ids = {r.player_id for r in ratings}
        # Both /m1 and the bot anchors should be present
        assert "/m1" in ids
        assert bot_player_id(1) in ids

    @pytest.mark.asyncio
    async def test_winning_model_rating_rises(
        self,
        tracker: EloTracker,
        repo: EvaluationRepository,
    ) -> None:
        # Equal-rated matchup (L3 anchor = 1500, model default = 1500);
        # 90% win rate → rating goes up.
        await repo.save(_payload(model_path="/strong", bot_level=3, win_rate=0.9))
        await tracker.tick()
        ratings = await tracker.get_ratings()
        strong = next(r for r in ratings if r.player_id == "/strong")
        assert strong.rating > 1500.0

    @pytest.mark.asyncio
    async def test_does_not_double_apply(
        self,
        tracker: EloTracker,
        repo: EvaluationRepository,
    ) -> None:
        await repo.save(_payload(model_path="/m1", win_rate=0.8))
        await tracker.tick()
        first = {r.player_id: r.rating for r in await tracker.get_ratings()}
        # Second tick with no new records should be a no-op.
        report = await tracker.tick()
        assert report.records_applied == 0
        second = {r.player_id: r.rating for r in await tracker.get_ratings()}
        assert first == second

    @pytest.mark.asyncio
    async def test_cursor_advances_only_when_records_processed(
        self,
        tracker: EloTracker,
        repo: EvaluationRepository,
    ) -> None:
        await repo.save(_payload(timestamp="2026-04-10T00:00:00+00:00"))
        first = await tracker.tick()
        assert first.last_cursor == "2026-04-10T00:00:00+00:00"

        # No new records — cursor stays where it is.
        second = await tracker.tick()
        assert second.last_cursor == "2026-04-10T00:00:00+00:00"

        await repo.save(_payload(timestamp="2026-04-12T00:00:00+00:00"))
        third = await tracker.tick()
        assert third.records_applied == 1
        assert third.last_cursor == "2026-04-12T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_records_applied_oldest_first(
        self,
        repo: EvaluationRepository,
        store: InMemoryEloStore,
    ) -> None:
        # Insert records out of chronological order; tracker must apply
        # them oldest-first so the cursor advances monotonically.
        await repo.save(_payload(timestamp="2026-04-12T00:00:00+00:00"))
        await repo.save(_payload(timestamp="2026-04-10T00:00:00+00:00"))
        tracker = EloTracker(repo, store)
        report = await tracker.tick()
        assert report.records_applied == 2
        assert report.last_cursor == "2026-04-12T00:00:00+00:00"


class TestStoreContract:
    @pytest.mark.asyncio
    async def test_anchors_seeded_on_fresh_store(
        self, tracker: EloTracker
    ) -> None:
        await tracker.tick()
        ratings = {r.player_id: r.rating for r in await tracker.get_ratings()}
        for name, expected in BOT_ANCHOR_RATINGS.items():
            assert ratings[name] == expected

    @pytest.mark.asyncio
    async def test_restart_restores_state_from_store(
        self,
        repo: EvaluationRepository,
        store: InMemoryEloStore,
    ) -> None:
        tracker = EloTracker(repo, store)
        await repo.save(_payload(model_path="/persist", win_rate=0.9, bot_level=3))
        await tracker.tick()
        persisted = {r.player_id: r.rating for r in await tracker.get_ratings()}

        # New tracker, same store — should load existing state
        tracker2 = EloTracker(repo, store)
        restored = {r.player_id: r.rating for r in await tracker2.get_ratings()}
        assert persisted == restored


class TestMongoEloStore:
    @pytest.mark.asyncio
    async def test_load_empty_returns_defaults(self) -> None:
        store = MongoEloStore(FakeCollection())
        state, cursor = await store.load()
        assert state == {}
        assert cursor is None

    @pytest.mark.asyncio
    async def test_roundtrip_insert_when_no_update_one(self) -> None:
        # FakeCollection in this repo has no update_one — store should
        # fall back to delete+insert.
        col = FakeCollection()
        store = MongoEloStore(col)
        await store.save({"m": (1500.0, 10)}, cursor="2026-04-12T00:00:00+00:00")
        state, cursor = await store.load()
        assert state == {"m": (1500.0, 10)}
        assert cursor == "2026-04-12T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_save_overwrites_existing(self) -> None:
        store = MongoEloStore(FakeCollection())
        await store.save({"m": (1500.0, 5)}, cursor="t1")
        await store.save({"m": (1600.0, 10)}, cursor="t2")
        state, cursor = await store.load()
        assert state == {"m": (1600.0, 10)}
        assert cursor == "t2"


class TestTickErrorHandling:
    @pytest.mark.asyncio
    async def test_tick_survives_store_failure(
        self,
        repo: EvaluationRepository,
    ) -> None:
        class BoomStore(InMemoryEloStore):
            async def load(self):  # type: ignore[override]
                raise RuntimeError("backend down")

        tracker = EloTracker(repo, BoomStore())
        report = await tracker.tick()
        assert report.ok is False
        assert "RuntimeError" in (report.error or "")


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_runs_tick_and_stop_cancels_loop(
        self,
        repo: EvaluationRepository,
        store: InMemoryEloStore,
    ) -> None:
        await repo.save(_payload(model_path="/loop", win_rate=0.9))

        tick_started = asyncio.Event()
        original_tick_called = asyncio.Event()

        # Fake sleep — blocks until stop is called so the loop runs
        # exactly one tick, records it happened, and then idles.
        async def fake_sleep(_seconds: float) -> None:
            original_tick_called.set()
            # Wait indefinitely; cancel will unblock this.
            await asyncio.Future()

        tracker = EloTracker(repo, store, sleep=fake_sleep)

        # Wrap tick so the test can observe that the loop ran it.
        original_tick = tracker.tick

        async def observed_tick() -> TickReport:
            tick_started.set()
            return await original_tick()

        tracker.tick = observed_tick  # type: ignore[method-assign]

        await tracker.start()
        await asyncio.wait_for(tick_started.wait(), timeout=1.0)
        await asyncio.wait_for(original_tick_called.wait(), timeout=1.0)
        await tracker.stop()
        # After stop, no task is running
        assert tracker._task is None

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(
        self, tracker: EloTracker
    ) -> None:
        await tracker.stop()  # should not raise

    @pytest.mark.asyncio
    async def test_double_start_is_idempotent(
        self, tracker: EloTracker
    ) -> None:
        async def never_wake(_s: float) -> None:
            await asyncio.Future()

        tracker._sleep = never_wake  # type: ignore[assignment]
        await tracker.start()
        first_task = tracker._task
        await tracker.start()
        assert tracker._task is first_task
        await tracker.stop()


class TestRatingEntry:
    def test_to_dict_shape(self) -> None:
        from backend.app.services.elo_tracker import RatingEntry

        e = RatingEntry(player_id="m", rating=1500.1234, games_played=7)
        d = e.to_dict()
        assert d == {"player_id": "m", "rating": 1500.12, "games_played": 7}


class TestMongoEloStoreUpdateOne:
    @pytest.mark.asyncio
    async def test_prefers_update_one_when_available(self) -> None:
        calls: list[dict[str, Any]] = []

        class RecordingCollection:
            async def update_one(
                self,
                filter: dict[str, Any],
                update: dict[str, Any],
                *,
                upsert: bool = False,
            ) -> None:
                calls.append({"filter": filter, "update": update, "upsert": upsert})

            async def find_one(self, filter: dict[str, Any]) -> dict[str, Any] | None:
                return None  # not exercised in this test

        store = MongoEloStore(RecordingCollection())
        await store.save({"m": (1500.0, 1)}, cursor="t")
        assert len(calls) == 1
        assert calls[0]["upsert"] is True
        assert calls[0]["update"]["$set"]["cursor"] == "t"
