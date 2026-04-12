"""Training metrics persistence + time-bucketed aggregation (BE-7).

The MetricsCallback (backend/rl/callbacks.py) emits a snapshot roughly every
``log_interval`` timesteps. At production scale that's thousands of snapshots
per experiment — fine to ship over the live WS for the dashboard, but far too
granular for a zoomed-out chart. This service:

  1. **Persists** each snapshot to the ``metrics`` collection with a server-
     side ``timestamp`` and the running ``experiment_id``. Writes go through
     ``with_mongo_retry`` so transient Mongo blips don't drop samples.
  2. **Aggregates** on read using MongoDB's ``$dateTrunc`` + ``$group``
     pipeline. The query uses the ``metrics_experiment_timestamp`` index
     declared in ``backend/app/services/indexes.py`` (BE-5), so the bucket
     endpoint stays cheap even as the collection grows.

Why server-side aggregation instead of pre-computing rollups:

  * Data volume stays modest — hundreds of snapshots per experiment, not
    millions. ``$group`` over an indexed time range is sub-100ms at this
    scale.
  * No second write path to keep in sync. A rollup table would double the
    failure surface (raw persist + rollup persist) for no latency win.
  * Bucket sizes can be requested on demand; we are not married to a fixed
    rollup grain.

If metrics cardinality grows (multi-agent fleets, longer experiments), we
can introduce a materialized rollup collection behind the same interface.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.app.services.db_utils import with_mongo_retry

logger = logging.getLogger(__name__)


# Allowed bucket grains. Keys map to MongoDB ``$dateTrunc`` (unit, binSize)
# pairs. Keeping this table explicit — rather than parsing arbitrary
# durations — prevents clients from asking for "3.7 minute" buckets and
# lets us reason about index usage.
_BUCKETS: dict[str, tuple[str, int]] = {
    "1m": ("minute", 1),
    "5m": ("minute", 5),
    "1h": ("hour", 1),
}

# Soft upper bound on returned buckets. Without a cap a query like
# bucket=1m&since=<a-year-ago> would return ~500k buckets and OOM the
# worker. The frontend's chart renders maybe a few hundred points anyway.
_MAX_BUCKETS = 1000


# --- Metric payload normalization ------------------------------------------
#
# MetricsCallback currently emits:
#     step, episode, mean_reward, win_rate, policy_loss, value_loss
# which does not line up with the legacy ``MetricRecord`` Pydantic schema
# (reward / loss). Rather than rename the callback fields — and break any
# live frontend consumers — we persist the wire payload verbatim and
# aggregate over its real field names.
_NUMERIC_FIELDS: tuple[str, ...] = (
    "mean_reward",
    "win_rate",
    "policy_loss",
    "value_loss",
)


class MetricsService:
    """Persist training metrics and serve time-bucketed aggregates."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["metrics"]

    async def record(self, experiment_id: str, data: dict[str, Any]) -> None:
        """Persist a single metric snapshot.

        Args:
            experiment_id: Id of the owning training run. Stored as-is; an
                empty string is tolerated (pre-start or unknown) but the
                document can still be aggregated over ``timestamp`` alone.
            data: The MetricsCallback payload, as emitted on the WS wire.
                Copied before mutation so we never edit the caller's dict.

        Errors are swallowed and logged — metrics persistence is best
        effort, never a hard requirement for the live dashboard or training
        loop. A transient Mongo outage should not crash the push loop.
        """
        doc = dict(data)
        doc["experiment_id"] = experiment_id or ""
        # Server-side timestamp: we trust the wall clock of the API node
        # over whatever the training thread might eventually stamp. Using
        # UTC explicitly keeps $dateTrunc behavior deterministic regardless
        # of the host timezone.
        doc["timestamp"] = datetime.now(timezone.utc)

        async def _insert() -> None:
            await self._col.insert_one(doc)

        try:
            await with_mongo_retry(_insert, op_name="metrics_record")
        except Exception:
            # Absolutely never propagate — the push loop owns correctness
            # for the live broadcast; persistence is an observability side
            # channel. We log loudly so ops can trace metric gaps.
            logger.exception(
                "metrics_record failed; metric snapshot dropped (experiment_id=%s)",
                experiment_id,
            )

    async def aggregate(
        self,
        *,
        experiment_id: str | None = None,
        bucket: str = "1m",
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return time-bucketed averages for a training run.

        Args:
            experiment_id: Restrict to one run. ``None`` aggregates across
                all runs — useful for global cluster views but cardinality
                can get uncomfortable; clients should pass one.
            bucket: One of ``"1m"``, ``"5m"``, ``"1h"``. Rejected otherwise
                rather than silently falling back so typos surface early.
            since, until: Optional inclusive / exclusive bounds on
                ``timestamp``. If both omitted we default to the last 6 hours
                so an unqualified query doesn't scan the full collection.

        Returns:
            List of ``{bucket_start, count, avg_<field>, ..., step_max}``
            documents, sorted by ``bucket_start`` ascending.
        """
        if bucket not in _BUCKETS:
            raise ValueError(f"unknown bucket {bucket!r}; choose from {sorted(_BUCKETS)}")

        unit, bin_size = _BUCKETS[bucket]
        if since is None and until is None:
            # Sensible default so the endpoint can't accidentally scan the
            # entire metrics collection for an unbounded range.
            since = datetime.now(timezone.utc) - timedelta(hours=6)

        match: dict[str, Any] = {}
        if experiment_id is not None:
            match["experiment_id"] = experiment_id
        ts_filter: dict[str, Any] = {}
        if since is not None:
            ts_filter["$gte"] = since
        if until is not None:
            ts_filter["$lt"] = until
        if ts_filter:
            match["timestamp"] = ts_filter

        # Build $avg stanzas only for the fields we know about. Storing the
        # set inline would let a caller inject arbitrary field names into
        # the pipeline; the explicit table keeps the query surface bounded.
        avg_stanzas = {f"avg_{field}": {"$avg": f"${field}"} for field in _NUMERIC_FIELDS}

        pipeline: list[dict[str, Any]] = [
            {"$match": match},
            {
                "$group": {
                    "_id": {
                        "$dateTrunc": {
                            "date": "$timestamp",
                            "unit": unit,
                            "binSize": bin_size,
                            "timezone": "UTC",
                        }
                    },
                    "count": {"$sum": 1},
                    "step_max": {"$max": "$step"},
                    **avg_stanzas,
                }
            },
            {"$sort": {"_id": 1}},
            {"$limit": _MAX_BUCKETS},
            {
                "$project": {
                    "_id": 0,
                    "bucket_start": "$_id",
                    "count": 1,
                    "step_max": 1,
                    **{k: 1 for k in avg_stanzas},
                }
            },
        ]

        async def _run() -> list[dict[str, Any]]:
            cursor = self._col.aggregate(pipeline)
            return await cursor.to_list(length=_MAX_BUCKETS)

        return await with_mongo_retry(_run, op_name="metrics_aggregate")

    async def recent_points(
        self,
        *,
        field: str,
        limit: int = 100,
        experiment_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the most recent ``limit`` raw (step, value) pairs for ``field``.

        Feeds the ``/api/training/timeseries`` endpoint that repaints the
        dashboard chart on page refresh: the frontend wants the N newest
        points so the live WS stream can extend the line to the right. We
        fetch newest-first from Mongo (the index covers this) and reverse
        to newest-last so the client doesn't have to sort.

        ``field`` MUST be one of ``_NUMERIC_FIELDS`` — the REST layer maps
        friendly aliases (``"reward"`` etc.) to these canonical names, so an
        arbitrary string here is a programming error we want to surface
        loudly rather than silently miss in the projection.
        """
        if field not in _NUMERIC_FIELDS:
            raise ValueError(
                f"unknown metric field {field!r}; allowed: {sorted(_NUMERIC_FIELDS)}"
            )

        match: dict[str, Any] = {}
        if experiment_id is not None:
            match["experiment_id"] = experiment_id
        # Only include docs that actually carry the field — otherwise the
        # projection would emit ``None`` entries that crash the chart.
        match[field] = {"$exists": True}

        projection = {"_id": 0, "step": 1, "timestamp": 1, field: 1}

        async def _run() -> list[dict[str, Any]]:
            cursor = (
                self._col.find(match, projection)
                .sort("timestamp", -1)
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            # Return newest-last so the FE can simply ``push`` new WS frames.
            docs.reverse()
            out: list[dict[str, Any]] = []
            for d in docs:
                ts = d.get("timestamp")
                # Normalise to ISO-8601 UTC so the FE doesn't have to know
                # about Mongo BSON datetime. ``None`` when absent — keeps the
                # shape stable for consumers that expect the key.
                if isinstance(ts, datetime):
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    ts_iso: str | None = ts.astimezone(timezone.utc).isoformat()
                else:
                    ts_iso = None
                out.append({
                    "step": d.get("step", 0),
                    "value": d.get(field, 0.0),
                    "timestamp": ts_iso,
                })
            return out

        return await with_mongo_retry(_run, op_name="metrics_recent_points")


def allowed_buckets() -> tuple[str, ...]:
    """Public list of accepted bucket tokens — handy for validators/docs."""
    return tuple(_BUCKETS.keys())
