"""In-memory job registry for long-running evaluations.

Each evaluation runs as an asyncio task that calls the blocking evaluator
on a worker thread. The registry exposes the job's lifecycle
(pending → running → done / failed) plus per-game progress so clients can
poll instead of holding an HTTP connection open for the full duration.

Rationale
---------
The synchronous ``/api/evaluation/run`` endpoint held the TCP connection
open for the full evaluation (minutes, sometimes tens of minutes). Nginx
defaults to a 60s upstream timeout, so users got 504s even on short runs.
Making the endpoint fire-and-forget plus a separate status poll sidesteps
the proxy timeout without touching nginx config.

State lives in process memory only — intentional. Evaluations are cheap
to re-run and the user-visible result is persisted to Mongo via the
service's own write, so losing in-flight state on restart is acceptable.
A bounded LRU cap keeps the registry from growing unboundedly under
repeated polling or failed runs.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Cap on the number of remembered jobs. Old entries are evicted FIFO so
# a long-running deployment does not accumulate stale job dicts forever.
# Picked large enough that a user polling yesterday's job still finds it,
# small enough that the registry stays a few kilobytes of RSS.
_MAX_JOBS: int = 100

JobState = Literal["pending", "running", "done", "failed"]


class EvalJobRegistry:
    """Async-safe in-memory job store.

    All mutations happen under a single ``asyncio.Lock`` — the registry
    is only touched from the event loop (background task callbacks + the
    HTTP handlers), so contention is negligible and a lock keeps the
    read-then-write compound operations atomic.
    """

    def __init__(self, max_jobs: int = _MAX_JOBS) -> None:
        self._jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._max_jobs = max_jobs

    async def create(self) -> str:
        """Allocate a fresh job id and seed it in pending state."""
        job_id = str(uuid.uuid4())
        now = _utcnow()
        async with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "state": "pending",
                "progress_current": 0,
                "progress_total": 0,
                "result": None,
                "error": None,
                "created_at": now,
                "started_at": None,
                "finished_at": None,
            }
            self._evict_if_needed()
        return job_id

    async def mark_running(self, job_id: str, total: int) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["state"] = "running"
            job["started_at"] = _utcnow()
            job["progress_total"] = int(total)

    async def update_progress(self, job_id: str, current: int) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["progress_current"] = int(current)

    async def mark_done(self, job_id: str, result: dict[str, Any]) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["state"] = "done"
            job["result"] = result
            job["finished_at"] = _utcnow()
            # Clip progress to total so the final poll never shows a fractional
            # "12/13" after a successful run — some evaluator implementations
            # don't fire the callback for the final game.
            if job["progress_total"] and job["progress_current"] < job["progress_total"]:
                job["progress_current"] = job["progress_total"]

    async def mark_failed(self, job_id: str, error: str) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["state"] = "failed"
            job["error"] = error
            job["finished_at"] = _utcnow()

    async def get(self, job_id: str) -> dict[str, Any] | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            # Return a shallow copy so callers can't mutate internal state.
            return dict(job)

    def _evict_if_needed(self) -> None:
        while len(self._jobs) > self._max_jobs:
            evicted_id, _ = self._jobs.popitem(last=False)
            logger.debug("eval_jobs: evicted old job %s (cap=%d)", evicted_id, self._max_jobs)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
