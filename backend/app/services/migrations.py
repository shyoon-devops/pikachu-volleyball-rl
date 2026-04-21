"""Startup-time Mongo data migrations — idempotent.

The app uses MongoDB (not a SQL store), so "ALTER TABLE ADD COLUMN"
schema changes translate to ``update_many`` backfills. Each migration
here must be idempotent so a re-run after partial completion is safe —
we key on ``{field: {"$exists": False}}`` rather than a version stamp
since the dev/prod footprint is tiny and a version-table would add
complexity without upside.

Migrations run once per process at lifespan startup (see
``backend/app/main.py``). Failures log and continue so a transient
Mongo hiccup at boot doesn't block the app from coming up.
"""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


async def backfill_training_runs_reward_model(
    db: AsyncIOMotorDatabase | None,
) -> int:
    """Backfill ``reward_model="shaped_v1"`` onto pre-v2.x run docs.

    Every v1.0.0-era run was shaped_v1 by construction — the selector
    didn't exist until ADR 0015 (v2.x Sprint-2). Matches the
    ``TrainingRunsService.register`` default so a row backfilled here
    is indistinguishable from one inserted fresh today.

    Idempotent: the ``$exists: False`` filter means re-running after
    completion matches zero docs (the previous run set the field).
    Returns the number of docs touched so the caller can log progress.
    Mongo-less / collection missing: no-op, returns 0.
    """
    if db is None:
        return 0
    try:
        result: Any = await db["training_runs"].update_many(
            {"reward_model": {"$exists": False}},
            {"$set": {"reward_model": "shaped_v1"}},
        )
    except Exception:  # noqa: BLE001 — non-fatal; startup continues
        logger.exception("backfill_training_runs_reward_model failed")
        return 0
    count = int(getattr(result, "modified_count", 0) or 0)
    if count:
        logger.info(
            "backfill_training_runs_reward_model: set shaped_v1 on %d docs",
            count,
        )
    return count


async def backfill_training_runs_policy_type(
    db: AsyncIOMotorDatabase | None,
) -> int:
    """Backfill ``policy_type="mlp_v1"`` onto pre-Sprint-3 run docs.

    ADR 0016 §9 mirror of the reward_model migration. Every pre-
    Sprint-3 run used SB3's ``MlpPolicy`` so the backfill value is the
    empirically-correct tag, not a stand-in. Matches
    ``TrainingRunsService.register``'s default so a row backfilled here
    is indistinguishable from a fresh Sprint-3 run that omitted the
    kwarg.

    Idempotent via the ``$exists: False`` filter; safe to invoke on
    every app start. Mongo-less deployments no-op.
    """
    if db is None:
        return 0
    try:
        result: Any = await db["training_runs"].update_many(
            {"policy_type": {"$exists": False}},
            {"$set": {"policy_type": "mlp_v1"}},
        )
    except Exception:  # noqa: BLE001 — non-fatal; startup continues
        logger.exception("backfill_training_runs_policy_type failed")
        return 0
    count = int(getattr(result, "modified_count", 0) or 0)
    if count:
        logger.info(
            "backfill_training_runs_policy_type: set mlp_v1 on %d docs",
            count,
        )
    return count


__all__ = [
    "backfill_training_runs_reward_model",
    "backfill_training_runs_policy_type",
]
