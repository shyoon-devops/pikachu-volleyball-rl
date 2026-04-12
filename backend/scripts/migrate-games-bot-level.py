#!/usr/bin/env python3
"""One-shot migration: backfill games.bot_level / games.experiment_id.

Context
-------
Prior to commit a532bdc4 (fix(ws): route missing bot_level/experiment_id
to dead-letter, not silent L1), ``LiveFrameCallback._on_step`` omitted
both ``bot_level`` and ``experiment_id`` from the results dict. The WS
handler silently coerced a missing bot_level to 1. Result: every row in
the ``games`` collection shows bot_level=1 regardless of the user's
actual training level, and experiment_id is the empty string.

Those legacy rows can't be recovered — the information was never
captured. This migration only ensures the *shape* is consistent:
rows that are missing the field entirely get it added (with the same
silent-L1 value the handler used to write), so FE code reading
``game.bot_level`` never sees ``undefined``.

Usage
-----
    # Dry run — report what would change, no writes.
    python -m backend.scripts.migrate-games-bot-level

    # Apply.
    python -m backend.scripts.migrate-games-bot-level --commit

    # Override connection.
    MONGODB_URL=mongodb://host/db python -m backend.scripts.migrate-games-bot-level --commit

Idempotency
-----------
A rerun after --commit is a no-op: the filters only match rows where the
field is *absent* or invalid. Rows written by the post-fix code path are
already valid and will never match.

Why this is a separate script
-----------------------------
* It's a one-time operation, not part of normal request flow.
* It reads every game doc — must not run inside the event loop that
  serves user traffic.
* Dry-run-first protects against accidentally writing the wrong default
  to a production DB before we've had a chance to inspect the diff.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("migrate-games-bot-level")

# Same default used by TrainingManager.__init__ and the pre-fix handler
# fallback — keeping it here (rather than importing from the app) so the
# script stays runnable against a checked-out repo without pulling in
# the FastAPI dependency graph just to read one int.
DEFAULT_BOT_LEVEL = 1
DEFAULT_EXPERIMENT_ID = ""
VALID_LEVEL_RANGE = (1, 5)


def _build_client() -> tuple[AsyncIOMotorClient, str]:
    """Build a Motor client from MONGODB_URL and return the db name."""
    url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/pikachu_rl")
    client = AsyncIOMotorClient(
        url,
        # Short timeouts — a migration that hangs for 30s per op is useless.
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    # AsyncIOMotorClient.get_default_database picks the DB from the URL.
    db_name = client.get_default_database().name
    return client, db_name


async def _count_and_preview(col, filt: dict, label: str, preview_n: int = 5) -> int:
    """Count docs matching filter and log the first N game_ids as a preview."""
    total = await col.count_documents(filt)
    if total == 0:
        logger.info("[%s] 0 documents match — nothing to migrate.", label)
        return 0

    cursor = col.find(filt, {"game_id": 1, "_id": 1}).limit(preview_n)
    sample = [doc async for doc in cursor]
    preview = ", ".join(
        str(doc.get("game_id") or doc.get("_id")) for doc in sample
    )
    logger.info(
        "[%s] %d document(s) match. Preview (first %d): %s%s",
        label, total, min(preview_n, total), preview,
        " ..." if total > preview_n else "",
    )
    return total


async def _migrate(commit: bool) -> int:
    """Return a process exit code: 0 = success, non-zero on error."""
    client, db_name = _build_client()
    try:
        db = client.get_default_database()
        col = db["games"]

        logger.info("Connected to MongoDB database %r, collection 'games'.", db_name)

        # --- Bucket 1: bot_level missing entirely -----------------------
        # The pre-fix insert path called GameRecord(bot_level=...) with
        # data.get("bot_level", 1), so bot_level WAS written — just as 1.
        # Rows missing the field only exist if a record was inserted by
        # legacy code paths (ad-hoc scripts, imports, very old versions).
        missing_level = {"bot_level": {"$exists": False}}
        n_missing_level = await _count_and_preview(
            col, missing_level, "missing bot_level",
        )

        # --- Bucket 2: bot_level out of range --------------------------
        # GameRecord enforces 1..5. Old docs could contain 0 or other
        # stale values from early development. Clamp to the default
        # rather than dropping — the game itself is still a valid
        # record of play.
        lo, hi = VALID_LEVEL_RANGE
        out_of_range = {
            "bot_level": {"$exists": True},
            "$or": [{"bot_level": {"$lt": lo}}, {"bot_level": {"$gt": hi}}],
        }
        n_out_of_range = await _count_and_preview(
            col, out_of_range, "bot_level out of range",
        )

        # --- Bucket 3: experiment_id missing ---------------------------
        # Empty string is the official post-fix legacy value for rows
        # that predate per-experiment tracking; missing field is not.
        missing_exp = {"experiment_id": {"$exists": False}}
        n_missing_exp = await _count_and_preview(
            col, missing_exp, "missing experiment_id",
        )

        total_to_fix = n_missing_level + n_out_of_range + n_missing_exp
        if total_to_fix == 0:
            logger.info("Nothing to do — DB already matches post-fix shape.")
            return 0

        if not commit:
            logger.warning(
                "DRY RUN — pass --commit to apply. Would update %d document(s) "
                "(missing_level=%d, out_of_range=%d, missing_exp=%d).",
                total_to_fix, n_missing_level, n_out_of_range, n_missing_exp,
            )
            return 0

        # --- Apply writes -----------------------------------------------
        # Done as three targeted updateMany calls rather than one
        # $set-everything sweep, so the audit log shows exactly which
        # bucket each row fell into. $exists + $lt/$gt filters make
        # each write idempotent.
        if n_missing_level:
            res = await col.update_many(
                missing_level, {"$set": {"bot_level": DEFAULT_BOT_LEVEL}},
            )
            logger.info(
                "Backfilled bot_level=%d on %d doc(s).",
                DEFAULT_BOT_LEVEL, res.modified_count,
            )

        if n_out_of_range:
            res = await col.update_many(
                out_of_range, {"$set": {"bot_level": DEFAULT_BOT_LEVEL}},
            )
            logger.info(
                "Clamped out-of-range bot_level→%d on %d doc(s).",
                DEFAULT_BOT_LEVEL, res.modified_count,
            )

        if n_missing_exp:
            res = await col.update_many(
                missing_exp, {"$set": {"experiment_id": DEFAULT_EXPERIMENT_ID}},
            )
            logger.info(
                "Backfilled experiment_id=%r on %d doc(s).",
                DEFAULT_EXPERIMENT_ID, res.modified_count,
            )

        logger.info("Migration complete.")
        return 0
    except Exception:
        logger.exception("Migration failed")
        return 1
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", action="store_true",
        help="Actually write changes. Without this flag, dry-run only.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG-level logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(_migrate(commit=args.commit))


if __name__ == "__main__":
    sys.exit(main())
