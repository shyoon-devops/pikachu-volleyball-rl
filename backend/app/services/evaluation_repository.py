"""Evaluation-result persistence for dev/qa/prod MongoDB databases.

The repository talks to any object that implements `EvaluationCollection`
(a Protocol matching the subset of Motor's collection API we actually
use). Production wires it to Motor's AsyncIOMotorCollection; tests use
an in-memory fake that satisfies the same contract.

Responsibilities:
    * Validate + persist EvaluationCreate payloads
    * Query by model_path / bot_level / window
    * Aggregate into per-checkpoint series (used by the time-series API)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Protocol

from backend.app.models.evaluation import EvaluationCreate, EvaluationRecord

COLLECTION_NAME: str = "evaluations"
DEFAULT_QUERY_LIMIT: int = 200
MAX_QUERY_LIMIT: int = 1000


class EvaluationCollection(Protocol):
    """Subset of motor's AsyncIOMotorCollection that the repository uses."""

    async def insert_one(self, document: dict[str, Any]) -> Any: ...

    def find(
        self, filter: dict[str, Any] | None = ..., *args: Any, **kwargs: Any
    ) -> "AsyncCursor": ...

    async def find_one(
        self, filter: dict[str, Any] | None = ..., *args: Any, **kwargs: Any
    ) -> dict[str, Any] | None: ...


class AsyncCursor(Protocol):
    """Minimal cursor protocol covering .sort and async iteration."""

    def sort(self, key_or_list: Any, direction: int = ...) -> "AsyncCursor": ...
    def limit(self, n: int) -> "AsyncCursor": ...
    def __aiter__(self) -> AsyncIterator[dict[str, Any]]: ...


def _clamp_limit(value: int | None) -> int:
    if value is None or value <= 0:
        return DEFAULT_QUERY_LIMIT
    return min(value, MAX_QUERY_LIMIT)


class EvaluationRepository:
    """CRUD-ish repository for evaluation records."""

    def __init__(self, collection: EvaluationCollection) -> None:
        self._collection = collection

    async def save(self, payload: EvaluationCreate) -> EvaluationRecord:
        """Persist a new evaluation record.

        Fills in `dominance_score` if the caller omitted it, generates a
        stable `id`, and stamps `inserted_at` in UTC. Returns the full
        stored record.
        """
        enriched = payload.with_derived_fields()
        doc = enriched.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["inserted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Delegate to the underlying collection. We never rely on the
        # returned _id — our `id` field is the stable identifier.
        await self._collection.insert_one(dict(doc))
        return EvaluationRecord(**doc)

    async def save_many(
        self, payloads: list[EvaluationCreate]
    ) -> list[EvaluationRecord]:
        """Persist many records. Sequential on purpose — tiny batches and
        MongoDB drivers already pipeline under the hood."""
        return [await self.save(p) for p in payloads]

    async def list(
        self,
        *,
        model_path: str | None = None,
        bot_level: int | None = None,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[EvaluationRecord]:
        """List records sorted newest-first with optional filters."""
        query: dict[str, Any] = {}
        if model_path is not None:
            query["model_path"] = model_path
        if bot_level is not None:
            query["bot_level"] = bot_level
        if since is not None:
            query["timestamp"] = {"$gte": since}

        cursor = self._collection.find(query).sort("timestamp", -1).limit(_clamp_limit(limit))
        out: list[EvaluationRecord] = []
        async for doc in cursor:
            out.append(EvaluationRecord.from_mongo(doc))
        return out

    async def get(self, record_id: str) -> EvaluationRecord | None:
        """Fetch a single record by its `id` field (our UUID, not _id)."""
        doc = await self._collection.find_one({"id": record_id})
        if doc is None:
            return None
        return EvaluationRecord.from_mongo(doc)

    async def list_checkpoints(self, *, limit: int | None = None) -> list[str]:
        """Return distinct model_paths present in storage, newest-seen first."""
        seen: dict[str, str] = {}
        cursor = self._collection.find({}).sort("timestamp", -1).limit(
            _clamp_limit(limit) * 5  # overscan — many records per checkpoint
        )
        async for doc in cursor:
            mp = doc.get("model_path")
            if mp and mp not in seen:
                seen[mp] = doc.get("timestamp", "")
        return list(seen.keys())


__all__ = [
    "COLLECTION_NAME",
    "DEFAULT_QUERY_LIMIT",
    "MAX_QUERY_LIMIT",
    "EvaluationCollection",
    "EvaluationRepository",
]
