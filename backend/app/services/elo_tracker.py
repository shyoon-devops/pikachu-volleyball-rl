"""Background Elo-rating tracker.

Runs alongside training: polls the EvaluationRepository for new
EvalRecords, feeds them into an EloRatingSystem, and persists the
updated ratings to an EloStore. The last-applied cursor is saved
alongside the ratings so a restart won't double-count records.

Design goals:
    * No blocking I/O in the event loop — repository/store are async.
    * Pure `tick()` method so tests can drive one iteration at a time.
    * `start()` / `stop()` manage a cancellable background asyncio.Task.
    * Injectable clock, so deterministic tests don't have to sleep.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from backend.app.models.evaluation import EvaluationRecord
from backend.app.services.evaluation_repository import EvaluationRepository
from backend.rl.elo import EloRatingSystem

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS: float = 60.0
# Upper bound on records pulled per tick. Plenty for steady training,
# small enough to keep a single tick bounded if there's backlog.
TICK_PULL_LIMIT: int = 500


@dataclass(frozen=True)
class RatingEntry:
    player_id: str
    rating: float
    games_played: int

    def to_dict(self) -> dict[str, object]:
        return {
            "player_id": self.player_id,
            "rating": round(self.rating, 2),
            "games_played": self.games_played,
        }


@dataclass(frozen=True)
class TickReport:
    """Observable result of one tick — useful for tests and telemetry."""

    records_applied: int
    total_players: int
    last_cursor: str | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class EloStore(Protocol):
    """Persistence contract for Elo state.

    Implementations:
        MongoEloStore   — production (single upsert document)
        InMemoryEloStore — tests
    """

    async def load(self) -> tuple[dict[str, tuple[float, int]], str | None]: ...

    async def save(
        self,
        state: dict[str, tuple[float, int]],
        cursor: str | None,
    ) -> None: ...


@dataclass
class InMemoryEloStore:
    """Test/default store — holds state in a dict."""

    _state: dict[str, tuple[float, int]] = field(default_factory=dict)
    _cursor: str | None = None

    async def load(self) -> tuple[dict[str, tuple[float, int]], str | None]:
        return dict(self._state), self._cursor

    async def save(
        self,
        state: dict[str, tuple[float, int]],
        cursor: str | None,
    ) -> None:
        self._state = dict(state)
        self._cursor = cursor


class MongoEloStore:
    """Persists Elo state as a single document in the `elo_state` collection.

    Uses a stable `_id` of "singleton" so the upsert writes always land on
    the same document. The collection is a motor AsyncIOMotorCollection
    in production and a FakeCollection under tests (same duck-typed API).
    """

    DOC_ID: str = "singleton"

    def __init__(self, collection: Any) -> None:
        self._col = collection

    async def load(self) -> tuple[dict[str, tuple[float, int]], str | None]:
        doc = await self._col.find_one({"_id": self.DOC_ID})
        if doc is None:
            return {}, None
        raw_state = doc.get("ratings", {}) or {}
        state: dict[str, tuple[float, int]] = {}
        for pid, entry in raw_state.items():
            rating = float(entry.get("rating", 0.0))
            games = int(entry.get("games_played", 0))
            state[pid] = (rating, games)
        cursor = doc.get("cursor")
        return state, (str(cursor) if cursor is not None else None)

    async def save(
        self,
        state: dict[str, tuple[float, int]],
        cursor: str | None,
    ) -> None:
        serialized = {
            pid: {"rating": rating, "games_played": games}
            for pid, (rating, games) in state.items()
        }
        # We reach for `update_one` when the backing collection supports
        # it (motor/FakeCollection can opt in). Otherwise we fall back
        # to a delete+insert-one pattern that any fake will handle.
        doc = {
            "_id": self.DOC_ID,
            "ratings": serialized,
            "cursor": cursor,
        }
        update_one = getattr(self._col, "update_one", None)
        if update_one is not None:
            await update_one({"_id": self.DOC_ID}, {"$set": doc}, upsert=True)
            return
        # Fallback: insert_one after clearing (only used by minimal fakes)
        delete_one = getattr(self._col, "delete_one", None)
        if delete_one is not None:
            await delete_one({"_id": self.DOC_ID})
        await self._col.insert_one(doc)


def _hydrate_elo(state: dict[str, tuple[float, int]]) -> EloRatingSystem:
    """Build an EloRatingSystem pre-seeded with persisted ratings."""
    rs = EloRatingSystem()
    # Bot anchors are already seeded in __post_init__ — override with
    # any persisted values (the tracker may have drifted L3/L5 ratings
    # based on actual results).
    for pid, (rating, games) in state.items():
        rs._ratings[pid] = rating
        rs._games[pid] = games
    return rs


def _extract_state(rs: EloRatingSystem) -> dict[str, tuple[float, int]]:
    return {pid: (rating, rs._games.get(pid, 0)) for pid, rating in rs._ratings.items()}


class EloTracker:
    """Polls EvaluationRepository and keeps an EloStore up to date.

    Call `start()` to spawn the background loop and `stop()` to cancel
    it. For unit tests, call `tick()` directly.
    """

    def __init__(
        self,
        repository: EvaluationRepository,
        store: EloStore,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._repo = repository
        self._store = store
        self._interval = poll_interval_seconds
        self._sleep = sleep or asyncio.sleep
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()

    # ---------- Lifecycle ----------

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            logger.debug("EloTracker.start called while task already running")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="elo-tracker")

    async def stop(self) -> None:
        self._stop_event.set()
        task = self._task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        self._task = None

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 — never kill the loop
                logger.exception("EloTracker.tick failed; continuing")
            try:
                await self._sleep(self._interval)
            except asyncio.CancelledError:
                break

    # ---------- Core work ----------

    async def tick(self) -> TickReport:
        """Apply new evaluation records to the Elo state, atomically."""
        async with self._lock:
            try:
                state, cursor = await self._store.load()
                rs = _hydrate_elo(state)

                records = await self._repo.list(
                    since=cursor,
                    limit=TICK_PULL_LIMIT,
                )
                # Repository returns newest-first; apply oldest-first so
                # cursor advancement is monotonic.
                new_records = _filter_new(records, cursor)
                new_records.sort(key=lambda r: r.timestamp)

                for rec in new_records:
                    rs.update_from_eval(_record_to_eval(rec))

                new_state = _extract_state(rs)
                new_cursor = new_records[-1].timestamp if new_records else cursor
                await self._store.save(new_state, new_cursor)

                return TickReport(
                    records_applied=len(new_records),
                    total_players=len(new_state),
                    last_cursor=new_cursor,
                )
            except Exception as exc:  # noqa: BLE001 — reported, not swallowed
                logger.exception("EloTracker.tick failure")
                return TickReport(
                    records_applied=0,
                    total_players=0,
                    last_cursor=None,
                    error=f"{type(exc).__name__}: {exc}",
                )

    async def get_ratings(self) -> list[RatingEntry]:
        """Snapshot of current ratings, sorted high → low."""
        async with self._lock:
            state, _ = await self._store.load()
        entries = [
            RatingEntry(player_id=pid, rating=rating, games_played=games)
            for pid, (rating, games) in state.items()
        ]
        entries.sort(key=lambda e: e.rating, reverse=True)
        return entries


def _filter_new(
    records: list[EvaluationRecord], cursor: str | None
) -> list[EvaluationRecord]:
    """Records strictly after the cursor — cursor is inclusive in Mongo
    queries (`$gte`), so we de-dupe here by comparing timestamps."""
    if cursor is None:
        return list(records)
    return [r for r in records if r.timestamp > cursor]


def _record_to_eval(record: EvaluationRecord):  # -> backend.rl.evaluator.EvalResult
    """Adapt a stored record to the EvalResult shape the Elo system wants."""
    from backend.rl.evaluator import EvalResult  # local import avoids cycle

    return EvalResult(
        model_path=record.model_path,
        bot_level=record.bot_level,
        n_games=record.n_games,
        win_rate=record.win_rate,
        avg_score=record.avg_score,
        avg_opponent_score=record.avg_opponent_score,
        avg_rally_length=record.avg_rally_length,
        avg_episode_length=record.avg_episode_length,
        timestamp=record.timestamp,
        dominance_score=record.dominance_score or 0.0,
    )


__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "TICK_PULL_LIMIT",
    "RatingEntry",
    "TickReport",
    "EloStore",
    "InMemoryEloStore",
    "MongoEloStore",
    "EloTracker",
]
