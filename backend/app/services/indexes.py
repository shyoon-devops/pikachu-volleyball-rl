"""MongoDB index setup — idempotent, run at startup.

The indexes listed here back the hot query paths exercised by the REST
endpoints. They are kept in a dedicated module (not per-service) so ops can
audit "what indexes does the app assume exist?" in one place, and so a new
collection gaining an index does not require touching service code.

Contract:
- Every index declared here has a stable ``name`` so a later deployment can
  drop or alter it without relying on auto-generated names.
- ``create_indexes`` is idempotent: Mongo no-ops when an identical index
  already exists. A *different* spec under the same name raises
  ``OperationFailure`` — treat that as a schema migration signal rather than
  silently fighting the existing index.
- Index creation is best-effort: if Mongo is unavailable we log and move on.
  The app still starts; queries work without the index, just slower. The
  readiness probe is the authoritative "is Mongo reachable" signal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import OperationFailure

from backend.app.services.db_utils import TRANSIENT_ERRORS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _IndexSpec:
    """Declarative index spec for a single collection."""

    collection: str
    models: tuple[IndexModel, ...]


# --- Declared indexes -------------------------------------------------------
#
# Each IndexModel gets an explicit ``name`` so deployments can reason about
# them without inspecting Mongo's auto-generated identifiers.

_GAME_INDEXES = _IndexSpec(
    collection="games",
    models=(
        # Primary list query: ``find().sort("timestamp", -1).skip().limit()``.
        IndexModel([("timestamp", DESCENDING)], name="games_timestamp_desc"),
        # Replay → game lookup by uuid4 game_id. Unique on the subset of
        # documents that actually carry the field — ``game_id`` was added
        # mid-sprint (ac03e02) so older records don't have it, and a plain
        # ``unique=True`` would fail at build time on legacy data.
        IndexModel(
            [("game_id", ASCENDING)],
            name="games_game_id",
            unique=True,
            partialFilterExpression={"game_id": {"$type": "string"}},
        ),
        # Compound for per-experiment history; ordering matches the list query.
        IndexModel(
            [("experiment_id", ASCENDING), ("timestamp", DESCENDING)],
            name="games_experiment_timestamp",
        ),
    ),
)

_EVAL_INDEXES = _IndexSpec(
    collection="evaluations",
    models=(
        IndexModel([("timestamp", DESCENDING)], name="evaluations_timestamp_desc"),
        IndexModel(
            [("model_path", ASCENDING), ("timestamp", DESCENDING)],
            name="evaluations_model_timestamp",
        ),
    ),
)

_METRIC_INDEXES = _IndexSpec(
    collection="metrics",
    models=(
        # Aggregation queries (see BE-7) bucket by time; experiment_id is the
        # usual filter dimension.
        IndexModel(
            [("experiment_id", ASCENDING), ("timestamp", DESCENDING)],
            name="metrics_experiment_timestamp",
        ),
        IndexModel([("timestamp", DESCENDING)], name="metrics_timestamp_desc"),
    ),
)

_ALL_INDEXES: tuple[_IndexSpec, ...] = (_GAME_INDEXES, _EVAL_INDEXES, _METRIC_INDEXES)


async def ensure_indexes(db: AsyncIOMotorDatabase) -> dict[str, list[str]]:
    """Ensure declared indexes exist on every known collection.

    Returns a mapping of collection name → list of index names created or
    already present. Index failures on one collection are logged and do not
    block the others — a missing index only costs query latency, not
    correctness.
    """
    results: dict[str, list[str]] = {}
    for spec in _ALL_INDEXES:
        try:
            names = await db[spec.collection].create_indexes(list(spec.models))
            results[spec.collection] = names
            logger.info(
                "ensured indexes on %s: %s",
                spec.collection,
                names,
                extra={"collection": spec.collection, "indexes": names},
            )
        except OperationFailure as e:
            # Spec mismatch against an existing index → surface loudly so we
            # notice schema drift, but do not crash the app startup.
            logger.error(
                "index spec mismatch on %s: %s. Existing indexes must be "
                "dropped before the new spec can take effect.",
                spec.collection,
                e,
                extra={"collection": spec.collection},
            )
            results[spec.collection] = []
        except TRANSIENT_ERRORS as e:
            logger.warning(
                "transient error creating indexes on %s; will retry on next restart: %s",
                spec.collection,
                e,
            )
            results[spec.collection] = []
    return results
